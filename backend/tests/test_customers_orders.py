from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db, get_engine
from app.main import app
from app.models import Cliente, DetallePedido, Pedido, Presentacion, Producto, Usuario
from app.services.auth import initialize_admin_from_env
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
        nombre_usuario="admin.pedidos",
        nombre_completo="Administradora Pedidos",
        password_hash=hash_password("ClaveSeguraPedidos2026!"),
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


def test_frontend_demo_orders_cleanup_preserves_ui_and_enforces_rules():
    """Verifica que los 6 pedidos ficticios INITIAL_DEMO_ORDERS fueron eliminados y que
    los componentes visuales y reglas de negocio del frontend se conservan."""
    order_options_src = (
        PROJECT_ROOT / "src" / "features" / "orders" / "data" / "orderOptions.js"
    ).read_text(encoding="utf-8")
    orders_storage_src = (
        PROJECT_ROOT / "src" / "features" / "orders" / "services" / "ordersStorage.js"
    ).read_text(encoding="utf-8")
    validate_order_src = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "orders"
        / "utils"
        / "validateOrderData.js"
    ).read_text(encoding="utf-8")
    modal_src = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "orders"
        / "components"
        / "OrderFormModal.jsx"
    ).read_text(encoding="utf-8")

    # 1. No existen pedidos ficticios ni presentaciones inventadas en orderOptions.js
    assert "INITIAL_DEMO_ORDERS" not in order_options_src
    assert "demo-order-001" not in order_options_src
    assert "lechona-cojin-30" not in order_options_src
    assert "lechona-cojin-50" not in order_options_src
    assert "hayacas-dozen" not in order_options_src

    # 2. ordersStorage.js y customersApi.js ya no almacenan en localStorage ni usan INITIAL_DEMO_ORDERS y consumen la API real (/pedidos y /clientes)
    customers_api_src = (
        PROJECT_ROOT / "src" / "features" / "orders" / "services" / "customersApi.js"
    ).read_text(encoding="utf-8")
    assert "INITIAL_DEMO_ORDERS" not in orders_storage_src
    assert re.search(r"apiRequest\(\s*['\"`]/pedidos", orders_storage_src)
    assert re.search(r"incluirSinteticos\s*=\s*true", orders_storage_src)
    assert re.search(r"limit\s*=\s*2000", orders_storage_src)
    assert re.search(r"apiRequest\(\s*['\"`]/clientes", customers_api_src)
    assert re.search(r"incluirSinteticos\s*=\s*true", customers_api_src)
    assert "localStorage.getItem" not in orders_storage_src
    assert "localStorage.setItem" not in orders_storage_src

    # 3. demoAccess.js fue eliminado y el login/guard/sidebar usan authService.js
    assert not (PROJECT_ROOT / "src" / "features" / "auth" / "demoAccess.js").exists()
    auth_service_src = (
        PROJECT_ROOT / "src" / "features" / "auth" / "services" / "authService.js"
    ).read_text(encoding="utf-8")
    login_page_src = (
        PROJECT_ROOT / "src" / "features" / "auth" / "pages" / "LoginPage.jsx"
    ).read_text(encoding="utf-8")
    guard_src = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "auth"
        / "components"
        / "DemoAccessGuard.jsx"
    ).read_text(encoding="utf-8")
    sidebar_src = (
        PROJECT_ROOT / "src" / "components" / "layout" / "Sidebar.jsx"
    ).read_text(encoding="utf-8")

    assert re.search(r"['\"`]/auth/login['\"`]", auth_service_src)
    assert re.search(r"['\"`]/auth/me['\"`]", auth_service_src)
    assert "demoAccess" not in login_page_src
    assert "demoAccess" not in guard_src
    assert "demoAccess" not in sidebar_src
    assert "loginWithCredentials" in login_page_src
    assert "fetchCurrentUser" in guard_src
    assert "clearAuthSession" in sidebar_src

    # 4. Validación de domicilio exige dirección y teléfono en el frontend
    assert "errors.address" in validate_order_src
    assert "errors.phone" in validate_order_src
    assert 'label="Número de teléfono" required error={errors.phone}' in modal_src

    # 4. Páginas y componentes visuales de otros módulos permanecen intactos
    for preserved_path in (
        "src/features/orders/pages/OrdersPage.jsx",
        "src/features/orders/components/OrdersList.jsx",
        "src/features/orders/components/OrdersFilters.jsx",
        "src/features/orders/components/DeleteOrderDialog.jsx",
        "src/features/sales/pages/SalesPage.jsx",
        "src/features/production/pages/ProductionPage.jsx",
        "src/features/dashboard/pages/DashboardPage.jsx",
        "src/features/demand/pages/DemandPage.jsx",
        "src/features/public/pages/PublicHomePage.jsx",
    ):
        assert (PROJECT_ROOT / preserved_path).is_file()


