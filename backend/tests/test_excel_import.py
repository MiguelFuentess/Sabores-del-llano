from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import get_engine
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
from app.services.excel_import import (
    build_trace_tag,
    import_excel_workbook,
    is_synthetic_trace,
    parse_and_validate_workbook,
)

HISTORICAL_EXCEL_PATH = Path(
    r"C:\Users\fuent\OneDrive\Desktop\Excel historico\Sabores_del_Llano_Datos_Ampliados_Ajustado.xlsx"
)


@pytest.fixture
def import_session():
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        for table_name in (
            "movimientos_inventario",
            "detalle_ventas",
            "ventas",
            "detalle_pedidos",
            "pedidos",
            "cierres_diarios",
            "producciones",
            "gastos",
            "presentaciones",
            "productos",
            "clientes",
        ):
            session.execute(text(f"DELETE FROM {table_name}"))
        session.flush()
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def sample_excel_file(tmp_path: Path) -> Path:
    """Crea un archivo Excel pequeño con datos sintéticos (<2026-06-06), reales (>=2026-06-06),
    la fecha con alerta 2025-11-11 y una fila vacía para pruebas rápidas y deterministas."""
    wb = openpyxl.Workbook()

    # 1. Productos
    ws_prod = wb.active
    ws_prod.title = "Productos"
    ws_prod.append(
        [
            "Producto",
            "Unidad base",
            "Presentacion",
            "Cantidad equivalente",
            "Precio de venta",
            "Estado",
        ]
    )
    ws_prod.append(["Hayaca", "Unidad", "individual", 1, 10000, "activo"])
    ws_prod.append(["Lechona", "Plato", "individual", 1, 12000, "activo"])

    # 2. Ventas (2 sintéticas en 2025-11-11 martes no festivo, 2 reales en 2026-06-06 sábado)
    ws_ventas = wb.create_sheet("Ventas")
    ws_ventas.append(
        [
            "Fecha",
            "Producto",
            "Presentación",
            "Cantidad",
            "Precio Unitario",
            "Total Venta",
        ]
    )
    ws_ventas.append([datetime(2025, 11, 11), "Hayaca", "Unidad", 100, 10000, 1000000])
    ws_ventas.append([datetime(2025, 11, 11), "Lechona", "Plato", 80, 12000, 960000])
    ws_ventas.append([datetime(2026, 6, 6), "Hayaca", "Unidad", 120, 10000, 1200000])
    ws_ventas.append([datetime(2026, 6, 6), "Lechona", "Plato", 90, 12000, 1080000])

    # 3. Pedidos (incluye dos pedidos del mismo cliente/fecha/producto con distinta cantidad + 1 fila vacía)
    ws_pedidos = wb.create_sheet("Pedidos")
    ws_pedidos.append(
        [
            "Fecha del pedido",
            "Fecha de entrega",
            "Cliente",
            "Producto",
            "Cantidad",
            "Estado",
        ]
    )
    ws_pedidos.append(
        [
            datetime(2025, 11, 8),
            datetime(2025, 11, 11),
            "Cliente Sintético Uno",
            "Hayaca",
            5,
            "Entregado",
        ]
    )
    ws_pedidos.append(
        [
            datetime(2026, 6, 3),
            datetime(2026, 6, 6),
            "Felipe Vargas",
            "Lechona",
            6,
            "Cancelado",
        ]
    )
    ws_pedidos.append(
        [
            datetime(2026, 6, 3),
            datetime(2026, 6, 6),
            "Felipe Vargas",
            "Lechona",
            3,
            "Entregado",
        ]
    )
    ws_pedidos.append([None, None, None, None, None, None])

    # 4. Produccion (Produccion = Ventas + Sobrantes)
    ws_produccion = wb.create_sheet("Produccion")
    ws_produccion.append(["Fecha", "Producto", "Ventas", "Sobrantes", "Produccion"])
    ws_produccion.append([datetime(2025, 11, 11), "Hayaca", 100, 10, 110])
    ws_produccion.append([datetime(2025, 11, 11), "Lechona", 80, 8, 88])
    ws_produccion.append([datetime(2026, 6, 6), "Hayaca", 120, 12, 132])
    ws_produccion.append([datetime(2026, 6, 6), "Lechona", 90, 9, 99])

    # 5. Sobrantes
    ws_sobrantes = wb.create_sheet("Sobrantes")
    ws_sobrantes.append(["Fecha", "Producto", "Produccion", "Sobrantes"])
    ws_sobrantes.append([datetime(2025, 11, 11), "Hayaca", 110, 10])
    ws_sobrantes.append([datetime(2025, 11, 11), "Lechona", 88, 8])
    ws_sobrantes.append([datetime(2026, 6, 6), "Hayaca", 132, 12])
    ws_sobrantes.append([datetime(2026, 6, 6), "Lechona", 99, 9])

    file_path = tmp_path / "sample_import.xlsx"
    wb.save(file_path)
    wb.close()
    return file_path


