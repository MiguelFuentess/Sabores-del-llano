from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import io
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import DetalleVenta, Presentacion, Producto, Venta
from app.services import production as production_service
from app.services import sales as sales_service

try:
    COLOMBIA_TZ: timezone | ZoneInfo = ZoneInfo("America/Bogota")
except ZoneInfoNotFoundError:
    COLOMBIA_TZ = timezone(timedelta(hours=-5))

_TRACE_TAG_RE = re.compile(r"\[IMPORTACION_EXCEL\|[^\]]+\]")

_PRODUCT_ALIASES = {
    "hayaca": "Hayaca",
    "hayacas": "Hayaca",
    "hayacas-individual": "Hayaca",
    "lechona": "Lechona",
    "lechona-personal": "Lechona",
}

_PRODUCT_DISPLAY = {
    "Hayaca": "Hayacas",
    "Lechona": "Lechona",
}

_PRODUCT_FILE_SLUG = {
    "Hayaca": "hayacas",
    "Lechona": "lechona",
}

_SPANISH_MONTH_ABBR = (
    "",
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)

_PEDIDO_ESTADO_LABELS = {
    "pendiente": "Pendiente",
    "confirmado": "Confirmado",
    "en_preparacion": "En preparación",
    "entregado": "Entregado",
    "cancelado": "Cancelado",
}

# Estilos visuales legibles para Excel
_TITLE_FILL = PatternFill(fill_type="solid", fgColor="2A5537")
_TITLE_FONT = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
_META_FILL = PatternFill(fill_type="solid", fgColor="FAF8F5")
_META_LABEL_FONT = Font(name="Calibri", size=10, bold=True, color="463F38")
_META_VALUE_FONT = Font(name="Calibri", size=10, bold=False, color="1E1C1A")
_HEADER_FILL = PatternFill(fill_type="solid", fgColor="3B332B")
_HEADER_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
_ROW_ALT_FILL = PatternFill(fill_type="solid", fgColor="FCF9F5")
_ROW_WHITE_FILL = PatternFill(fill_type="solid", fgColor="FFFFFF")
_DATA_FONT = Font(name="Calibri", size=10, color="1E1C1A")
_TOTAL_FILL = PatternFill(fill_type="solid", fgColor="F3EDE4")
_TOTAL_FONT = Font(name="Calibri", size=10, bold=True, color="1E1C1A")

_THIN_SIDE = Side(style="thin", color="E0D7C6")
_MEDIUM_TOP_SIDE = Side(style="medium", color="8C7B6B")
_CELL_BORDER = Border(
    left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE
)
_TOTAL_BORDER = Border(
    left=_THIN_SIDE,
    right=_THIN_SIDE,
    top=_MEDIUM_TOP_SIDE,
    bottom=_MEDIUM_TOP_SIDE,
)


def _now_colombia() -> datetime:
    return datetime.now(COLOMBIA_TZ)


def _strip_trace_tags(value: str | None) -> str:
    if not value:
        return ""
    return _TRACE_TAG_RE.sub("", str(value)).strip()


def _sanitize_excel_text(value: str | None) -> str:
    cleaned = _strip_trace_tags(value)
    if cleaned and cleaned[0] in ("=", "+", "-", "@"):
        return f"'{cleaned}"
    return cleaned


def _display_product_name(nombre: str | None) -> str:
    if not nombre:
        return "Producto"
    return _PRODUCT_DISPLAY.get(nombre, nombre)


def _display_unit_plural(unidad_base: str | None) -> str:
    base = (unidad_base or "").strip().lower()
    if base == "plato":
        return "platos"
    if base == "unidad":
        return "unidades"
    return base or "unidades"