def test_routes_require_authentication(api_client):
    assert api_client.get("/clientes").status_code == 401
    assert api_client.post("/clientes", json={"nombre": "Ana"}).status_code == 401
    assert api_client.get("/pedidos").status_code == 401
    assert (
        api_client.post(
            "/pedidos",
            json={
                "cliente_nombre": "Ana",
                "fecha_entrega_prevista": "2026-11-07T12:00:00",
                "detalles": [{"producto_nombre": "Hayaca", "cantidad": 2}],
            },
        ).status_code
        == 401
    )


def test_create_query_update_and_deduplicate_clientes(
    api_client, auth_headers: dict[str, str]
):
    # Crear cliente operativo
    resp = api_client.post(
        "/clientes",
        headers=auth_headers,
        json={
            "nombre": "  María   Fernanda   López  ",
            "telefono": "3101234567",
            "correo": "mflopez@example.com",
            "notas": "Cliente frecuente de domingos",
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["nombre"] == "María Fernanda López"
    assert created["telefono"] == "3101234567"
    assert created["es_historico"] is False
    assert created["es_sintetico"] is False
    assert created["origen_registro"] == "operativo"

    # Intento duplicado exacto (mismo nombre y mismo teléfono) -> 409
    dup = api_client.post(
        "/clientes",
        headers=auth_headers,
        json={
            "nombre": "maría fernanda lópez",
            "telefono": "3101234567",
        },
    )
    assert dup.status_code == 409

    # Homónimo legítimo (mismo nombre pero distinto teléfono) -> 201 sin fusionar
    homonym = api_client.post(
        "/clientes",
        headers=auth_headers,
        json={
            "nombre": "María Fernanda López",
            "telefono": "3209998877",
        },
    )
    assert homonym.status_code == 201
    assert homonym.json()["id"] != created["id"]

    # Consultar por id y listar con búsqueda
    by_id = api_client.get(f"/clientes/{created['id']}", headers=auth_headers)
    assert by_id.status_code == 200
    assert by_id.json()["correo"] == "mflopez@example.com"

    listed = api_client.get(
        "/clientes?q=María Fernanda", headers=auth_headers
    ).json()
    assert len(listed) == 2

    # Actualizar cliente
    patched = api_client.patch(
        f"/clientes/{created['id']}",
        headers=auth_headers,
        json={"telefono": "3107654321", "notas": "Actualizó número"},
    )
    assert patched.status_code == 200
    assert patched.json()["telefono"] == "3107654321"
    assert patched.json()["notas"] == "Actualizó número"


def test_free_text_customer_resolution_associates_existing_and_separates_homonyms(
    api_client, auth_headers: dict[str, str]
):
    # Pedido 1: crea automáticamente al cliente "Jorge Iván Mora" (modalidad retiro)
    order1 = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Jorge Iván Mora",
            "fecha_pedido": "2026-11-05T09:00:00",
            "fecha_entrega_prevista": "2026-11-07T12:00:00",
            "modalidad_entrega": "retiro",
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": 4}],
        },
    )
    assert order1.status_code == 201
    cid_1 = order1.json()["cliente_id"]

    # Pedido 2: mismo cliente pide a domicilio con su teléfono -> reutiliza el mismo cliente_id
    order2 = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "  jorge   iván mora ",
            "fecha_pedido": "2026-11-06T10:00:00",
            "fecha_entrega_prevista": "2026-11-08T13:00:00",
            "modalidad_entrega": "domicilio",
            "direccion_entrega": "Calle 14 # 22-10 Barrio Centro",
            "telefono_contacto": "3112223344",
            "detalles": [{"producto_nombre": "Lechona", "cantidad": 2}],
        },
    )
    assert order2.status_code == 201
    assert order2.json()["cliente_id"] == cid_1

    # Pedido 3: otra persona llamada "Jorge Iván Mora" pero con distinto teléfono -> NO los fusiona
    order3 = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Jorge Iván Mora",
            "fecha_pedido": "2026-11-06T11:00:00",
            "fecha_entrega_prevista": "2026-11-08T14:00:00",
            "modalidad_entrega": "domicilio",
            "direccion_entrega": "Vereda San Nicolás Km 3",
            "telefono_contacto": "3187776655",
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": 6}],
        },
    )
    assert order3.status_code == 201
    cid_2 = order3.json()["cliente_id"]
    assert cid_2 != cid_1