def test_trace_tag_builder_and_detector():
    syn_tag = build_trace_tag(
        hoja="Ventas",
        fila=12,
        es_sintetico=True,
        alerta_calendario="2025-11-11_martes_no_festivo",
    )
    assert (
        syn_tag
        == "[IMPORTACION_EXCEL|origen=sintetico|es_sintetico=1|hoja=Ventas|fila=12|alerta_calendario=2025-11-11_martes_no_festivo]"
    )
    assert is_synthetic_trace(syn_tag) is True

    real_tag = build_trace_tag(hoja="Pedidos", fila=900, es_sintetico=False)
    assert (
        real_tag
        == "[IMPORTACION_EXCEL|origen=real|es_sintetico=0|hoja=Pedidos|fila=900]"
    )
    assert is_synthetic_trace(real_tag) is False
    assert is_synthetic_trace("Observación manual de usuario") is None


def test_parse_and_validate_real_historical_workbook():
    if not HISTORICAL_EXCEL_PATH.is_file():
        pytest.skip("El archivo Excel histórico no se encuentra en la ruta esperada.")

    parsed = parse_and_validate_workbook(HISTORICAL_EXCEL_PATH)
    report = parsed.report

    assert report.valido_para_importar is True
    assert report.errores == []
    assert report.fecha_minima_operacion == date(2024, 11, 2)
    assert report.fecha_maxima_operacion == date(2026, 10, 31)
    assert report.total_fechas_operacion == 241
    assert report.total_clientes_unicos == 207
    assert report.clientes_reales == 42
    assert report.clientes_sinteticos == 165
    assert report.total_ventas_reales_cop == Decimal("136290000")

    by_sheet = {s.hoja: s for s in report.hojas}
    assert by_sheet["Ventas"].registros_validos == 482
    assert by_sheet["Ventas"].registros_reales == 98
    assert by_sheet["Ventas"].registros_sinteticos == 384
    assert by_sheet["Pedidos"].registros_validos == 1040
    assert by_sheet["Pedidos"].registros_reales == 210
    assert by_sheet["Pedidos"].registros_sinteticos == 830
    assert by_sheet["Pedidos"].filas_vacias_ignoradas == 1


def test_import_excel_is_idempotent_and_preserves_traceability(
    import_session: Session, sample_excel_file: Path
):
    first = import_excel_workbook(import_session, sample_excel_file, dry_run=False)

    assert first.tablas["productos"].creados == 2
    assert first.tablas["presentaciones"].creados == 2
    assert first.tablas["clientes"].creados == 2
    assert first.tablas["clientes"].reales_creados == 1
    assert first.tablas["clientes"].sinteticos_creados == 1
    assert first.tablas["pedidos"].creados == 3
    assert first.tablas["pedidos"].reales_creados == 2
    assert first.tablas["pedidos"].sinteticos_creados == 1
    assert first.tablas["ventas"].creados == 4
    assert first.tablas["detalle_ventas"].creados == 4
    assert first.tablas["producciones"].creados == 4
    assert first.tablas["cierres_diarios"].creados == 4
    assert first.tablas["movimientos_inventario"].creados == 8  # 4 prod + 4 venta

    # Verificar alerta de calendario en 2025-11-11
    syn_venta = import_session.scalar(
        select(Venta).where(
            Venta.observaciones.like("%alerta_calendario=2025-11-11_martes_no_festivo%")
        )
    )
    assert syn_venta is not None
    assert is_synthetic_trace(syn_venta.observaciones) is True

    # Segunda ejecución: idempotencia total (0 nuevos registros)
    second = import_excel_workbook(import_session, sample_excel_file, dry_run=False)
    for table_name, counter in second.tablas.items():
        assert counter.creados == 0, f"Se duplicaron registros en {table_name}"
        assert counter.existentes > 0


def test_import_excel_dry_run_rolls_back_all_changes(
    import_session: Session, sample_excel_file: Path
):
    res = import_excel_workbook(import_session, sample_excel_file, dry_run=True)
    assert res.dry_run is True
    assert res.tablas["ventas"].creados == 4
    assert res.tablas["pedidos"].creados == 3

    # Como dry_run=True revierte el savepoint, las tablas deben seguir en 0
    assert import_session.scalar(select(func.count()).select_from(Venta)) == 0
    assert import_session.scalar(select(func.count()).select_from(Pedido)) == 0
    assert import_session.scalar(select(func.count()).select_from(Cliente)) == 0


def test_import_excel_rejects_broken_production_formula(
    import_session: Session, sample_excel_file: Path
):
    wb = openpyxl.load_workbook(sample_excel_file)
    ws_prod = wb["Produccion"]
    # Alterar Produccion para que Ventas (100) + Sobrantes (10) != Produccion (999)
    ws_prod.cell(row=2, column=5, value=999)
    wb.save(sample_excel_file)
    wb.close()

    with pytest.raises(ValueError, match="errores de validación"):
        import_excel_workbook(import_session, sample_excel_file)
