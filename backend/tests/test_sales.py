from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import re

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db, get_engine
from app.main import app
from app.models import (
    DetalleVenta,
    MovimientoInventario,
    Presentacion,
    Usuario,
    Venta,
)
from app.services.catalog import seed_initial_catalog
from app.services.excel_import import build_trace_tag

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def isolated_session():
    """Sesión transaccional aislada con SAVEPOINT y ROLLBACK automático al finalizar."""
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
        nombre_usuario="admin.ventas",
        nombre_completo="Administradora Ventas",
        password_hash=hash_password("ClaveSeguraVentas2026!"),
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


def test_sales_routes_require_authentication(api_client):
    assert api_client.get("/ventas").status_code == 401
    assert (
        api_client.post(
            "/ventas",
            json={
                "detalles": [{"producto_nombre": "Hayaca", "cantidad": 2}],
            },
        ).status_code
        == 401
    )
    assert (
        api_client.patch("/ventas/1", json={"observaciones": "x"}).status_code
        == 401
    )
    assert api_client.delete("/ventas/1").status_code == 401


def test_create_sale_calculates_totals_and_creates_inventory_movements(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    # Crear venta operativa con 4 Hayacas (precio catálogo $10.000) y 3 Lechonas (precio explícito $12.500)
    resp = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "fecha_venta": "2026-11-04T12:30:00",
            "observaciones": "Venta mostrador mediodía",
            "detalles": [
                {"producto_nombre": "Hayaca", "cantidad": 4},
                {
                    "producto_nombre": "Lechona",
                    "cantidad": 3,
                    "precio_unitario": "12500.00",
                },
            ],
        },
    )
    assert resp.status_code == 201
    sale = resp.json()
    assert sale["estado"] == "concretada"
    assert sale["es_historico"] is False
    assert sale["es_sintetico"] is False
    assert sale["origen_registro"] == "operativo"
    assert Decimal(sale["cantidad_total_base"]) == Decimal("7.000")
    assert Decimal(sale["total"]) == Decimal("77500.00")
    assert len(sale["detalles"]) == 2

    # Verificar que se crearon exactamente 2 movimientos de inventario de salida (tipo='venta')
    movs = list(
        isolated_session.scalars(
            select(MovimientoInventario).order_by(MovimientoInventario.id.asc())
        ).all()
    )
    assert len(movs) == 2
    assert all(m.tipo == "venta" for m in movs)
    assert sorted(Decimal(m.cantidad_base) for m in movs) == [
        Decimal("3.000"),
        Decimal("4.000"),
    ]

    # Consultar detalles mediante GET /ventas/{id}/detalles
    det_resp = api_client.get(
        f"/ventas/{sale['id']}/detalles", headers=auth_headers
    )
    assert det_resp.status_code == 200
    assert len(det_resp.json()) == 2


def test_sale_validations_reject_invalid_quantities_prices_and_presentations(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    # 1. Cantidad fraccionaria o <= 0 -> 422
    bad_qty = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": "1.5"}],
        },
    )
    assert bad_qty.status_code == 422

    # 2. Precio unitario <= 0 -> 422
    bad_price = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "detalles": [
                {"producto_nombre": "Hayaca", "cantidad": 2, "precio_unitario": 0}
            ],
        },
    )
    assert bad_price.status_code == 422

    # 3. Producto inexistente -> 404
    bad_prod = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "detalles": [{"producto_nombre": "Empanada", "cantidad": 2}],
        },
    )
    assert bad_prod.status_code == 404

    # 4. Presentación no individual es rechazada (400)
    lechona_id = isolated_session.scalar(
        text("SELECT id FROM productos WHERE nombre = 'Lechona'")
    )
    cojin = Presentacion(
        producto_id=int(lechona_id),
        nombre="cojin_40",
        unidad_venta="Cojin",
        factor_conversion=Decimal("40.0000"),
        precio_actual=Decimal("420000.00"),
        activo=True,
    )
    isolated_session.add(cojin)
    isolated_session.commit()

    non_indiv = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "detalles": [{"presentacion_id": cojin.id, "cantidad": 1}],
        },
    )
    assert non_indiv.status_code == 400