def _canonical_product_name(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip()
    return _PRODUCT_ALIASES.get(cleaned.lower(), cleaned)


def _resolve_period_bounds_and_label(
    *,
    periodo: str | None,
    fecha_desde: date | None,
    fecha_hasta: date | None,
    today: date,
) -> tuple[date | None, date | None, str]:
    eff_desde = fecha_desde
    eff_hasta = fecha_hasta
    norm_period = (periodo or "").strip().lower()

    if eff_desde is None and eff_hasta is None:
        if norm_period == "month":
            eff_desde = date(today.year, today.month, 1)
            eff_hasta = today
        elif norm_period == "15days":
            eff_desde = today - timedelta(days=14)
            eff_hasta = today
        elif norm_period == "week":
            weekday = today.weekday()  # 0=Lunes..6=Domingo
            eff_desde = today - timedelta(days=weekday)
            eff_hasta = eff_desde + timedelta(days=6)

    if eff_desde and eff_hasta and eff_desde > eff_hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La fecha inicial del filtro no puede ser posterior a la fecha final.",
        )

    period_names = {
        "all": "Todo el historial",
        "week": "Esta semana",
        "15days": "Últimos 15 días",
        "month": "Este mes",
    }
    base_label = period_names.get(norm_period, "")
    if eff_desde and eff_hasta:
        range_str = f"{eff_desde.isoformat()} a {eff_hasta.isoformat()}"
        label = f"{base_label} ({range_str})" if base_label else range_str
    elif eff_desde:
        label = f"Desde {eff_desde.isoformat()}"
    elif eff_hasta:
        label = f"Hasta {eff_hasta.isoformat()}"
    else:
        label = base_label or "Todo el historial"

    return eff_desde, eff_hasta, label


def _decimal_to_excel_money(value: Decimal) -> int | float:
    quant = Decimal(value).quantize(Decimal("0.01"))
    if quant == quant.to_integral_value():
        return int(quant)
    return float(quant)


def _money_format_for_value(value: int | float) -> str:
    return "$#,##0" if isinstance(value, int) else "$#,##0.00"


def _autofit_columns(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    *,
    header_row: int,
    min_widths: dict[int, int] | None = None,
    max_width: int = 46,
) -> None:
    min_map = min_widths or {}
    for col_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(col_idx)
        longest = min_map.get(col_idx, 12)
        for row_idx in range(header_row, ws.max_row + 1):
            cell_val = ws.cell(row=row_idx, column=col_idx).value
            if cell_val is None:
                continue
            if isinstance(cell_val, date):
                text_len = 12
            elif isinstance(cell_val, float):
                text_len = 12
            elif isinstance(cell_val, int):
                text_len = len(f"{cell_val:,}") + 4
            else:
                text_len = len(str(cell_val)) + 3
            if text_len > longest:
                longest = text_len
        ws.column_dimensions[col_letter].width = min(max_width, longest)


