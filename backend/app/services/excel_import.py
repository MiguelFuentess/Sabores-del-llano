from __future__ import annotations

import ctypes
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import io
import os
from pathlib import Path
import sys
from typing import Any

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models import (
    CierreDiario,
    Cliente,
    DetallePedido,
    DetalleVenta,
    MovimientoInventario,
    Pedido,
    Presentacion,
    Produccion,
    Producto,
    Venta,
)
from app.schemas.excel_import import (
    ExcelAuditReport,
    ExcelImportResult,
    ExcelSheetSummary,
    ExcelValidationIssue,
    TableImportCounter,
)
from app.services.catalog import seed_initial_catalog
from app.services.colombian_calendar import is_valid_operation_date

REAL_DATA_CUTOFF_DATE = date(2026, 6, 6)
REQUIRED_SHEETS = ("Productos", "Ventas", "Pedidos", "Produccion", "Sobrantes")

_ESTADO_PEDIDO_MAP = {
    "pendiente": "pendiente",
    "confirmado": "confirmado",
    "en preparacion": "en_preparacion",
    "en preparación": "en_preparacion",
    "en_preparacion": "en_preparacion",
    "entregado": "entregado",
    "cancelado": "cancelado",
}


@dataclass(frozen=True)
class ParsedVentaRow:
    row_number: int
    fecha: date
    producto: str
    presentacion_unidad: str
    cantidad: int
    precio_unitario: Decimal
    total_venta: Decimal
    es_sintetico: bool
    alerta_calendario: str | None


@dataclass(frozen=True)
class ParsedPedidoRow:
    row_number: int
    fecha_pedido: date
    fecha_entrega: date
    cliente: str
    producto: str
    cantidad: int
    estado_db: str
    es_sintetico: bool
    alerta_calendario: str | None


@dataclass(frozen=True)
class ParsedProduccionRow:
    row_number: int
    fecha: date
    producto: str
    ventas: int
    sobrantes: int
    produccion: int
    es_sintetico: bool
    alerta_calendario: str | None


@dataclass(frozen=True)
class ParsedWorkbookData:
    report: ExcelAuditReport
    ventas: list[ParsedVentaRow]
    pedidos: list[ParsedPedidoRow]
    producciones: list[ParsedProduccionRow]


def build_trace_tag(
    *,
    hoja: str,
    fila: int,
    es_sintetico: bool,
    alerta_calendario: str | None = None,
) -> str:
    """Construye la marca estructurada de trazabilidad para la columna `observaciones` o `notas`."""
    origen = "sintetico" if es_sintetico else "real"
    sintetico_flag = "1" if es_sintetico else "0"
    parts = [
        "IMPORTACION_EXCEL",
        f"origen={origen}",
        f"es_sintetico={sintetico_flag}",
        f"hoja={hoja}",
        f"fila={fila}",
    ]
    if alerta_calendario:
        parts.append(f"alerta_calendario={alerta_calendario}")
    return f"[{'|'.join(parts)}]"


def is_synthetic_trace(observaciones: str | None) -> bool | None:
    """Permite consultar si un registro tiene marca de dato sintético (True), real (False) o ninguna (None)."""
    if not observaciones or "IMPORTACION_EXCEL|" not in observaciones:
        return None
    if "|es_sintetico=1|" in observaciones or observaciones.endswith("|es_sintetico=1]"):
        return True
    if "|es_sintetico=0|" in observaciones or observaciones.endswith("|es_sintetico=0]"):
        return False
    return None


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _is_summary_row(row: tuple[Any, ...]) -> bool:
    first_cells = " ".join(str(cell).strip().lower() for cell in row[:3] if cell is not None)
    return "total general" in first_cells or first_cells.startswith("total")


def _open_excel_stream(path: Path) -> io.BytesIO:
    """Lee el archivo Excel en memoria en modo solo lectura.
    En Windows, si el archivo está abierto simultáneamente en Microsoft Excel
    (que retiene acceso con FILE_SHARE_DELETE), abre el descriptor con
    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE sin modificar el archivo."""
    try:
        return io.BytesIO(path.read_bytes())
    except PermissionError:
        if os.name != "nt":
            raise
        generic_read = 0x80000000
        share_all = 0x00000001 | 0x00000002 | 0x00000004
        open_existing = 3
        file_attribute_normal = 0x80
        invalid_handle_value = ctypes.c_void_p(-1).value

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = ctypes.c_void_p
        handle = kernel32.CreateFileW(
            ctypes.c_wchar_p(str(path)),
            generic_read,
            share_all,
            None,
            open_existing,
            file_attribute_normal,
            None,
        )
        if handle == invalid_handle_value or handle is None:
            raise
        try:
            chunks: list[bytes] = []
            buf = ctypes.create_string_buffer(65536)
            bytes_read = ctypes.c_ulong(0)
            while True:
                ok = kernel32.ReadFile(
                    ctypes.c_void_p(handle),
                    buf,
                    len(buf),
                    ctypes.byref(bytes_read),
                    None,
                )
                if not ok or bytes_read.value == 0:
                    break
                chunks.append(buf.raw[: bytes_read.value])
            return io.BytesIO(b"".join(chunks))
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))