def test_sale_linked_to_operational_order_marks_delivered_and_prevents_duplicates(
    api_client,
    auth_headers: dict[str, str],
):
    order_resp = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Carlos Andrés Rojas",
            "fecha_pedido": "2026-11-04T09:00:00",
            "fecha_entrega_prevista": "2026-11-07T13:00:00",
            "modalidad_entrega": "retiro",
            "detalles": [{"producto_nombre": "Lechona", "cantidad": 5}],
        },
    )
    assert order_resp.status_code == 201
    order_id = order_resp.json()["id"]

    sale_resp = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "pedido_id": order_id,
            "fecha_venta": "2026-11-07T13:05:00",
            "detalles": [{"producto_nombre": "Lechona", "cantidad": 5}],
        },
    )
    assert sale_resp.status_code == 201
    assert sale_resp.json()["pedido_id"] == order_id

    # El pedido vinculado pasa automáticamente a estado 'entregado'
    updated_order = api_client.get(
        f"/pedidos/{order_id}", headers=auth_headers
    ).json()
    assert updated_order["estado"] == "entregado"

    # Intentar registrar una segunda venta sobre el mismo pedido devuelve 409
    dup_sale = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "pedido_id": order_id,
            "detalles": [{"producto_nombre": "Lechona", "cantidad": 5}],
        },
    )
    assert dup_sale.status_code == 409


def test_update_annul_delete_operational_sale_and_protect_historical_sales(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    # 1. Crear venta operativa
    created = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "fecha_venta": "2026-11-04T10:00:00",
            "detalles": [
                {"producto_nombre": "Hayaca", "cantidad": 3, "precio_unitario": 10000}
            ],
        },
    ).json()
    venta_id = created["id"]

    # 2. Actualizar cantidad y precio -> sincroniza movimientos_inventario sin violar fk_movimientos_detalle_venta
    patched = api_client.patch(
        f"/ventas/{venta_id}",
        headers=auth_headers,
        json={
            "fecha_venta": "2026-11-04T11:15:00",
            "detalles": [
                {"producto_nombre": "Lechona", "cantidad": 6, "precio_unitario": 12000}
            ],
        },
    )
    assert patched.status_code == 200
    p_data = patched.json()
    assert Decimal(p_data["total"]) == Decimal("72000.00")
    assert p_data["detalles"][0]["producto_nombre"] == "Lechona"

    movs_after_patch = list(
        isolated_session.scalars(select(MovimientoInventario)).all()
    )
    assert len(movs_after_patch) == 1
    assert Decimal(movs_after_patch[0].cantidad_base) == Decimal("6.000")

    # 3. Anular la venta retira el descuento de inventario
    annulled = api_client.patch(
        f"/ventas/{venta_id}",
        headers=auth_headers,
        json={"estado": "anulada"},
    )
    assert annulled.status_code == 200
    assert annulled.json()["estado"] == "anulada"
    assert len(list(isolated_session.scalars(select(MovimientoInventario)).all())) == 0

    # 4. Reactivar a concretada vuelve a generar el movimiento de inventario y luego eliminar la venta limpia todo
    reactivated = api_client.patch(
        f"/ventas/{venta_id}",
        headers=auth_headers,
        json={"estado": "concretada"},
    )
    assert reactivated.status_code == 200
    assert len(list(isolated_session.scalars(select(MovimientoInventario)).all())) == 1

    del_resp = api_client.delete(f"/ventas/{venta_id}", headers=auth_headers)
    assert del_resp.status_code == 204
    assert (
        api_client.get(f"/ventas/{venta_id}", headers=auth_headers).status_code
        == 404
    )
    assert len(list(isolated_session.scalars(select(MovimientoInventario)).all())) == 0

    # 5. Simular una venta histórica importada y comprobar protección 409 en PATCH y DELETE
    trace = build_trace_tag(hoja="Ventas", fila=410, es_sintetico=False)
    hayaca_pres = isolated_session.scalar(
        text(
            "SELECT pr.id FROM presentaciones pr JOIN productos p ON p.id = pr.producto_id WHERE p.nombre = 'Hayaca'"
        )
    )
    hist_venta = Venta(
        pedido_id=None,
        fecha_venta=datetime(2026, 7, 12, 0, 0),
        estado="concretada",
        observaciones=trace,
    )
    isolated_session.add(hist_venta)
    isolated_session.flush()
    hist_det = DetalleVenta(
        venta_id=hist_venta.id,
        presentacion_id=int(hayaca_pres),
        cantidad=Decimal("80.000"),
        precio_unitario=Decimal("10000.00"),
        factor_conversion_snapshot=Decimal("1.0000"),
    )
    isolated_session.add(hist_det)
    isolated_session.commit()

    hist_get = api_client.get(
        f"/ventas/{hist_venta.id}", headers=auth_headers
    ).json()
    assert hist_get["es_historico"] is True
    assert hist_get["origen_registro"] == "historico_real"

    assert (
        api_client.patch(
            f"/ventas/{hist_venta.id}",
            headers=auth_headers,
            json={"observaciones": "Intento editar histórico"},
        ).status_code
        == 409
    )
    assert (
        api_client.delete(
            f"/ventas/{hist_venta.id}", headers=auth_headers
        ).status_code
        == 409
    )

    # Filtros de listado
    all_sales = api_client.get("/ventas", headers=auth_headers).json()
    assert len(all_sales) == 1
    only_op = api_client.get(
        "/ventas?solo_operativos=true", headers=auth_headers
    ).json()
    assert len(only_op) == 0