def generate_production_report_xlsx(
    session: Session,
    *,
    producto_id: int | None = None,
    producto_nombre: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    periodo: str | None = None,
    incluir_historicos: bool = True,
    incluir_sinteticos: bool = True,
    solo_operativos: bool = False,
) -> tuple[bytes, str]:
    now_co = _now_colombia()
    eff_desde, eff_hasta, periodo_label = _resolve_period_bounds_and_label(
        periodo=periodo,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        today=now_co.date(),
    )
    canonical_prod = _canonical_product_name(producto_nombre)

    records = production_service.list_producciones(
        session,
        producto_id=producto_id,
        producto_nombre=canonical_prod,
        fecha_desde=eff_desde,
        fecha_hasta=eff_hasta,
        incluir_historicos=incluir_historicos,
        incluir_sinteticos=incluir_sinteticos,
        solo_operativos=solo_operativos,
        limit=100_000,
        offset=0,
    )

    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay registros de producción para los filtros seleccionados.",
        )

    # Totales separados por producto respetando unidades base (Hayacas: unidades, Lechona: platos)
    # y deduplicando métricas diarias por (producto_id, fecha_jornada)
    stats_by_prod: dict[str, dict[str, int]] = {}
    seen_daily_keys: set[tuple[int, date]] = set()

    for rec in records:
        pname = rec.producto_nombre
        bucket = stats_by_prod.setdefault(
            pname,
            {
                "producido": 0,
                "vendido": 0,
                "sobrantes": 0,
                "existencia": 0,
                "diferencia": 0,
            },
        )
        prod_qty = int(round(float(rec.cantidad_producida_base)))
        bucket["producido"] += prod_qty

        daily_key = (rec.producto_id, rec.fecha_jornada)
        if daily_key not in seen_daily_keys:
            seen_daily_keys.add(daily_key)
            bucket["vendido"] += int(round(float(rec.cantidad_vendida_fecha)))
            bucket["sobrantes"] += int(round(float(rec.sobrante_real_base)))
            bucket["existencia"] += int(
                round(float(rec.existencia_calculada_base))
            )
            bucket["diferencia"] += int(round(float(rec.diferencia_base)))

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Producción y Balance"
    wb.properties.creator = "Sabores del Llano"
    wb.properties.title = "Reporte de Producción y Balance de Ventas"

    total_cols = 10
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    title_cell = ws.cell(
        row=1,
        column=1,
        value="SABORES DEL LLANO — HISTORIAL DE PRODUCCIÓN Y BALANCE DE VENTAS",
    )
    title_cell.font = _TITLE_FONT
    title_cell.fill = _TITLE_FILL
    title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    prod_filter_label = (
        f"{_display_product_name(records[0].producto_nombre)} "
        f"({_display_unit_plural(records[0].unidad_base)})"
        if (producto_id is not None or canonical_prod is not None)
        else "Todos los productos (Hayacas en unidades · Lechona en platos)"
    )

    hayaca_stats = stats_by_prod.get("Hayaca")
    lechona_stats = stats_by_prod.get("Lechona")
    hayaca_summary = (
        f"Producido: {hayaca_stats['producido']:,} unidades · "
        f"Vendido: {hayaca_stats['vendido']:,} unidades · "
        f"Sobrantes: {hayaca_stats['sobrantes']:,} unidades · "
        f"Existencia calculada: {hayaca_stats['existencia']:,} unidades"
        if hayaca_stats
        else "Sin registros en el filtro actual"
    )
    lechona_summary = (
        f"Producido: {lechona_stats['producido']:,} platos · "
        f"Vendido: {lechona_stats['vendido']:,} platos · "
        f"Sobrantes: {lechona_stats['sobrantes']:,} platos · "
        f"Existencia calculada: {lechona_stats['existencia']:,} platos"
        if lechona_stats
        else "Sin registros en el filtro actual"
    )

    meta_rows = [
        (
            "Fecha de generación:",
            now_co.strftime("%Y-%m-%d %H:%M"),
            "Período consultado:",
            periodo_label,
        ),
        (
            "Filtro de producto:",
            prod_filter_label,
            "Registros exportados:",
            len(records),
        ),
        ("Balance Hayacas:", hayaca_summary, "", ""),
        ("Balance Lechona:", lechona_summary, "", ""),
    ]

    for offset_idx, (lbl1, val1, lbl2, val2) in enumerate(meta_rows, start=2):
        ws.row_dimensions[offset_idx].height = 20
        for c_idx in range(1, total_cols + 1):
            cell = ws.cell(row=offset_idx, column=c_idx)
            cell.fill = _META_FILL
            cell.border = _CELL_BORDER
        c_lbl1 = ws.cell(row=offset_idx, column=1, value=lbl1)
        c_lbl1.font = _META_LABEL_FONT
        if lbl2:
            ws.merge_cells(
                start_row=offset_idx, start_column=2, end_row=offset_idx, end_column=5
            )
            c_val1 = ws.cell(row=offset_idx, column=2, value=val1)
            c_val1.font = _META_VALUE_FONT
            c_lbl2 = ws.cell(row=offset_idx, column=6, value=lbl2)
            c_lbl2.font = _META_LABEL_FONT
            ws.merge_cells(
                start_row=offset_idx,
                start_column=7,
                end_row=offset_idx,
                end_column=total_cols,
            )
            c_val2 = ws.cell(row=offset_idx, column=7, value=val2)
            c_val2.font = _META_VALUE_FONT
            c_val2.alignment = Alignment(horizontal="left", vertical="center")
        else:
            ws.merge_cells(
                start_row=offset_idx,
                start_column=2,
                end_row=offset_idx,
                end_column=total_cols,
            )
            c_val1 = ws.cell(row=offset_idx, column=2, value=val1)
            c_val1.font = _META_VALUE_FONT

    header_row = 7
    headers = [
        "Fecha",
        "Producto",
        "Unidad base",
        "Cantidad producida",
        "Cantidad vendida",
        "Sobrantes",
        "Existencia calculada (balance)",
        "Diferencia de balance",
        "Rendimiento de venta",
        "Observaciones",
    ]
    ws.row_dimensions[header_row].height = 26
    for col_idx, h_text in enumerate(headers, start=1):
        h_cell = ws.cell(row=header_row, column=col_idx, value=h_text)
        h_cell.font = _HEADER_FONT
        h_cell.fill = _HEADER_FILL
        h_cell.border = _CELL_BORDER
        h_cell.alignment = Alignment(
            horizontal="center" if col_idx in (1, 3) else ("right" if 4 <= col_idx <= 9 else "left"),
            vertical="center",
            wrap_text=True,
        )

    ws.freeze_panes = f"A{header_row + 1}"

    current_row = header_row + 1
    for idx, rec in enumerate(records):
        fill = _ROW_ALT_FILL if idx % 2 == 1 else _ROW_WHITE_FILL
        producida = int(round(float(rec.cantidad_producida_base)))
        vendida = int(round(float(rec.cantidad_vendida_fecha)))
        sobrantes = int(round(float(rec.sobrante_real_base)))
        existencia = int(round(float(rec.existencia_calculada_base)))
        diferencia = int(round(float(rec.diferencia_base)))
        rendimiento: float | str = (vendida / producida) if producida > 0 else "—"
        obs_clean = _sanitize_excel_text(rec.observaciones)

        row_values: list[object] = [
            rec.fecha_jornada,
            _display_product_name(rec.producto_nombre),
            _display_unit_plural(rec.unidad_base),
            producida,
            vendida,
            sobrantes,
            existencia,
            diferencia,
            rendimiento,
            obs_clean,
        ]
        ws.row_dimensions[current_row].height = 20
        for col_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = _DATA_FONT
            cell.fill = fill
            cell.border = _CELL_BORDER
            if col_idx == 1:
                cell.number_format = "yyyy-mm-dd"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 3:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in (4, 5, 6, 7):
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx == 8:
                cell.number_format = "+#,##0;-#,##0;0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx == 9:
                if isinstance(val, float):
                    cell.number_format = "0.0%"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        current_row += 1

    # Filas de totales por producto respetando unidades base
    for prod_key, unit_label in (("Hayaca", "unidades"), ("Lechona", "platos")):
        st = stats_by_prod.get(prod_key)
        if not st:
            continue
        disp_name = _display_product_name(prod_key)
        rend_tot: float | str = (
            (st["vendido"] / st["producido"]) if st["producido"] > 0 else "—"
        )
        tot_values: list[object] = [
            f"Total {disp_name}",
            disp_name,
            unit_label,
            st["producido"],
            st["vendido"],
            st["sobrantes"],
            st["existencia"],
            st["diferencia"],
            rend_tot,
            "",
        ]
        ws.row_dimensions[current_row].height = 22
        for col_idx, val in enumerate(tot_values, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = _TOTAL_FONT
            cell.fill = _TOTAL_FILL
            cell.border = _TOTAL_BORDER
            if col_idx == 3:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in (4, 5, 6, 7):
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx == 8:
                cell.number_format = "+#,##0;-#,##0;0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx == 9:
                if isinstance(val, float):
                    cell.number_format = "0.0%"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        current_row += 1

    _autofit_columns(
        ws,
        header_row=header_row,
        min_widths={1: 14, 2: 14, 3: 13, 4: 18, 5: 17, 6: 13, 7: 24, 8: 19, 9: 18, 10: 24},
    )

    slug = (
        f"_{_PRODUCT_FILE_SLUG.get(records[0].producto_nombre, 'producto')}"
        if (producto_id is not None or canonical_prod is not None)
        else ""
    )
    filename = f"reporte_produccion_balance{slug}_{now_co.strftime('%Y-%m-%d')}.xlsx"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), filename