def parse_and_validate_workbook(
    excel_path: str | Path,
    *,
    cutoff_date: date = REAL_DATA_CUTOFF_DATE,
) -> ParsedWorkbookData:
    """Inspecciona y valida todas las hojas del Excel histórico sin tocar la base de datos."""
    path = Path(excel_path)
    if not path.is_file():
        raise FileNotFoundError(f"No se encontró el archivo Excel en: {path}")

    stream = _open_excel_stream(path)
    wb = openpyxl.load_workbook(stream, data_only=True, read_only=True)
    try:
        advertencias: list[ExcelValidationIssue] = []
        errores: list[ExcelValidationIssue] = []
        sheet_summaries: list[ExcelSheetSummary] = []

        missing_sheets = [s for s in REQUIRED_SHEETS if s not in wb.sheetnames]
        if missing_sheets:
            for s in missing_sheets:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja=s,
                        codigo="HOJA_FALTANTE",
                        mensaje=f"El archivo Excel no contiene la hoja obligatoria '{s}'.",
                    )
                )
            report = ExcelAuditReport(
                archivo=path.name,
                valido_para_importar=False,
                fecha_corte_real=cutoff_date,
                advertencias=advertencias,
                errores=errores,
            )
            return ParsedWorkbookData(
                report=report, ventas=[], pedidos=[], producciones=[]
            )

        # 1. Hoja Productos
        ws_prod = wb["Productos"]
        prod_rows = list(ws_prod.iter_rows(min_row=2, values_only=True))
        prod_empty = 0
        catalog_products: dict[str, tuple[str, str, int, Decimal]] = {}
        for idx, row in enumerate(prod_rows, start=2):
            if not any(cell is not None for cell in row):
                prod_empty += 1
                continue
            nombre = str(row[0] or "").strip()
            unidad_base = str(row[1] or "").strip()
            presentacion = str(row[2] or "").strip()
            factor = int(row[3] or 0)
            precio = Decimal(str(row[4] or 0))
            if nombre not in {"Hayaca", "Lechona"}:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Productos",
                        fila=idx,
                        codigo="PRODUCTO_NO_RECONOCIDO",
                        mensaje=f"Producto '{nombre}' fuera del catálogo base permitido.",
                    )
                )
                continue
            catalog_products[nombre] = (unidad_base, presentacion, factor, precio)

        sheet_summaries.append(
            ExcelSheetSummary(
                hoja="Productos",
                filas_totales_con_encabezado=len(prod_rows) + 1,
                filas_vacias_ignoradas=prod_empty,
                registros_validos=len(catalog_products),
                registros_reales=len(catalog_products),
                registros_sinteticos=0,
            )
        )

        # 2. Hoja Ventas
        ws_ventas = wb["Ventas"]
        ventas_rows = list(ws_ventas.iter_rows(min_row=2, values_only=True))
        parsed_ventas: list[ParsedVentaRow] = []
        ventas_empty = 0
        seen_ventas_keys: dict[tuple[date, str], int] = {}

        for idx, row in enumerate(ventas_rows, start=2):
            if not any(cell is not None for cell in row):
                ventas_empty += 1
                continue
            if _is_summary_row(row):
                ventas_empty += 1
                advertencias.append(
                    ExcelValidationIssue(
                        severidad="warning",
                        hoja="Ventas",
                        fila=idx,
                        codigo="FILA_RESUMEN_IGNORADA",
                        mensaje="Se ignoró fila de resumen o total general.",
                    )
                )
                continue

            fecha = _coerce_date(row[0])
            producto = str(row[1] or "").strip()
            presentacion_unidad = str(row[2] or "").strip()
            cantidad = int(row[3] or 0)
            precio_unitario = Decimal(str(row[4] or 0))
            total_venta = Decimal(str(row[5] or 0))

            if fecha is None:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Ventas",
                        fila=idx,
                        codigo="FECHA_INVALIDA",
                        mensaje=f"Fecha inválida en fila {idx} de Ventas.",
                    )
                )
                continue

            if producto not in catalog_products:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Ventas",
                        fila=idx,
                        codigo="PRODUCTO_INEXISTENTE",
                        mensaje=f"El producto '{producto}' no existe en la hoja Productos.",
                    )
                )
                continue

            expected_unit = catalog_products[producto][0]
            if presentacion_unidad != expected_unit:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Ventas",
                        fila=idx,
                        codigo="UNIDAD_PRESENTACION_INCONSISTENTE",
                        mensaje=(
                            f"La unidad '{presentacion_unidad}' no coincide con "
                            f"la unidad base '{expected_unit}' de {producto}."
                        ),
                    )
                )
                continue

            if cantidad <= 0 or precio_unitario <= 0:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Ventas",
                        fila=idx,
                        codigo="CANTIDAD_O_PRECIO_INVALIDO",
                        mensaje="Cantidad y precio unitario deben ser mayores que cero.",
                    )
                )
                continue

            if Decimal(cantidad) * precio_unitario != total_venta:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Ventas",
                        fila=idx,
                        codigo="TOTAL_VENTA_INCONSISTENTE",
                        mensaje=(
                            f"Cantidad ({cantidad}) * Precio ({precio_unitario}) "
                            f"!= Total Venta ({total_venta})."
                        ),
                    )
                )
                continue

            v_key = (fecha, producto)
            if v_key in seen_ventas_keys:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Ventas",
                        fila=idx,
                        codigo="VENTA_DUPLICADA_EN_EXCEL",
                        mensaje=(
                            f"Registro duplicado para ({fecha.isoformat()}, {producto}) "
                            f"en filas {seen_ventas_keys[v_key]} y {idx}."
                        ),
                    )
                )
                continue
            seen_ventas_keys[v_key] = idx

            es_sintetico = fecha < cutoff_date
            alerta_calendario: str | None = None
            if not is_valid_operation_date(fecha):
                weekday_names = (
                    "lunes",
                    "martes",
                    "miercoles",
                    "jueves",
                    "viernes",
                    "sabado",
                    "domingo",
                )
                w_name = weekday_names[fecha.weekday()]
                alerta_calendario = f"{fecha.isoformat()}_{w_name}_no_festivo"
                advertencias.append(
                    ExcelValidationIssue(
                        severidad="warning",
                        hoja="Ventas",
                        fila=idx,
                        codigo="FECHA_OPERACION_NO_FESTIVA",
                        mensaje=(
                            f"La fecha {fecha.isoformat()} ({w_name}) no es sábado, "
                            "domingo ni festivo nacional oficial de Colombia. "
                            "Se conserva con marca de alerta en observaciones."
                        ),
                    )
                )

            parsed_ventas.append(
                ParsedVentaRow(
                    row_number=idx,
                    fecha=fecha,
                    producto=producto,
                    presentacion_unidad=presentacion_unidad,
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    total_venta=total_venta,
                    es_sintetico=es_sintetico,
                    alerta_calendario=alerta_calendario,
                )
            )

        sheet_summaries.append(
            ExcelSheetSummary(
                hoja="Ventas",
                filas_totales_con_encabezado=len(ventas_rows) + 1,
                filas_vacias_ignoradas=ventas_empty,
                registros_validos=len(parsed_ventas),
                registros_reales=sum(1 for r in parsed_ventas if not r.es_sintetico),
                registros_sinteticos=sum(1 for r in parsed_ventas if r.es_sintetico),
            )
        )

        # 3. Hoja Pedidos
        ws_pedidos = wb["Pedidos"]
        pedidos_rows = list(ws_pedidos.iter_rows(min_row=2, values_only=True))
        parsed_pedidos: list[ParsedPedidoRow] = []
        pedidos_empty = 0

        for idx, row in enumerate(pedidos_rows, start=2):
            if not any(cell is not None for cell in row):
                pedidos_empty += 1
                advertencias.append(
                    ExcelValidationIssue(
                        severidad="warning",
                        hoja="Pedidos",
                        fila=idx,
                        codigo="FILA_VACIA_IGNORADA",
                        mensaje=f"La fila {idx} de Pedidos está completamente vacía y será ignorada.",
                    )
                )
                continue
            if _is_summary_row(row):
                pedidos_empty += 1
                continue

            fecha_pedido = _coerce_date(row[0])
            fecha_entrega = _coerce_date(row[1])
            cliente = str(row[2] or "").strip()
            producto = str(row[3] or "").strip()
            cantidad = int(row[4] or 0)
            estado_raw = str(row[5] or "").strip().lower()

            if fecha_pedido is None or fecha_entrega is None:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Pedidos",
                        fila=idx,
                        codigo="FECHA_PEDIDO_INVALIDA",
                        mensaje="Fecha del pedido o fecha de entrega inválida.",
                    )
                )
                continue

            if fecha_entrega < fecha_pedido:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Pedidos",
                        fila=idx,
                        codigo="ENTREGA_ANTERIOR_A_PEDIDO",
                        mensaje="La fecha de entrega es anterior a la fecha del pedido.",
                    )
                )
                continue

            if not cliente:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Pedidos",
                        fila=idx,
                        codigo="CLIENTE_VACIO",
                        mensaje="El nombre del cliente no puede estar vacío.",
                    )
                )
                continue

            if producto not in catalog_products:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Pedidos",
                        fila=idx,
                        codigo="PRODUCTO_INEXISTENTE",
                        mensaje=f"Producto '{producto}' no existe en el catálogo.",
                    )
                )
                continue

            if cantidad <= 0:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Pedidos",
                        fila=idx,
                        codigo="CANTIDAD_PEDIDO_INVALIDA",
                        mensaje="La cantidad del pedido debe ser mayor que cero.",
                    )
                )
                continue

            estado_db = _ESTADO_PEDIDO_MAP.get(estado_raw)
            if estado_db is None:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Pedidos",
                        fila=idx,
                        codigo="ESTADO_PEDIDO_INVALIDO",
                        mensaje=f"El estado '{row[5]}' no es válido.",
                    )
                )
                continue

            es_sintetico = fecha_entrega < cutoff_date
            alerta_calendario = None
            if not is_valid_operation_date(fecha_entrega):
                weekday_names = (
                    "lunes",
                    "martes",
                    "miercoles",
                    "jueves",
                    "viernes",
                    "sabado",
                    "domingo",
                )
                w_name = weekday_names[fecha_entrega.weekday()]
                alerta_calendario = f"{fecha_entrega.isoformat()}_{w_name}_no_festivo"
                advertencias.append(
                    ExcelValidationIssue(
                        severidad="warning",
                        hoja="Pedidos",
                        fila=idx,
                        codigo="FECHA_ENTREGA_NO_FESTIVA",
                        mensaje=(
                            f"La fecha de entrega {fecha_entrega.isoformat()} ({w_name}) "
                            "no es sábado, domingo ni festivo nacional oficial."
                        ),
                    )
                )

            parsed_pedidos.append(
                ParsedPedidoRow(
                    row_number=idx,
                    fecha_pedido=fecha_pedido,
                    fecha_entrega=fecha_entrega,
                    cliente=cliente,
                    producto=producto,
                    cantidad=cantidad,
                    estado_db=estado_db,
                    es_sintetico=es_sintetico,
                    alerta_calendario=alerta_calendario,
                )
            )

        sheet_summaries.append(
            ExcelSheetSummary(
                hoja="Pedidos",
                filas_totales_con_encabezado=len(pedidos_rows) + 1,
                filas_vacias_ignoradas=pedidos_empty,
                registros_validos=len(parsed_pedidos),
                registros_reales=sum(1 for r in parsed_pedidos if not r.es_sintetico),
                registros_sinteticos=sum(1 for r in parsed_pedidos if r.es_sintetico),
            )
        )

        # 4. Hoja Produccion y 5. Hoja Sobrantes
        ws_produccion = wb["Produccion"]
        prod_sheet_rows = list(ws_produccion.iter_rows(min_row=2, values_only=True))
        ws_sobrantes = wb["Sobrantes"]
        sob_sheet_rows = list(ws_sobrantes.iter_rows(min_row=2, values_only=True))

        sobrantes_map: dict[tuple[date, str], tuple[int, int, int]] = {}
        sob_empty = 0
        sob_real = 0
        sob_syn = 0
        for idx, row in enumerate(sob_sheet_rows, start=2):
            if not any(cell is not None for cell in row):
                sob_empty += 1
                continue
            fecha = _coerce_date(row[0])
            producto = str(row[1] or "").strip()
            produccion_val = int(row[2] or 0)
            sobrante_val = int(row[3] or 0)
            if fecha is not None and producto:
                sobrantes_map[(fecha, producto)] = (idx, produccion_val, sobrante_val)
                if fecha < cutoff_date:
                    sob_syn += 1
                else:
                    sob_real += 1

        ventas_qty_map = {(v.fecha, v.producto): v.cantidad for v in parsed_ventas}
        parsed_producciones: list[ParsedProduccionRow] = []
        produccion_empty = 0

        for idx, row in enumerate(prod_sheet_rows, start=2):
            if not any(cell is not None for cell in row):
                produccion_empty += 1
                continue
            fecha = _coerce_date(row[0])
            producto = str(row[1] or "").strip()
            ventas_col = int(row[2] or 0)
            sobrantes_col = int(row[3] or 0)
            produccion_col = int(row[4] or 0)

            if fecha is None or producto not in catalog_products:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Produccion",
                        fila=idx,
                        codigo="DATOS_PRODUCCION_INVALIDOS",
                        mensaje="Fecha o producto inválido en hoja Produccion.",
                    )
                )
                continue

            # Regla fundamental: Producción = Ventas + Sobrantes
            if ventas_col + sobrantes_col != produccion_col:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Produccion",
                        fila=idx,
                        codigo="REGLA_PRODUCCION_INCUMPLIDA",
                        mensaje=(
                            f"En {fecha.isoformat()} ({producto}): "
                            f"Ventas ({ventas_col}) + Sobrantes ({sobrantes_col}) "
                            f"!= Producción ({produccion_col})."
                        ),
                    )
                )
                continue

            if ventas_qty_map.get((fecha, producto)) != ventas_col:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Produccion",
                        fila=idx,
                        codigo="DESFASE_VENTAS_PRODUCCION",
                        mensaje=(
                            f"Las ventas en hoja Produccion ({ventas_col}) no coinciden "
                            f"con la hoja Ventas ({ventas_qty_map.get((fecha, producto))})."
                        ),
                    )
                )
                continue

            sob_entry = sobrantes_map.get((fecha, producto))
            if sob_entry is None or sob_entry[1] != produccion_col or sob_entry[2] != sobrantes_col:
                errores.append(
                    ExcelValidationIssue(
                        severidad="error",
                        hoja="Produccion",
                        fila=idx,
                        codigo="DESFASE_HOJA_SOBRANTES",
                        mensaje=(
                            f"Los datos de Produccion para ({fecha.isoformat()}, {producto}) "
                            "no coinciden con la hoja Sobrantes."
                        ),
                    )
                )
                continue

            es_sintetico = fecha < cutoff_date
            alerta_calendario = None
            if not is_valid_operation_date(fecha):
                weekday_names = (
                    "lunes",
                    "martes",
                    "miercoles",
                    "jueves",
                    "viernes",
                    "sabado",
                    "domingo",
                )
                w_name = weekday_names[fecha.weekday()]
                alerta_calendario = f"{fecha.isoformat()}_{w_name}_no_festivo"

            parsed_producciones.append(
                ParsedProduccionRow(
                    row_number=idx,
                    fecha=fecha,
                    producto=producto,
                    ventas=ventas_col,
                    sobrantes=sobrantes_col,
                    produccion=produccion_col,
                    es_sintetico=es_sintetico,
                    alerta_calendario=alerta_calendario,
                )
            )

        sheet_summaries.append(
            ExcelSheetSummary(
                hoja="Produccion",
                filas_totales_con_encabezado=len(prod_sheet_rows) + 1,
                filas_vacias_ignoradas=produccion_empty,
                registros_validos=len(parsed_producciones),
                registros_reales=sum(1 for r in parsed_producciones if not r.es_sintetico),
                registros_sinteticos=sum(1 for r in parsed_producciones if r.es_sintetico),
            )
        )
        sheet_summaries.append(
            ExcelSheetSummary(
                hoja="Sobrantes",
                filas_totales_con_encabezado=len(sob_sheet_rows) + 1,
                filas_vacias_ignoradas=sob_empty,
                registros_validos=len(sobrantes_map),
                registros_reales=sob_real,
                registros_sinteticos=sob_syn,
            )
        )

        fechas_op = sorted({v.fecha for v in parsed_ventas})
        clientes_reales = {p.cliente for p in parsed_pedidos if not p.es_sintetico}
        clientes_sinteticos = {p.cliente for p in parsed_pedidos if p.es_sintetico}
        total_real_cop = sum(
            (v.total_venta for v in parsed_ventas if not v.es_sintetico),
            Decimal("0.00"),
        )
        total_syn_cop = sum(
            (v.total_venta for v in parsed_ventas if v.es_sintetico),
            Decimal("0.00"),
        )

        report = ExcelAuditReport(
            archivo=path.name,
            valido_para_importar=len(errores) == 0,
            fecha_corte_real=cutoff_date,
            fecha_minima_operacion=fechas_op[0] if fechas_op else None,
            fecha_maxima_operacion=fechas_op[-1] if fechas_op else None,
            total_fechas_operacion=len(fechas_op),
            total_clientes_unicos=len(clientes_reales | clientes_sinteticos),
            clientes_reales=len(clientes_reales),
            clientes_sinteticos=len(clientes_sinteticos),
            total_ventas_cop=total_real_cop + total_syn_cop,
            total_ventas_reales_cop=total_real_cop,
            total_ventas_sinteticas_cop=total_syn_cop,
            hojas=sheet_summaries,
            advertencias=advertencias,
            errores=errores,
        )
        return ParsedWorkbookData(
            report=report,
            ventas=parsed_ventas,
            pedidos=parsed_pedidos,
            producciones=parsed_producciones,
        )
    finally:
        wb.close()


