from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import io

import openpyxl
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db, get_engine
from app.main import app
from app.models import (
    CierreDiario,
    Cliente,
    DetallePedido,
    DetalleVenta,
    Pedido,
    Presentacion,
    Produccion,
    Producto,
    Usuario,
    Venta,
)
from app.services.catalog import seed_initial_catalog
from app.services.excel_import import build_trace_tag

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def isolated_session():
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
            "usuarios",
        ):
            session.execute(text(f"DELETE FROM {table_name}"))
        session.flush()
        seed_initial_catalog(session, commit=False)
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def auth_headers(isolated_session: Session) -> dict[str, str]:
    user = Usuario(
        nombre_usuario="admin.reportes",
        nombre_completo="Administradora Reportes",
        password_hash=hash_password("ClaveSeguraReportes2026!"),
        activo=True,
    )
    isolated_session.add(user)
    isolated_session.commit()
    token, _ = create_access_token(
        user_id=user.id,
        username=user.nombre_usuario,
        secret_key=get_settings().auth_secret_key,
        expires_delta=timedelta(minutes=60),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api_client(client, isolated_session: Session):
    def override_get_db():
        yield isolated_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_report_endpoints_require_authentication(api_client):
    assert api_client.get("/producciones/reporte").status_code == 401
    assert api_client.get("/ventas/reporte").status_code == 401


def test_production_report_xlsx_structure_filters_units_and_empty_guard(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    hayaca = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Hayaca")
    )
    lechona = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Lechona")
    )
    assert hayaca is not None and lechona is not None

    pres_h = isolated_session.scalar(
        select(Presentacion).where(Presentacion.producto_id == hayaca.id)
    )
    pres_l = isolated_session.scalar(
        select(Presentacion).where(Presentacion.producto_id == lechona.id)
    )
    assert pres_h is not None and pres_l is not None

    # 1. Producción histórica de Hayaca (2026-10-24: prod 120, vend 105, sobrante 15)
    hist_tag = build_trace_tag(hoja="Produccion", fila=20, es_sintetico=False)
    isolated_session.add(
        Produccion(
            producto_id=hayaca.id,
            fecha_produccion=datetime(2026, 10, 24, 8, 0),
            cantidad_producida_base=Decimal("120.000"),
            observaciones=f"{hist_tag} Lote especial",
        )
    )
    isolated_session.add(
        CierreDiario(
            producto_id=hayaca.id,
            fecha=datetime(2026, 10, 24).date(),
            existencia_calculada_base=Decimal("15.000"),
            sobrante_real_base=Decimal("15.000"),
            observaciones=hist_tag,
        )
    )
    v_h = Venta(
        fecha_venta=datetime(2026, 10, 24, 13, 0),
        estado="concretada",
        observaciones=hist_tag,
    )
    isolated_session.add(v_h)
    isolated_session.flush()
    isolated_session.add(
        DetalleVenta(
            venta_id=v_h.id,
            presentacion_id=pres_h.id,
            cantidad=Decimal("105.000"),
            precio_unitario=Decimal("10000.00"),
            factor_conversion_snapshot=Decimal("1.0000"),
        )
    )

    # 2. Producción operativa de Lechona (2026-10-31: prod 60, vend 52, sobrante 8)
    isolated_session.add(
        Produccion(
            producto_id=lechona.id,
            fecha_produccion=datetime(2026, 10, 31, 8, 0),
            cantidad_producida_base=Decimal("60.000"),
            observaciones="=SUM(1,2)",
        )
    )
    isolated_session.add(
        CierreDiario(
            producto_id=lechona.id,
            fecha=datetime(2026, 10, 31).date(),
            existencia_calculada_base=Decimal("8.000"),
            sobrante_real_base=Decimal("8.000"),
            observaciones="Cierre operativo",
        )
    )
    v_l = Venta(
        fecha_venta=datetime(2026, 10, 31, 14, 30),
        estado="concretada",
        observaciones="Venta sábado",
    )
    isolated_session.add(v_l)
    isolated_session.flush()
    isolated_session.add(
        DetalleVenta(
            venta_id=v_l.id,
            presentacion_id=pres_l.id,
            cantidad=Decimal("52.000"),
            precio_unitario=Decimal("12000.00"),
            factor_conversion_snapshot=Decimal("1.0000"),
        )
    )
    isolated_session.commit()

    # Descargar reporte completo
    resp = api_client.get(
        "/producciones/reporte?periodo=all",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(XLSX_MIME)
    disp = resp.headers.get("content-disposition", "")
    assert "attachment;" in disp
    assert "reporte_produccion_balance_" in disp
    assert ".xlsx" in disp

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb["Producción y Balance"]

    headers = [ws.cell(row=7, column=c).value for c in range(1, 11)]
    assert headers == [
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

    # Fila 8: Lechona (2026-10-31, orden descendente)
    row_l = [ws.cell(row=8, column=c).value for c in range(1, 11)]
    assert row_l[0].strftime("%Y-%m-%d") == "2026-10-31"
    assert row_l[1] == "Lechona"
    assert row_l[2] == "platos"
    assert row_l[3:8] == [60, 52, 8, 8, 0]
    assert row_l[9] == "'=SUM(1,2)"

    # Fila 9: Hayacas (2026-10-24)
    row_h = [ws.cell(row=9, column=c).value for c in range(1, 11)]
    assert row_h[0].strftime("%Y-%m-%d") == "2026-10-24"
    assert row_h[1] == "Hayacas"
    assert row_h[2] == "unidades"
    assert row_h[3:8] == [120, 105, 15, 15, 0]
    assert row_h[9] == "Lote especial"

    # Ninguna celda expone marcas internas IMPORTACION_EXCEL
    all_texts = [
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1)
        for c in range(1, ws.max_column + 1)
    ]
    assert not any("IMPORTACION_EXCEL" in t for t in all_texts)

    # Filtrar únicamente Hayacas y rango de fecha
    resp_h = api_client.get(
        "/producciones/reporte?producto_nombre=hayacas&fecha_desde=2026-10-20&fecha_hasta=2026-10-25",
        headers=auth_headers,
    )
    assert resp_h.status_code == 200
    assert "reporte_produccion_balance_hayacas_" in resp_h.headers["content-disposition"]
    wb_h = openpyxl.load_workbook(io.BytesIO(resp_h.content))
    ws_h = wb_h["Producción y Balance"]
    assert ws_h.cell(row=8, column=2).value == "Hayacas"
    assert ws_h.cell(row=9, column=1).value == "Total Hayacas"

    # Filtro sin resultados -> 404 sin archivo vacío
    resp_empty = api_client.get(
        "/producciones/reporte?fecha_desde=2027-06-01&fecha_hasta=2027-06-10",
        headers=auth_headers,
    )
    assert resp_empty.status_code == 404
    assert "No hay registros de producción" in resp_empty.json()["detail"]


def test_sales_report_xlsx_structure_filters_monetary_values_and_related_order(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    hayaca = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Hayaca")
    )
    lechona = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Lechona")
    )
    assert hayaca is not None and lechona is not None

    pres_h = isolated_session.scalar(
        select(Presentacion).where(Presentacion.producto_id == hayaca.id)
    )
    pres_l = isolated_session.scalar(
        select(Presentacion).where(Presentacion.producto_id == lechona.id)
    )
    assert pres_h is not None and pres_l is not None

    cliente = Cliente(nombre="Restaurante El Morichal", telefono="3140001122")
    isolated_session.add(cliente)
    isolated_session.flush()

    pedido = Pedido(
        cliente_id=cliente.id,
        fecha_pedido=datetime(2026, 10, 30, 10, 0),
        fecha_entrega_prevista=datetime(2026, 10, 31, 12, 0),
        estado="confirmado",
        nombre_contacto="Doña Clara",
        telefono_contacto="3140001122",
    )
    isolated_session.add(pedido)
    isolated_session.flush()
    isolated_session.add(
        DetallePedido(
            pedido_id=pedido.id,
            presentacion_id=pres_l.id,
            cantidad=Decimal("10.000"),
            precio_unitario=Decimal("12000.00"),
            factor_conversion_snapshot=Decimal("1.0000"),
        )
    )
    isolated_session.commit()

    # Crear venta vinculada al pedido vía endpoint oficial POST /ventas
    sale_order_resp = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "pedido_id": pedido.id,
            "fecha_venta": "2026-10-31T13:15:00",
            "observaciones": "Entrega puntual",
            "detalles": [
                {"producto_nombre": "Lechona", "cantidad": 10, "precio_unitario": 12000}
            ],
        },
    )
    assert sale_order_resp.status_code == 201

    # Crear venta directa de Hayacas sin pedido
    sale_direct_resp = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "fecha_venta": "2026-10-25T00:00:00",
            "observaciones": "Mostrador domingo",
            "detalles": [
                {"producto_nombre": "Hayaca", "cantidad": 25, "precio_unitario": 10000}
            ],
        },
    )
    assert sale_direct_resp.status_code == 201

    # Descargar reporte completo
    resp = api_client.get("/ventas/reporte?periodo=all", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(XLSX_MIME)
    assert "reporte_historial_ventas_" in resp.headers["content-disposition"]

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb["Historial de Ventas"]

    headers = [ws.cell(row=7, column=c).value for c in range(1, 14)]
    assert headers == [
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

    # Fila 8: Venta vinculada a pedido (Lechona, 2026-10-31 13:15)
    row_order = [ws.cell(row=8, column=c).value for c in range(1, 14)]
    assert row_order[1].strftime("%Y-%m-%d") == "2026-10-31"
    assert row_order[2] == "13:15"
    assert row_order[3] == "Lechona"
    assert row_order[4] == "Individual"
    assert row_order[5] == "platos"
    assert row_order[6] == 10
    assert row_order[7] == 12000
    assert row_order[8] == 120000
    assert row_order[9] == 120000
    assert row_order[10] == f"Pedido #{pedido.id:03d}"
    assert "Cliente: Doña Clara" in row_order[11]
    assert "Estado: Entregado" in row_order[11]
    assert "Entrega: 2026-10-31" in row_order[11]
    assert ws.cell(row=8, column=8).number_format == "$#,##0"

    # Fila 9: Venta directa (Hayacas, 2026-10-25 Jornada completa)
    row_direct = [ws.cell(row=9, column=c).value for c in range(1, 14)]
    assert row_direct[1].strftime("%Y-%m-%d") == "2026-10-25"
    assert row_direct[2] == "Jornada completa"
    assert row_direct[3] == "Hayacas"
    assert row_direct[4] == "Individual"
    assert row_direct[5] == "unidades"
    assert row_direct[6] == 25
    assert row_direct[7] == 10000
    assert row_direct[8] == 250000
    assert row_direct[9] == 250000
    assert row_direct[10] == "Venta directa"
    assert row_direct[11] == "Sin pedido asociado"

    # Total general = 120000 + 250000 = 370000
    assert ws.cell(row=ws.max_row, column=1).value == "TOTAL GENERAL"
    assert ws.cell(row=ws.max_row, column=9).value == 370000

    # Búsqueda por etiqueta de interfaz ("Hayacas Tradicionales") respeta el filtro del módulo
    resp_search = api_client.get(
        "/ventas/reporte?q=Hayacas%20Tradicionales",
        headers=auth_headers,
    )
    assert resp_search.status_code == 200
    wb_s = openpyxl.load_workbook(io.BytesIO(resp_search.content))
    ws_s = wb_s["Historial de Ventas"]
    assert ws_s.cell(row=8, column=4).value == "Hayacas"
    assert ws_s.cell(row=ws_s.max_row, column=9).value == 250000

    # Búsqueda sin coincidencias -> 404 sin descargar archivo vacío
    resp_none = api_client.get(
        "/ventas/reporte?q=BusquedaSinResultados999",
        headers=auth_headers,
    )
    assert resp_none.status_code == 404
    assert "No hay ventas registradas" in resp_none.json()["detail"]


def test_reports_export_with_real_mysql_data_preserves_database_integrity():
    from app.services.reports import (
        generate_production_report_xlsx,
        generate_sales_report_xlsx,
    )

    engine = get_engine()
    with Session(engine) as session:
        before = {
            tbl: session.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar_one()
            for tbl in ("ventas", "producciones", "cierres_diarios", "pedidos")
        }

        prod_bytes, prod_name = generate_production_report_xlsx(
            session, periodo="all"
        )
        sales_bytes, sales_name = generate_sales_report_xlsx(
            session, periodo="all"
        )

        after = {
            tbl: session.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar_one()
            for tbl in ("ventas", "producciones", "cierres_diarios", "pedidos")
        }

    assert before == after
    assert before["ventas"] == 482
    assert before["producciones"] == 482
    assert before["cierres_diarios"] == 482
    assert prod_name.endswith(".xlsx")
    assert sales_name.endswith(".xlsx")

    wb_prod = openpyxl.load_workbook(io.BytesIO(prod_bytes))
    ws_prod = wb_prod["Producción y Balance"]
    # 7 encabezado + 482 registros + 2 filas de totales (Hayacas y Lechona) = 491
    assert ws_prod.max_row == 7 + 482 + 2

    wb_sales = openpyxl.load_workbook(io.BytesIO(sales_bytes))
    ws_sales = wb_sales["Historial de Ventas"]
    # 7 encabezado + 482 registros + 2 subtotales + 1 total general = 492
    assert ws_sales.max_row == 7 + 482 + 3