def _matches_sale_search(venta: Venta, raw_query: str) -> bool:
    term = raw_query.strip().lower()
    if not term:
        return True

    sale_date = venta.fecha_venta.date()
    month_abbr = _SPANISH_MONTH_ABBR[sale_date.month]
    date_tokens = (
        sale_date.isoformat(),
        f"{sale_date.day:02d} {month_abbr} {sale_date.year}",
        f"{sale_date.day} {month_abbr} {sale_date.year}",
        f"{sale_date.day:02d} de {month_abbr} de {sale_date.year}",
        f"{sale_date.day} de {month_abbr} de {sale_date.year}",
    )

    searchable: list[str] = [
        f"#{venta.id:03d}",
        f"#{venta.id}",
        str(venta.id),
        *date_tokens,
        _strip_trace_tags(venta.observaciones),
    ]

    numeric_term = term.lstrip("#0")
    if term.startswith("#") and numeric_term.isdigit() and int(numeric_term) == venta.id:
        return True

    for det in venta.detalles:
        pname = det.presentacion.producto.nombre
        searchable.append(pname)
        searchable.append(det.presentacion.nombre)
        if pname == "Hayaca":
            searchable.extend(["hayacas", "hayacas tradicionales"])
        elif pname == "Lechona":
            searchable.extend(
                [
                    "lechona tolimense (porción)",
                    "lechona tolimense (porcion)",
                    "porciones",
                ]
            )

    if venta.pedido is not None:
        searchable.append(f"pedido #{venta.pedido.id:03d}")
        searchable.append(f"pedido #{venta.pedido.id}")
        if venta.pedido.nombre_contacto:
            searchable.append(venta.pedido.nombre_contacto)
        if venta.pedido.cliente and venta.pedido.cliente.nombre:
            searchable.append(venta.pedido.cliente.nombre)

    return any(term in token.lower() for token in searchable if token)