def test_create_order_with_multiple_details_and_catalog_calculations(
    api_client, auth_headers: dict[str, str]
):
    # Pedido individual con 2 detalles: 5 Hayacas ($10.000 c/u = $50.000) + 3 Lechonas ($12.000 c/u = $36.000)
    resp = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Restaurante Los Centauros",
            "fecha_pedido": "2026-11-04T08:30:00",
            "fecha_entrega_prevista": "2026-11-07T11:30:00",
            "estado": "confirmado",
            "modalidad_entrega": "domicilio",
            "direccion_entrega": "Av. 40 # 15-20",
            "telefono_contacto": "3154445566",
            "observaciones": "Entregar caliente en recepción",
            "detalles": [
                {"producto_nombre": "Hayaca", "cantidad": 5},
                {"producto_nombre": "Lechona", "cantidad": 3},
            ],
        },
    )
    assert resp.status_code == 201
    order = resp.json()
    assert order["modalidad_entrega"] == "domicilio"
    assert order["direccion_entrega"] == "Av. 40 # 15-20"
    assert order["telefono_contacto"] == "3154445566"
    assert order["es_historico"] is False
    assert order["origen_registro"] == "operativo"
    assert Decimal(order["cantidad_total_base"]) == Decimal("8.000")
    assert Decimal(order["total"]) == Decimal("86000.00")
    assert len(order["detalles"]) == 2

    by_prod = {d["producto_nombre"]: d for d in order["detalles"]}
    assert by_prod["Hayaca"]["unidad_base"] == "Unidad"
    assert Decimal(by_prod["Hayaca"]["precio_unitario"]) == Decimal("10000.00")
    assert Decimal(by_prod["Hayaca"]["subtotal"]) == Decimal("50000.00")
    assert by_prod["Lechona"]["unidad_base"] == "Plato"
    assert Decimal(by_prod["Lechona"]["precio_unitario"]) == Decimal("12000.00")
    assert Decimal(by_prod["Lechona"]["subtotal"]) == Decimal("36000.00")

    # Consultar detalles del pedido por endpoint específico
    det_resp = api_client.get(
        f"/pedidos/{order['id']}/detalles", headers=auth_headers
    )
    assert det_resp.status_code == 200
    assert len(det_resp.json()) == 2