def validate_excel_workbook(
    excel_path: str | Path,
    *,
    cutoff_date: date = REAL_DATA_CUTOFF_DATE,
) -> ExcelAuditReport:
    """Devuelve únicamente el reporte de auditoría y validación previa del archivo Excel."""
    return parse_and_validate_workbook(excel_path, cutoff_date=cutoff_date).report


def import_excel_workbook(
    session: Session,
    excel_path: str | Path,
    *,
    dry_run: bool = False,
    cutoff_date: date = REAL_DATA_CUTOFF_DATE,
) -> ExcelImportResult:
    """Importa de forma idempotente y transaccional los datos históricos del Excel a MySQL."""
    parsed = parse_and_validate_workbook(excel_path, cutoff_date=cutoff_date)
    if not parsed.report.valido_para_importar:
        error_msgs = "; ".join(e.mensaje for e in parsed.report.errores[:5])
        raise ValueError(
            f"El archivo Excel contiene errores de validación y no puede importarse: {error_msgs}"
        )

    counters: dict[str, TableImportCounter] = {
        name: TableImportCounter()
        for name in (
            "productos",
            "presentaciones",
            "clientes",
            "pedidos",
            "detalle_pedidos",
            "ventas",
            "detalle_ventas",
            "producciones",
            "cierres_diarios",
            "movimientos_inventario",
        )
    }

    savepoint = session.begin_nested() if dry_run else None
    try:
        # 1. Catálogo base (productos y presentaciones)
        seed_res = seed_initial_catalog(session, commit=False)
        counters["productos"].creados = len(seed_res.productos_creados)
        counters["productos"].existentes = len(seed_res.productos_existentes)
        counters["productos"].reales_creados = len(seed_res.productos_creados)
        counters["presentaciones"].creados = len(seed_res.presentaciones_creadas)
        counters["presentaciones"].existentes = len(seed_res.presentaciones_existentes)
        counters["presentaciones"].reales_creados = len(seed_res.presentaciones_creadas)

        productos_by_name = {
            p.nombre: p for p in session.scalars(select(Producto)).all()
        }
        presentaciones_by_prod_id = {
            pr.producto_id: pr
            for pr in session.scalars(
                select(Presentacion).where(Presentacion.nombre == "individual")
            ).all()
        }

        # 2. Clientes únicos (extraídos de Pedidos)
        existing_clients = {
            c.nombre: c for c in session.scalars(select(Cliente)).all()
        }
        first_seen_clients: dict[str, tuple[int, bool]] = {}
        for ped in parsed.pedidos:
            if ped.cliente not in first_seen_clients:
                first_seen_clients[ped.cliente] = (ped.row_number, ped.es_sintetico)

        for nombre_cliente, (first_row, es_sintetico) in first_seen_clients.items():
            if nombre_cliente in existing_clients:
                counters["clientes"].existentes += 1
                continue
            nuevo_cliente = Cliente(
                nombre=nombre_cliente,
                telefono=None,
                correo=None,
                notas=build_trace_tag(
                    hoja="Pedidos", fila=first_row, es_sintetico=es_sintetico
                ),
                activo=True,
            )
            session.add(nuevo_cliente)
            existing_clients[nombre_cliente] = nuevo_cliente
            counters["clientes"].creados += 1
            if es_sintetico:
                counters["clientes"].sinteticos_creados += 1
            else:
                counters["clientes"].reales_creados += 1

        session.flush()

        # 3. Pedidos y DetallePedido (1:1 por fila válida de Pedidos)
        existing_pedido_traces = set(
            session.scalars(
                select(Pedido.observaciones).where(
                    Pedido.observaciones.is_not(None)
                )
            ).all()
        )
        for ped_row in parsed.pedidos:
            trace = build_trace_tag(
                hoja="Pedidos",
                fila=ped_row.row_number,
                es_sintetico=ped_row.es_sintetico,
                alerta_calendario=ped_row.alerta_calendario,
            )
            row_marker = f"|hoja=Pedidos|fila={ped_row.row_number}"
            if any(row_marker in obs for obs in existing_pedido_traces if obs):
                counters["pedidos"].existentes += 1
                counters["detalle_pedidos"].existentes += 1
                continue

            cliente_obj = existing_clients[ped_row.cliente]
            prod_obj = productos_by_name[ped_row.producto]
            pres_obj = presentaciones_by_prod_id[prod_obj.id]

            pedido = Pedido(
                cliente_id=cliente_obj.id,
                fecha_pedido=datetime.combine(ped_row.fecha_pedido, datetime.min.time()),
                fecha_entrega_prevista=datetime.combine(
                    ped_row.fecha_entrega, datetime.min.time()
                ),
                estado=ped_row.estado_db,
                nombre_contacto=None,
                telefono_contacto=None,
                direccion_entrega=None,
                observaciones=trace,
            )
            session.add(pedido)
            session.flush()

            detalle_pedido = DetallePedido(
                pedido_id=pedido.id,
                presentacion_id=pres_obj.id,
                cantidad=Decimal(ped_row.cantidad),
                precio_unitario=Decimal(pres_obj.precio_actual),
                factor_conversion_snapshot=Decimal(pres_obj.factor_conversion),
                observaciones=trace,
            )
            session.add(detalle_pedido)
            existing_pedido_traces.add(trace)

            counters["pedidos"].creados += 1
            counters["detalle_pedidos"].creados += 1
            if ped_row.es_sintetico:
                counters["pedidos"].sinteticos_creados += 1
                counters["detalle_pedidos"].sinteticos_creados += 1
            else:
                counters["pedidos"].reales_creados += 1
                counters["detalle_pedidos"].reales_creados += 1

        session.flush()

        # 4. Producciones, Cierres Diarios y Movimientos de Inventario (tipo='produccion')
        existing_prod_by_key = {
            (p.fecha_produccion.date(), p.producto_id): p
            for p in session.scalars(select(Produccion)).all()
        }
        existing_cierre_keys = {
            (c.fecha, c.producto_id)
            for c in session.scalars(select(CierreDiario)).all()
        }
        existing_mov_prod_ids = set(
            session.scalars(
                select(MovimientoInventario.produccion_id).where(
                    MovimientoInventario.produccion_id.is_not(None)
                )
            ).all()
        )

        for prod_row in parsed.producciones:
            prod_obj = productos_by_name[prod_row.producto]
            trace = build_trace_tag(
                hoja="Produccion",
                fila=prod_row.row_number,
                es_sintetico=prod_row.es_sintetico,
                alerta_calendario=prod_row.alerta_calendario,
            )
            prod_key = (prod_row.fecha, prod_obj.id)
            produccion_entity = existing_prod_by_key.get(prod_key)

            if produccion_entity is None:
                produccion_entity = Produccion(
                    producto_id=prod_obj.id,
                    fecha_produccion=datetime.combine(
                        prod_row.fecha, datetime.min.time()
                    ),
                    cantidad_producida_base=Decimal(prod_row.produccion),
                    observaciones=trace,
                )
                session.add(produccion_entity)
                session.flush()
                existing_prod_by_key[prod_key] = produccion_entity
                counters["producciones"].creados += 1
                if prod_row.es_sintetico:
                    counters["producciones"].sinteticos_creados += 1
                else:
                    counters["producciones"].reales_creados += 1
            else:
                counters["producciones"].existentes += 1

            # Cierre diario (existencia_calculada_base = Producción - Ventas = Sobrantes)
            if prod_key not in existing_cierre_keys:
                existencia_calculada = Decimal(prod_row.produccion - prod_row.ventas)
                cierre = CierreDiario(
                    producto_id=prod_obj.id,
                    fecha=prod_row.fecha,
                    existencia_calculada_base=existencia_calculada,
                    sobrante_real_base=Decimal(prod_row.sobrantes),
                    observaciones=trace,
                    usuario_id=None,
                )
                session.add(cierre)
                existing_cierre_keys.add(prod_key)
                counters["cierres_diarios"].creados += 1
                if prod_row.es_sintetico:
                    counters["cierres_diarios"].sinteticos_creados += 1
                else:
                    counters["cierres_diarios"].reales_creados += 1
            else:
                counters["cierres_diarios"].existentes += 1

            # Movimiento de inventario por entrada de producción
            if produccion_entity.id not in existing_mov_prod_ids:
                mov_prod = MovimientoInventario(
                    producto_id=prod_obj.id,
                    produccion_id=produccion_entity.id,
                    detalle_venta_id=None,
                    tipo="produccion",
                    fecha_movimiento=datetime.combine(
                        prod_row.fecha, datetime.min.time()
                    ),
                    cantidad_base=Decimal(prod_row.produccion),
                    observaciones=trace,
                )
                session.add(mov_prod)
                existing_mov_prod_ids.add(produccion_entity.id)
                counters["movimientos_inventario"].creados += 1
                if prod_row.es_sintetico:
                    counters["movimientos_inventario"].sinteticos_creados += 1
                else:
                    counters["movimientos_inventario"].reales_creados += 1
            else:
                counters["movimientos_inventario"].existentes += 1

        session.flush()

        # 5. Ventas, DetalleVenta (1:1) y Movimientos de Inventario (tipo='venta')
        existing_venta_traces = set(
            session.scalars(
                select(Venta.observaciones).where(Venta.observaciones.is_not(None))
            ).all()
        )
        for v_row in parsed.ventas:
            trace = build_trace_tag(
                hoja="Ventas",
                fila=v_row.row_number,
                es_sintetico=v_row.es_sintetico,
                alerta_calendario=v_row.alerta_calendario,
            )
            row_marker = f"|hoja=Ventas|fila={v_row.row_number}"
            if any(row_marker in obs for obs in existing_venta_traces if obs):
                counters["ventas"].existentes += 1
                counters["detalle_ventas"].existentes += 1
                counters["movimientos_inventario"].existentes += 1
                continue

            prod_obj = productos_by_name[v_row.producto]
            pres_obj = presentaciones_by_prod_id[prod_obj.id]
            fecha_dt = datetime.combine(v_row.fecha, datetime.min.time())

            venta = Venta(
                pedido_id=None,
                fecha_venta=fecha_dt,
                estado="concretada",
                observaciones=trace,
            )
            session.add(venta)
            session.flush()

            detalle_venta = DetalleVenta(
                venta_id=venta.id,
                presentacion_id=pres_obj.id,
                cantidad=Decimal(v_row.cantidad),
                precio_unitario=v_row.precio_unitario,
                factor_conversion_snapshot=Decimal(pres_obj.factor_conversion),
            )
            session.add(detalle_venta)
            session.flush()

            mov_venta = MovimientoInventario(
                producto_id=prod_obj.id,
                produccion_id=None,
                detalle_venta_id=detalle_venta.id,
                tipo="venta",
                fecha_movimiento=fecha_dt,
                cantidad_base=Decimal(v_row.cantidad)
                * Decimal(pres_obj.factor_conversion),
                observaciones=trace,
            )
            session.add(mov_venta)
            existing_venta_traces.add(trace)

            counters["ventas"].creados += 1
            counters["detalle_ventas"].creados += 1
            counters["movimientos_inventario"].creados += 1
            if v_row.es_sintetico:
                counters["ventas"].sinteticos_creados += 1
                counters["detalle_ventas"].sinteticos_creados += 1
                counters["movimientos_inventario"].sinteticos_creados += 1
            else:
                counters["ventas"].reales_creados += 1
                counters["detalle_ventas"].reales_creados += 1
                counters["movimientos_inventario"].reales_creados += 1

        if dry_run and savepoint is not None:
            savepoint.rollback()
        else:
            session.commit()

        return ExcelImportResult(
            archivo=parsed.report.archivo,
            dry_run=dry_run,
            fecha_corte_real=cutoff_date,
            tablas=counters,
            advertencias=parsed.report.advertencias,
        )
    except Exception:
        if savepoint is not None and savepoint.is_active:
            savepoint.rollback()
        else:
            session.rollback()
        raise


def _cli() -> None:
    import argparse
    import json

    from app.db.session import get_engine

    parser = argparse.ArgumentParser(
        description="Valida e importa de forma idempotente el archivo Excel histórico a MySQL."
    )
    parser.add_argument("excel_path", help="Ruta al archivo .xlsx histórico.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Solo ejecuta la auditoría y validación previa sin conectar a MySQL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecuta la importación dentro de un SAVEPOINT y revierte todos los cambios al final.",
    )
    args = parser.parse_args()

    if args.validate_only:
        report = validate_excel_workbook(args.excel_path)
        print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return

    engine = get_engine()
    with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
        result = import_excel_workbook(session, args.excel_path, dry_run=args.dry_run)
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