def _format_related_order_details(venta: Venta) -> tuple[str, str]:
    if venta.pedido_id is None:
        return "Venta directa", "Sin pedido asociado"

    pedido_code = f"Pedido #{venta.pedido_id:03d}"
    pedido = venta.pedido
    if pedido is None:
        return pedido_code, "Pedido vinculado"

    parts: list[str] = []
    cliente_nombre = _sanitize_excel_text(
        pedido.nombre_contacto
        or (pedido.cliente.nombre if pedido.cliente is not None else "")
    )
    if cliente_nombre:
        parts.append(f"Cliente: {cliente_nombre}")

    estado_lbl = _PEDIDO_ESTADO_LABELS.get(pedido.estado, pedido.estado)
    if estado_lbl:
        parts.append(f"Estado: {estado_lbl}")

    if pedido.fecha_entrega_prevista is not None:
        parts.append(
            f"Entrega: {pedido.fecha_entrega_prevista.date().isoformat()}"
        )

    return pedido_code, (" · ".join(parts) if parts else "Pedido vinculado")


def generate_sales_report_xlsx(
    session: Session,
    *,
    q: str | None = None,
    estado: str | None = "concretada",
    producto_id: int | None = None,
    producto_nombre: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    periodo: str | None = None,
    incluir_historicos: bool = True,
    incluir_sinteticos: bool = True,
    solo_operativos: bool = False,
) -> tuple[bytes, str]:
    now_co = _now_colombia()
    eff_desde, eff_hasta, periodo_label = _resolve_period_bounds_and_label(
        periodo=periodo,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        today=now_co.date(),
    )
    canonical_prod = _canonical_product_name(producto_nombre)

    stmt = sales_service._load_venta_query()

    if estado:
        stmt = stmt.where(Venta.estado == estado)

    if eff_desde is not None:
        stmt = stmt.where(
            Venta.fecha_venta >= datetime.combine(eff_desde, datetime.min.time())
        )
    if eff_hasta is not None:
        stmt = stmt.where(
            Venta.fecha_venta <= datetime.combine(eff_hasta, datetime.max.time())
        )

    if producto_id is not None:
        stmt = stmt.where(
            Venta.detalles.any(
                DetalleVenta.presentacion.has(
                    Presentacion.producto_id == producto_id
                )
            )
        )
    elif canonical_prod:
        stmt = stmt.where(
            Venta.detalles.any(
                DetalleVenta.presentacion.has(
                    Presentacion.producto.has(
                        func.lower(Producto.nombre) == canonical_prod.lower()
                    )
                )
            )
        )

    if solo_operativos or not incluir_historicos:
        stmt = stmt.where(
            or_(
                Venta.observaciones.is_(None),
                ~Venta.observaciones.like("%IMPORTACION_EXCEL|%"),
            )
        )
    elif not incluir_sinteticos:
        stmt = stmt.where(
            or_(
                Venta.observaciones.is_(None),
                ~Venta.observaciones.like("%|es_sintetico=1%"),
            )
        )

    stmt = stmt.order_by(Venta.fecha_venta.desc(), Venta.id.desc())
    ventas = list(session.scalars(stmt).all())

    if q and q.strip():
        ventas = [v for v in ventas if _matches_sale_search(v, q)]

    # Construir filas de detalle respetando filtro de producto si está activo
    export_rows: list[tuple[Venta, DetalleVenta, Decimal]] = []
    for venta in ventas:
        venta_total = sum(
            (
                (Decimal(d.cantidad) * Decimal(d.precio_unitario)).quantize(
                    Decimal("0.01")
                )
                for d in venta.detalles
            ),
            Decimal("0.00"),
        )
        for det in venta.detalles:
            prod = det.presentacion.producto
            if producto_id is not None and prod.id != producto_id:
                continue
            if canonical_prod and prod.nombre.lower() != canonical_prod.lower():
                continue
            export_rows.append((venta, det, venta_total))

    if not export_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay ventas registradas para los filtros seleccionados.",
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Historial de Ventas"
    wb.properties.creator = "Sabores del Llano"
    wb.properties.title = "Reporte de Historial de Ventas"

    total_cols = 13
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    title_cell = ws.cell(
        row=1,
        column=1,
        value="SABORES DEL LLANO — REPORTE DE HISTORIAL DE VENTAS",
    )
    title_cell.font = _TITLE_FONT
    title_cell.fill = _TITLE_FILL
    title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    qty_by_prod: dict[str, int] = {"Hayaca": 0, "Lechona": 0}
    subtotal_by_prod: dict[str, Decimal] = {
        "Hayaca": Decimal("0.00"),
        "Lechona": Decimal("0.00"),
    }
    distinct_sale_ids: set[int] = set()
    grand_subtotal = Decimal("0.00")

    for venta, det, _ in export_rows:
        distinct_sale_ids.add(venta.id)
        pname = det.presentacion.producto.nombre
        qty_int = int(round(float(det.cantidad)))
        sub_dec = (Decimal(det.cantidad) * Decimal(det.precio_unitario)).quantize(
            Decimal("0.01")
        )
        qty_by_prod[pname] = qty_by_prod.get(pname, 0) + qty_int
        subtotal_by_prod[pname] = subtotal_by_prod.get(
            pname, Decimal("0.00")
        ) + sub_dec
        grand_subtotal += sub_dec

    first_prod = export_rows[0][1].presentacion.producto
    prod_filter_label = (
        f"{_display_product_name(first_prod.nombre)} ({_display_unit_plural(first_prod.unidad_base)})"
        if (producto_id is not None or canonical_prod is not None)
        else "Todos los productos"
    )
    search_label = _sanitize_excel_text(q) if (q and q.strip()) else "Sin filtro de texto"
    grand_money_val = _decimal_to_excel_money(grand_subtotal)

    meta_rows: list[tuple[str, object, str, object]] = [
        (
            "Fecha de generación:",
            now_co.strftime("%Y-%m-%d %H:%M"),
            "Período consultado:",
            periodo_label,
        ),
        (
            "Filtro de producto:",
            prod_filter_label,
            "Búsqueda aplicada:",
            search_label,
        ),
        (
            "Ventas exportadas:",
            f"{len(distinct_sale_ids)} venta(s) ({len(export_rows)} registro(s))",
            "Total ventas filtradas (COP):",
            grand_money_val,
        ),
        (
            "Unidades vendidas:",
            f"Hayacas: {qty_by_prod.get('Hayaca', 0):,} unidades · "
            f"Lechona: {qty_by_prod.get('Lechona', 0):,} platos",
            "",
            "",
        ),
    ]

    for offset_idx, (lbl1, val1, lbl2, val2) in enumerate(meta_rows, start=2):
        ws.row_dimensions[offset_idx].height = 20
        for c_idx in range(1, total_cols + 1):
            cell = ws.cell(row=offset_idx, column=c_idx)
            cell.fill = _META_FILL
            cell.border = _CELL_BORDER
        c_lbl1 = ws.cell(row=offset_idx, column=1, value=lbl1)
        c_lbl1.font = _META_LABEL_FONT
        if lbl2:
            ws.merge_cells(
                start_row=offset_idx, start_column=2, end_row=offset_idx, end_column=6
            )
            c_val1 = ws.cell(row=offset_idx, column=2, value=val1)
            c_val1.font = _META_VALUE_FONT
            ws.merge_cells(
                start_row=offset_idx, start_column=7, end_row=offset_idx, end_column=8
            )
            c_lbl2 = ws.cell(row=offset_idx, column=7, value=lbl2)
            c_lbl2.font = _META_LABEL_FONT
            ws.merge_cells(
                start_row=offset_idx,
                start_column=9,
                end_row=offset_idx,
                end_column=total_cols,
            )
            c_val2 = ws.cell(row=offset_idx, column=9, value=val2)
            c_val2.font = _META_VALUE_FONT
            if isinstance(val2, (int, float)):
                c_val2.number_format = _money_format_for_value(val2)
                c_val2.font = Font(name="Calibri", size=10, bold=True, color="1E1C1A")
            c_val2.alignment = Alignment(horizontal="left", vertical="center")
        else:
            ws.merge_cells(
                start_row=offset_idx,
                start_column=2,
                end_row=offset_idx,
                end_column=total_cols,
            )
            c_val1 = ws.cell(row=offset_idx, column=2, value=val1)
            c_val1.font = _META_VALUE_FONT

    header_row = 7
    headers = [
        "N.° Venta",
        "Fecha de venta",
        "Hora",
        "Producto",
        "Presentación",
        "Unidad",
        "Cantidad",
        "Precio unitario (COP)",
        "Subtotal (COP)",
        "Total venta (COP)",
        "Pedido relacionado",
        "Información del pedido",
        "Observaciones",
    ]
    ws.row_dimensions[header_row].height = 26
    for col_idx, h_text in enumerate(headers, start=1):
        h_cell = ws.cell(row=header_row, column=col_idx, value=h_text)
        h_cell.font = _HEADER_FONT
        h_cell.fill = _HEADER_FILL
        h_cell.border = _CELL_BORDER
        h_cell.alignment = Alignment(
            horizontal="center"
            if col_idx in (1, 2, 3, 6)
            else ("right" if 7 <= col_idx <= 10 else "left"),
            vertical="center",
            wrap_text=True,
        )

    ws.freeze_panes = f"A{header_row + 1}"

    current_row = header_row + 1
    for idx, (venta, det, venta_total) in enumerate(export_rows):
        fill = _ROW_ALT_FILL if idx % 2 == 1 else _ROW_WHITE_FILL
        pres = det.presentacion
        prod = pres.producto
        hora_str = (
            venta.fecha_venta.strftime("%H:%M")
            if (venta.fecha_venta.hour != 0 or venta.fecha_venta.minute != 0)
            else "Jornada completa"
        )
        cantidad_int = int(round(float(det.cantidad)))
        unit_price_val = _decimal_to_excel_money(Decimal(det.precio_unitario))
        subtotal_dec = (
            Decimal(det.cantidad) * Decimal(det.precio_unitario)
        ).quantize(Decimal("0.01"))
        subtotal_val = _decimal_to_excel_money(subtotal_dec)
        total_venta_val = _decimal_to_excel_money(venta_total)
        pedido_code, pedido_info = _format_related_order_details(venta)
        obs_clean = _sanitize_excel_text(venta.observaciones)

        pres_display = _sanitize_excel_text(
            f"{pres.nombre[:1].upper()}{pres.nombre[1:]}" if pres.nombre else ""
        )

        row_values: list[object] = [
            f"#{venta.id:03d}",
            venta.fecha_venta.date(),
            hora_str,
            _display_product_name(prod.nombre),
            pres_display,
            _display_unit_plural(prod.unidad_base),
            cantidad_int,
            unit_price_val,
            subtotal_val,
            total_venta_val,
            pedido_code,
            pedido_info,
            obs_clean,
        ]
        ws.row_dimensions[current_row].height = 20
        for col_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = _DATA_FONT
            cell.fill = fill
            cell.border = _CELL_BORDER
            if col_idx == 2:
                cell.number_format = "yyyy-mm-dd"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in (1, 3, 6):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 7:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (8, 9, 10) and isinstance(val, (int, float)):
                cell.number_format = _money_format_for_value(val)
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        current_row += 1

    # Subtotales por producto (respetando unidades base) + Total general monetario
    for prod_key, unit_label in (("Hayaca", "unidades"), ("Lechona", "platos")):
        qty_p = qty_by_prod.get(prod_key, 0)
        if qty_p <= 0:
            continue
        disp_name = _display_product_name(prod_key)
        sub_p_val = _decimal_to_excel_money(subtotal_by_prod[prod_key])
        sub_row: list[object] = [
            f"Subtotal {disp_name}",
            "",
            "",
            disp_name,
            "Individual",
            unit_label,
            qty_p,
            "",
            sub_p_val,
            sub_p_val,
            "",
            "",
            "",
        ]
        ws.row_dimensions[current_row].height = 21
        for col_idx, val in enumerate(sub_row, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = _TOTAL_FONT
            cell.fill = _TOTAL_FILL
            cell.border = _TOTAL_BORDER
            if col_idx == 6:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 7:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (9, 10) and isinstance(val, (int, float)):
                cell.number_format = _money_format_for_value(val)
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        current_row += 1

    grand_row: list[object] = [
        "TOTAL GENERAL",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        grand_money_val,
        grand_money_val,
        "",
        "",
        "",
    ]
    ws.row_dimensions[current_row].height = 22
    for col_idx, val in enumerate(grand_row, start=1):
        cell = ws.cell(row=current_row, column=col_idx, value=val)
        cell.font = _TOTAL_FONT
        cell.fill = _TOTAL_FILL
        cell.border = _TOTAL_BORDER
        if col_idx in (9, 10) and isinstance(val, (int, float)):
            cell.number_format = _money_format_for_value(val)
            cell.alignment = Alignment(horizontal="right", vertical="center")
        else:
            cell.alignment = Alignment(horizontal="left", vertical="center")

    _autofit_columns(
        ws,
        header_row=header_row,
        min_widths={
            1: 13,
            2: 15,
            3: 16,
            4: 13,
            5: 14,
            6: 12,
            7: 12,
            8: 19,
            9: 17,
            10: 18,
            11: 18,
            12: 30,
            13: 24,
        },
    )

    slug = (
        f"_{_PRODUCT_FILE_SLUG.get(first_prod.nombre, 'producto')}"
        if (producto_id is not None or canonical_prod is not None)
        else ""
    )
    filename = f"reporte_historial_ventas{slug}_{now_co.strftime('%Y-%m-%d')}.xlsx"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), filename