def test_order_validations_for_domicilio_products_and_quantities(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    # 1. Modalidad domicilio sin dirección -> 422
    no_addr = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Pedro Gómez",
            "fecha_entrega_prevista": "2026-11-08T12:00:00",
            "modalidad_entrega": "domicilio",
            "telefono_contacto": "3100001111",
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": 2}],
        },
    )
    assert no_addr.status_code == 422

    # 2. Modalidad domicilio sin teléfono -> 422
    no_phone = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Pedro Gómez",
            "fecha_entrega_prevista": "2026-11-08T12:00:00",
            "modalidad_entrega": "domicilio",
            "direccion_entrega": "Carrera 10 # 5-12",
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": 2}],
        },
    )
    assert no_phone.status_code == 422

    # 3. Cantidad fraccionaria o <= 0 -> 422
    bad_qty = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Pedro Gómez",
            "fecha_entrega_prevista": "2026-11-08T12:00:00",
            "modalidad_entrega": "retiro",
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": "2.5"}],
        },
    )
    assert bad_qty.status_code == 422

    # 4. Producto inexistente -> 404
    bad_prod = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Pedro Gómez",
            "fecha_entrega_prevista": "2026-11-08T12:00:00",
            "modalidad_entrega": "retiro",
            "detalles": [{"producto_nombre": "Tamal Tolimense", "cantidad": 2}],
        },
    )
    assert bad_prod.status_code == 404

    # 5. Presentación no individual es rechazada (los pedidos nuevos son individuales)
    lechona = isolated_session.scalar(
        text("SELECT id FROM productos WHERE nombre = 'Lechona'")
    )
    cojin = Presentacion(
        producto_id=int(lechona),
        nombre="cojin_30",
        unidad_venta="Cojin",
        factor_conversion=Decimal("30.0000"),
        precio_actual=Decimal("320000.00"),
        activo=True,
    )
    isolated_session.add(cojin)
    isolated_session.commit()

    non_indiv = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Pedro Gómez",
            "fecha_entrega_prevista": "2026-11-08T12:00:00",
            "modalidad_entrega": "retiro",
            "detalles": [{"presentacion_id": cojin.id, "cantidad": 1}],
        },
    )
    assert non_indiv.status_code == 400