def test_sales_filters_search_and_pagination(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    # Crear 2 ventas operativas en distintas fechas y distintos productos + 1 sintética histórica
    s1 = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "fecha_venta": "2026-11-01T09:00:00",
            "observaciones": "Venta domingo familia Pérez",
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": 5}],
        },
    ).json()
    s2 = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "fecha_venta": "2026-11-04T14:00:00",
            "observaciones": "Venta empresarial",
            "detalles": [{"producto_nombre": "Lechona", "cantidad": 10}],
        },
    ).json()

    trace_syn = build_trace_tag(hoja="Ventas", fila=15, es_sintetico=True)
    hayaca_pres = isolated_session.scalar(
        text(
            "SELECT pr.id FROM presentaciones pr JOIN productos p ON p.id = pr.producto_id WHERE p.nombre = 'Hayaca'"
        )
    )
    syn_venta = Venta(
        pedido_id=None,
        fecha_venta=datetime(2025, 12, 20, 0, 0),
        estado="concretada",
        observaciones=trace_syn,
    )
    isolated_session.add(syn_venta)
    isolated_session.flush()
    isolated_session.add(
        DetalleVenta(
            venta_id=syn_venta.id,
            presentacion_id=int(hayaca_pres),
            cantidad=Decimal("50.000"),
            precio_unitario=Decimal("10000.00"),
            factor_conversion_snapshot=Decimal("1.0000"),
        )
    )
    isolated_session.commit()

    # 1. Listado completo incluye históricas sintéticas y operativas (3)
    full = api_client.get("/ventas", headers=auth_headers).json()
    assert len(full) == 3

    # 2. Excluir sintéticos deja solo las 2 operativas
    no_syn = api_client.get(
        "/ventas?incluir_sinteticos=false", headers=auth_headers
    ).json()
    assert [v["id"] for v in no_syn] == [s2["id"], s1["id"]]

    # 3. Filtrar por producto_nombre
    only_lechona = api_client.get(
        "/ventas?producto_nombre=Lechona", headers=auth_headers
    ).json()
    assert [v["id"] for v in only_lechona] == [s2["id"]]

    # 4. Filtrar por rango de fechas (fecha_desde / fecha_hasta)
    by_date = api_client.get(
        "/ventas?fecha_desde=2026-11-01&fecha_hasta=2026-11-02",
        headers=auth_headers,
    ).json()
    assert [v["id"] for v in by_date] == [s1["id"]]

    # 5. Búsqueda por texto (q) y por número de recibo (#id)
    by_q = api_client.get("/ventas?q=empresarial", headers=auth_headers).json()
    assert [v["id"] for v in by_q] == [s2["id"]]

    by_receipt = api_client.get(
        f"/ventas?q=%2300{s1['id']}", headers=auth_headers
    ).json()
    assert [v["id"] for v in by_receipt] == [s1["id"]]

    # 6. Paginación limit / offset
    page_1 = api_client.get("/ventas?limit=1&offset=0", headers=auth_headers).json()
    page_2 = api_client.get("/ventas?limit=1&offset=1", headers=auth_headers).json()
    assert len(page_1) == 1 and len(page_2) == 1
    assert page_1[0]["id"] != page_2[0]["id"]


def test_frontend_sales_integration_and_filters():
    sales_storage_src = (
        PROJECT_ROOT / "src" / "features" / "sales" / "services" / "salesStorage.js"
    ).read_text(encoding="utf-8")
    use_sales_src = (
        PROJECT_ROOT / "src" / "features" / "sales" / "hooks" / "useSales.js"
    ).read_text(encoding="utf-8")
    sales_page_src = (
        PROJECT_ROOT / "src" / "features" / "sales" / "pages" / "SalesPage.jsx"
    ).read_text(encoding="utf-8")
    sales_filters_src = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "sales"
        / "components"
        / "SalesFilters.jsx"
    ).read_text(encoding="utf-8")
    filter_sales_src = (
        PROJECT_ROOT / "src" / "features" / "sales" / "utils" / "filterSales.js"
    ).read_text(encoding="utf-8")
    sale_modal_src = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "sales"
        / "components"
        / "SaleFormModal.jsx"
    ).read_text(encoding="utf-8")

    # 1. salesStorage.js usa apiRequest contra /ventas, limpia localStorage obsoleto y no lee/escribe ventas en localStorage
    assert re.search(r"apiRequest\(\s*['\"`]/ventas", sales_storage_src)
    assert "sabores-del-llano-sales-v1" in sales_storage_src
    assert "sabores-del-llano-sales-next-receipt-v1" in sales_storage_src
    assert "localStorage.getItem" not in sales_storage_src
    assert "localStorage.setItem" not in sales_storage_src
    assert re.search(r"incluirSinteticos\s*=\s*true", sales_storage_src)
    assert re.search(r"limit\s*=\s*2000", sales_storage_src)

    # 2. SalesFilters.jsx y filterSales.js incluyen 'all' ("Todo el historial") manteniendo week, 15days y month
    assert 'value="all"' in sales_filters_src
    assert "Todo el historial" in sales_filters_src
    assert 'value="week"' in sales_filters_src
    assert 'value="15days"' in sales_filters_src
    assert 'value="month"' in sales_filters_src
    assert "period === 'all'" in filter_sales_src
    assert "useState('all')" in sales_page_src

    # 3. SaleFormModal.jsx precarga el precio unitario oficial del catálogo
    assert "getDefaultUnitPrice" in sale_modal_src

    # 4. useSales.js y SalesPage.jsx trabajan de forma asíncrona
    assert "async" in use_sales_src
    assert "await create(" in sales_page_src
    assert "await update(" in sales_page_src
    assert "await remove(" in sales_page_src


def test_frontend_sale_form_modal_order_linking():
    """Verifica que SaleFormModal incorpora el selector opcional de pedidos pendientes,
    autocompleta producto y cantidades respetando unidades base, previene el doble envío,
    documenta y resguarda pedidos con múltiples detalles y envía pedido_id al servicio."""
    sale_modal_src = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "sales"
        / "components"
        / "SaleFormModal.jsx"
    ).read_text(encoding="utf-8")
    sales_storage_src = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "sales"
        / "services"
        / "salesStorage.js"
    ).read_text(encoding="utf-8")
    use_orders_src = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "orders"
        / "hooks"
        / "useOrders.js"
    ).read_text(encoding="utf-8")

    # 1. SaleFormModal consulta pedidos mediante useOrders con filtro operativo
    assert "useOrders" in sale_modal_src
    assert "useOrders({ soloOperativos: true })" in sale_modal_src

    # 2. El selector existe y filtra órdenes históricas, entregadas o canceladas
    assert "sale-order-select" in sale_modal_src
    assert "!order.esHistorico" in sale_modal_src
    assert "order.status !== 'Entregado'" in sale_modal_src
    assert "order.status !== 'Cancelado'" in sale_modal_src

    # 3. Permite volver a venta directa y limpiar la selección
    assert "Venta directa (sin pedido asociado)" in sale_modal_src
    assert "handleClearOrder" in sale_modal_src
    assert "Limpiar selección" in sale_modal_src

    # 4. Autocompleta producto, cantidad y precio unitario
    assert "mapOrderToSaleProduct" in sale_modal_src
    assert "extractOrderQuantity" in sale_modal_src
    assert "extractOrderUnitPrice" in sale_modal_src

    # 5. Manejo seguro de pedidos con múltiples productos sin descarte silencioso
    assert "hasMultipleDetails" in sale_modal_src
    assert "sales-order-warning" in sale_modal_src
    assert "hasMultipleDetails" in sale_modal_src and "disabled=" in sale_modal_src

    # 6. Envío de pedido_id y prevención de doble envío
    assert "pedidoId: selectedOrderId ? Number(selectedOrderId) : undefined" in sale_modal_src
    assert "isSaving" in sale_modal_src

    # 7. Sincronización de eventos entre ventas y pedidos
    assert "sabores-del-llano:orders-changed" in sales_storage_src
    assert "sabores-del-llano:orders-changed" in use_orders_src