def test_update_operational_order_and_protect_historical_orders(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    # Crear pedido operativo nuevo
    created = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Laura Camila Díaz",
            "fecha_pedido": "2026-11-05T08:00:00",
            "fecha_entrega_prevista": "2026-11-07T12:00:00",
            "modalidad_entrega": "retiro",
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": 3}],
        },
    ).json()
    order_id = created["id"]

    # Cambiar a domicilio sin teléfono/dirección falla con 422
    bad_patch = api_client.patch(
        f"/pedidos/{order_id}",
        headers=auth_headers,
        json={"modalidad_entrega": "domicilio"},
    )
    assert bad_patch.status_code == 422

    # Actualizar a domicilio con datos válidos, nuevo detalle y estado 'en_preparacion'
    updated = api_client.patch(
        f"/pedidos/{order_id}",
        headers=auth_headers,
        json={
            "estado": "en_preparacion",
            "modalidad_entrega": "domicilio",
            "direccion_entrega": "Calle 20 # 8-15",
            "telefono_contacto": "3129876543",
            "detalles": [
                {"producto_nombre": "Hayaca", "cantidad": 4},
                {"producto_nombre": "Lechona", "cantidad": 2},
            ],
        },
    )
    assert updated.status_code == 200
    upd_data = updated.json()
    assert upd_data["estado"] == "en_preparacion"
    assert upd_data["modalidad_entrega"] == "domicilio"
    assert Decimal(upd_data["total"]) == Decimal("64000.00")

    # Marcar como entregado y verificar que ya no permite modificaciones posteriores
    delivered = api_client.patch(
        f"/pedidos/{order_id}",
        headers=auth_headers,
        json={"estado": "entregado"},
    )
    assert delivered.status_code == 200

    after_delivered = api_client.patch(
        f"/pedidos/{order_id}",
        headers=auth_headers,
        json={"observaciones": "Intento posterior"},
    )
    assert after_delivered.status_code == 409

    # Simular un pedido histórico importado y comprobar que es inmutable y diferenciable
    trace = build_trace_tag(hoja="Pedidos", fila=850, es_sintetico=False)
    hist_client = Cliente(
        nombre="Yolanda Franco",
        notas=trace,
        activo=True,
    )
    isolated_session.add(hist_client)
    isolated_session.flush()

    hayaca_pres = isolated_session.scalar(
        text(
            "SELECT pr.id FROM presentaciones pr JOIN productos p ON p.id = pr.producto_id WHERE p.nombre = 'Hayaca'"
        )
    )
    hist_order = Pedido(
        cliente_id=hist_client.id,
        fecha_pedido=datetime(2026, 6, 2, 0, 0),
        fecha_entrega_prevista=datetime(2026, 6, 6, 0, 0),
        estado="entregado",
        observaciones=trace,
    )
    isolated_session.add(hist_order)
    isolated_session.flush()
    isolated_session.add(
        DetallePedido(
            pedido_id=hist_order.id,
            presentacion_id=int(hayaca_pres),
            cantidad=Decimal("4.000"),
            precio_unitario=Decimal("10000.00"),
            factor_conversion_snapshot=Decimal("1.0000"),
            observaciones=trace,
        )
    )
    isolated_session.commit()

    # El pedido histórico se identifica como histórico real y no permite edición
    hist_get = api_client.get(f"/pedidos/{hist_order.id}", headers=auth_headers).json()
    assert hist_get["es_historico"] is True
    assert hist_get["es_sintetico"] is False
    assert hist_get["origen_registro"] == "historico_real"

    hist_patch = api_client.patch(
        f"/pedidos/{hist_order.id}",
        headers=auth_headers,
        json={"estado": "pendiente"},
    )
    assert hist_patch.status_code == 409

    # El filtro solo_operativos excluye los históricos
    only_op = api_client.get(
        "/pedidos?solo_operativos=true", headers=auth_headers
    ).json()
    assert [o["id"] for o in only_op] == [order_id]

    # Eliminar un pedido histórico o un pedido ya entregado está prohibido (409)
    del_hist = api_client.delete(
        f"/pedidos/{hist_order.id}", headers=auth_headers
    )
    assert del_hist.status_code == 409

    del_delivered = api_client.delete(
        f"/pedidos/{order_id}", headers=auth_headers
    )
    assert del_delivered.status_code == 409

    # Un pedido operativo nuevo en estado pendiente sí puede eliminarse
    removable = api_client.post(
        "/pedidos",
        headers=auth_headers,
        json={
            "cliente_nombre": "Cliente Temporal",
            "fecha_entrega_prevista": "2026-11-09T12:00:00",
            "modalidad_entrega": "retiro",
            "detalles": [{"producto_nombre": "Hayaca", "cantidad": 2}],
        },
    ).json()
    del_ok = api_client.delete(
        f"/pedidos/{removable['id']}", headers=auth_headers
    )
    assert del_ok.status_code == 204
    assert (
        api_client.get(
            f"/pedidos/{removable['id']}", headers=auth_headers
        ).status_code
        == 404
    )


def test_end_to_end_admin_init_login_and_orders_flow(
    api_client, isolated_session: Session, monkeypatch
):
    """Flujo integral E2E: inicializar admin -> login -> /auth/me -> crear cliente/pedido -> consultar y actualizar."""
    monkeypatch.setenv("ADMIN_INITIAL_USERNAME", "admin.e2e")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "ClaveE2ESuperSegura#2026")
    monkeypatch.setenv("ADMIN_INITIAL_FULL_NAME", "Administrador E2E")

    init_res = initialize_admin_from_env(isolated_session, commit=True)
    assert init_res.creado is True

    login_resp = api_client.post(
        "/auth/login",
        json={
            "nombre_usuario": "admin.e2e",
            "password": "ClaveE2ESuperSegura#2026",
        },
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_resp = api_client.get("/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["nombre_usuario"] == "admin.e2e"

    # Crear pedido con cliente nuevo por texto libre y domicilio
    create_resp = api_client.post(
        "/pedidos",
        headers=headers,
        json={
            "cliente_nombre": "Doña Gloria Villavicencio",
            "fecha_pedido": "2026-11-05T10:00:00",
            "fecha_entrega_prevista": "2026-11-08T12:30:00",
            "modalidad_entrega": "domicilio",
            "direccion_entrega": "Cra 33 # 18-09",
            "telefono_contacto": "3145556677",
            "detalles": [
                {"producto_nombre": "Hayaca", "cantidad": 6},
                {"producto_nombre": "Lechona", "cantidad": 4},
            ],
        },
    )
    assert create_resp.status_code == 201
    created_order = create_resp.json()
    assert Decimal(created_order["total"]) == Decimal("108000.00")

    # Consultar listado de clientes y pedidos con el mismo token
    clientes_list = api_client.get("/clientes", headers=headers).json()
    assert len(clientes_list) == 1
    assert clientes_list[0]["nombre"] == "Doña Gloria Villavicencio"

    pedidos_list = api_client.get("/pedidos", headers=headers).json()
    assert len(pedidos_list) == 1
    assert pedidos_list[0]["id"] == created_order["id"]



def test_historical_mysql_data_remains_intact():
    """Verifica directamente en la base de datos real que los 5.183 registros históricos
    importados en la Fase 3 permanecen intactos."""
    engine = get_engine()
    trace_pattern = {"p": "%IMPORTACION_EXCEL|%"}
    with engine.connect() as conn:
        counts = {
            "productos": conn.execute(text("SELECT COUNT(*) FROM productos")).scalar(),
            "presentaciones": conn.execute(
                text("SELECT COUNT(*) FROM presentaciones")
            ).scalar(),
            "clientes": conn.execute(
                text("SELECT COUNT(*) FROM clientes WHERE notas LIKE :p"),
                trace_pattern,
            ).scalar(),
            "pedidos": conn.execute(
                text("SELECT COUNT(*) FROM pedidos WHERE observaciones LIKE :p"),
                trace_pattern,
            ).scalar(),
            "detalle_pedidos": conn.execute(
                text(
                    "SELECT COUNT(*) FROM detalle_pedidos WHERE observaciones LIKE :p"
                ),
                trace_pattern,
            ).scalar(),
            "ventas": conn.execute(
                text("SELECT COUNT(*) FROM ventas WHERE observaciones LIKE :p"),
                trace_pattern,
            ).scalar(),
            "detalle_ventas": conn.execute(
                text(
                    "SELECT dv_count FROM (SELECT COUNT(*) AS dv_count FROM detalle_ventas dv JOIN ventas v ON v.id = dv.venta_id WHERE v.observaciones LIKE :p) t"
                ),
                trace_pattern,
            ).scalar(),
            "producciones": conn.execute(
                text("SELECT COUNT(*) FROM producciones WHERE observaciones LIKE :p"),
                trace_pattern,
            ).scalar(),
            "cierres_diarios": conn.execute(
                text(
                    "SELECT COUNT(*) FROM cierres_diarios WHERE observaciones LIKE :p"
                ),
                trace_pattern,
            ).scalar(),
            "movimientos_inventario": conn.execute(
                text(
                    "SELECT COUNT(*) FROM movimientos_inventario WHERE observaciones LIKE :p"
                ),
                trace_pattern,
            ).scalar(),
        }
    assert counts == {
        "productos": 2,
        "presentaciones": 2,
        "clientes": 207,
        "pedidos": 1040,
        "detalle_pedidos": 1040,
        "ventas": 482,
        "detalle_ventas": 482,
        "producciones": 482,
        "cierres_diarios": 482,
        "movimientos_inventario": 964,
    }
