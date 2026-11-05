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
    CierreDiario,
    MovimientoInventario,
    Produccion,
    Producto,
    Usuario,
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
        nombre_usuario="admin.produccion",
        nombre_completo="Administradora Producción",
        password_hash=hash_password("ClaveSeguraProduccion2026!"),
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


def test_production_routes_require_authentication(api_client):
    assert api_client.get("/producciones").status_code == 401
    assert (
        api_client.post(
            "/producciones",
            json={
                "producto_nombre": "Hayaca",
                "cantidad_producida_base": 50,
                "sobrante_real_base": 5,
            },
        ).status_code
        == 401
    )
    assert (
        api_client.patch(
            "/producciones/1", json={"sobrante_real_base": 3}
        ).status_code
        == 401
    )
    assert api_client.delete("/producciones/1").status_code == 401


def test_create_production_syncs_inventory_and_cierre_diario(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    # Crear una venta concretada el mismo día para verificar cálculo de existencia_calculada_base
    sale_resp = api_client.post(
        "/ventas",
        headers=auth_headers,
        json={
            "fecha_venta": "2026-11-04T11:30:00",
            "estado": "concretada",
            "detalles": [
                {"producto_nombre": "Hayaca", "cantidad": 18},
            ],
        },
    )
    assert sale_resp.status_code == 201

    # Crear producción de Hayaca (Unidad) y Lechona (Plato)
    hayaca_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Hayaca",
            "fecha_produccion": "2026-11-04T08:00:00",
            "cantidad_producida_base": 60,
            "sobrante_real_base": 42,
            "observaciones": "Producción matutina de Hayacas",
        },
    )
    assert hayaca_resp.status_code == 201, hayaca_resp.text
    hayaca_data = hayaca_resp.json()
    assert hayaca_data["producto_nombre"] == "Hayaca"
    assert hayaca_data["unidad_base"] == "Unidad"
    assert Decimal(str(hayaca_data["cantidad_producida_base"])) == Decimal("60.000")
    assert Decimal(str(hayaca_data["cantidad_vendida_fecha"])) == Decimal("18.000")
    assert Decimal(str(hayaca_data["existencia_calculada_base"])) == Decimal("42.000")
    assert Decimal(str(hayaca_data["sobrante_real_base"])) == Decimal("42.000")
    assert Decimal(str(hayaca_data["diferencia_base"])) == Decimal("0.000")
    assert hayaca_data["es_historico"] is False
    assert hayaca_data["origen_registro"] == "operativo"

    lechona_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Lechona",
            "fecha_produccion": "2026-11-04T09:00:00",
            "cantidad_producida_base": 45,
            "sobrante_real_base": 10,
            "observaciones": "Horneado de Lechona",
        },
    )
    assert lechona_resp.status_code == 201, lechona_resp.text
    lechona_data = lechona_resp.json()
    assert lechona_data["producto_nombre"] == "Lechona"
    assert lechona_data["unidad_base"] == "Plato"
    assert Decimal(str(lechona_data["cantidad_producida_base"])) == Decimal("45.000")
    assert Decimal(str(lechona_data["sobrante_real_base"])) == Decimal("10.000")

    # Verificar sincronización con movimientos_inventario y cierres_diarios
    movs = list(
        isolated_session.scalars(
            select(MovimientoInventario).where(
                MovimientoInventario.tipo == "produccion"
            )
        ).all()
    )
    assert len(movs) == 2
    by_prod_id = {m.produccion_id: m for m in movs}
    assert Decimal(by_prod_id[hayaca_data["id"]].cantidad_base) == Decimal("60.000")
    assert Decimal(by_prod_id[lechona_data["id"]].cantidad_base) == Decimal("45.000")

    cierres = list(isolated_session.scalars(select(CierreDiario)).all())
    assert len(cierres) == 2


def test_production_validations_reject_invalid_quantities_and_products(
    api_client,
    auth_headers: dict[str, str],
):
    # Sobrante mayor que cantidad producida
    exceed_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Hayaca",
            "cantidad_producida_base": 20,
            "sobrante_real_base": 25,
        },
    )
    assert exceed_resp.status_code == 422

    # Cantidad producida <= 0
    zero_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Hayaca",
            "cantidad_producida_base": 0,
            "sobrante_real_base": 0,
        },
    )
    assert zero_resp.status_code == 422

    # Cantidad fraccionaria
    frac_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Lechona",
            "cantidad_producida_base": "15.5",
            "sobrante_real_base": 2,
        },
    )
    assert frac_resp.status_code == 422

    # Producto inexistente
    not_found_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Tamal",
            "cantidad_producida_base": 30,
            "sobrante_real_base": 4,
        },
    )
    assert not_found_resp.status_code == 404


def test_update_and_delete_operational_production_syncs_movements_and_closures(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    create_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Hayaca",
            "fecha_produccion": "2026-11-05T08:00:00",
            "cantidad_producida_base": 50,
            "sobrante_real_base": 8,
        },
    )
    assert create_resp.status_code == 201
    prod_id = create_resp.json()["id"]

    # Actualizar cantidad producida y sobrantes
    patch_resp = api_client.patch(
        f"/producciones/{prod_id}",
        headers=auth_headers,
        json={
            "cantidad_producida_base": 75,
            "sobrante_real_base": 12,
            "observaciones": "Ajuste de tanda",
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    updated = patch_resp.json()
    assert Decimal(str(updated["cantidad_producida_base"])) == Decimal("75.000")
    assert Decimal(str(updated["sobrante_real_base"])) == Decimal("12.000")
    assert updated["observaciones"] == "Ajuste de tanda"

    mov = isolated_session.scalar(
        select(MovimientoInventario).where(
            MovimientoInventario.produccion_id == prod_id
        )
    )
    assert mov is not None
    assert Decimal(mov.cantidad_base) == Decimal("75.000")

    # Eliminar registro operativo y comprobar limpieza de movimiento y cierre diario
    del_resp = api_client.delete(
        f"/producciones/{prod_id}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 204
    assert (
        api_client.get(
            f"/producciones/{prod_id}", headers=auth_headers
        ).status_code
        == 404
    )
    assert (
        isolated_session.scalar(
            select(MovimientoInventario).where(
                MovimientoInventario.produccion_id == prod_id
            )
        )
        is None
    )
    assert (
        isolated_session.scalar(
            select(CierreDiario).where(
                CierreDiario.fecha == datetime(2026, 11, 5).date()
            )
        )
        is None
    )


def test_historical_production_and_closures_are_protected_with_409(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    hayaca = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Hayaca")
    )
    assert hayaca is not None

    hist_tag = build_trace_tag(
        hoja="Consolidado historico",
        fila=120,
        es_sintetico=False,
    )
    hist_prod = Produccion(
        producto_id=hayaca.id,
        fecha_produccion=datetime(2026, 10, 25, 8, 0, 0),
        cantidad_producida_base=Decimal("90.000"),
        observaciones=hist_tag,
    )
    hist_cierre = CierreDiario(
        producto_id=hayaca.id,
        fecha=datetime(2026, 10, 25).date(),
        existencia_calculada_base=Decimal("6.000"),
        sobrante_real_base=Decimal("6.000"),
        observaciones=hist_tag,
    )
    isolated_session.add_all([hist_prod, hist_cierre])
    isolated_session.commit()

    # No debe permitir editar ni eliminar producción histórica
    assert (
        api_client.patch(
            f"/producciones/{hist_prod.id}",
            headers=auth_headers,
            json={"sobrante_real_base": 4},
        ).status_code
        == 409
    )
    assert (
        api_client.delete(
            f"/producciones/{hist_prod.id}",
            headers=auth_headers,
        ).status_code
        == 409
    )

    # Tampoco debe permitir sobrescribir una jornada con cierre histórico importado
    assert (
        api_client.post(
            "/producciones",
            headers=auth_headers,
            json={
                "producto_nombre": "Hayaca",
                "fecha_produccion": "2026-10-25T14:00:00",
                "cantidad_producida_base": 30,
                "sobrante_real_base": 2,
            },
        ).status_code
        == 409
    )


def test_list_producciones_filters_by_product_date_and_origin(
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

    synth_tag = build_trace_tag(
        hoja="Consolidado historico",
        fila=15,
        es_sintetico=True,
    )
    real_hist_tag = build_trace_tag(
        hoja="Consolidado historico",
        fila=210,
        es_sintetico=False,
    )

    p_synth = Produccion(
        producto_id=hayaca.id,
        fecha_produccion=datetime(2025, 3, 15, 8, 0, 0),
        cantidad_producida_base=Decimal("80.000"),
        observaciones=synth_tag,
    )
    p_hist = Produccion(
        producto_id=lechona.id,
        fecha_produccion=datetime(2026, 8, 16, 8, 0, 0),
        cantidad_producida_base=Decimal("55.000"),
        observaciones=real_hist_tag,
    )
    isolated_session.add_all([p_synth, p_hist])
    isolated_session.commit()

    # Crear además 1 registro operativo
    op_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Hayaca",
            "fecha_produccion": "2026-11-04T08:00:00",
            "cantidad_producida_base": 65,
            "sobrante_real_base": 5,
        },
    )
    assert op_resp.status_code == 201

    all_items = api_client.get("/producciones", headers=auth_headers).json()
    assert len(all_items) == 3

    only_op = api_client.get(
        "/producciones?solo_operativos=true", headers=auth_headers
    ).json()
    assert len(only_op) == 1
    assert only_op[0]["origen_registro"] == "operativo"

    no_synth = api_client.get(
        "/producciones?incluir_sinteticos=false", headers=auth_headers
    ).json()
    assert len(no_synth) == 2

    only_lechona = api_client.get(
        "/producciones?producto_nombre=Lechona", headers=auth_headers
    ).json()
    assert len(only_lechona) == 1
    assert only_lechona[0]["producto_nombre"] == "Lechona"

    # Filtros por rango de fechas
    by_date = api_client.get(
        "/producciones?fecha_desde=2026-08-01&fecha_hasta=2026-10-31",
        headers=auth_headers,
    ).json()
    assert len(by_date) == 1
    assert by_date[0]["id"] == p_hist.id

    # Paginación (limit y offset)
    page1 = api_client.get(
        "/producciones?limit=1&offset=0", headers=auth_headers
    ).json()
    page2 = api_client.get(
        "/producciones?limit=1&offset=1", headers=auth_headers
    ).json()
    assert len(page1) == 1
    assert len(page2) == 1
    assert page1[0]["id"] != page2[0]["id"]


def test_base_unit_validation_and_no_duplicate_movements(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    # Crear registro y actualizarlo varias veces verificando que solo exista 1 movimiento
    create_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Lechona",
            "fecha_produccion": "2026-11-06T08:00:00",
            "cantidad_producida_base": 40,
            "sobrante_real_base": 5,
        },
    )
    assert create_resp.status_code == 201
    prod_id = create_resp.json()["id"]
    assert create_resp.json()["unidad_base"] == "Plato"

    for new_qty, new_leftovers in ((55, 6), (60, 4), (48, 3)):
        upd = api_client.patch(
            f"/producciones/{prod_id}",
            headers=auth_headers,
            json={
                "cantidad_producida_base": new_qty,
                "sobrante_real_base": new_leftovers,
            },
        )
        assert upd.status_code == 200

    movs = list(
        isolated_session.scalars(
            select(MovimientoInventario).where(
                MovimientoInventario.produccion_id == prod_id
            )
        ).all()
    )
    assert len(movs) == 1
    assert Decimal(movs[0].cantidad_base) == Decimal("48.000")

    # Intento inválido de actualización (sobrantes > cantidad) no debe alterar los datos previos
    bad_upd = api_client.patch(
        f"/producciones/{prod_id}",
        headers=auth_headers,
        json={"sobrante_real_base": 99},
    )
    assert bad_upd.status_code == 422

    current = api_client.get(
        f"/producciones/{prod_id}", headers=auth_headers
    ).json()
    assert Decimal(str(current["cantidad_producida_base"])) == Decimal("48.000")
    assert Decimal(str(current["sobrante_real_base"])) == Decimal("3.000")

    # Si la unidad base de un producto es alterada en catálogo, el servicio rechaza la operación
    lechona = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Lechona")
    )
    assert lechona is not None
    lechona.unidad_base = "Kilogramo"
    isolated_session.flush()

    bad_unit_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Lechona",
            "fecha_produccion": "2026-11-07T08:00:00",
            "cantidad_producida_base": 30,
            "sobrante_real_base": 2,
        },
    )
    assert bad_unit_resp.status_code == 400


def test_frontend_production_integration_and_historical_mysql_integrity():
    storage_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "production"
        / "services"
        / "productionStorage.js"
    ).read_text(encoding="utf-8")
    hook_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "production"
        / "hooks"
        / "useProductionRecords.js"
    ).read_text(encoding="utf-8")
    page_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "production"
        / "pages"
        / "ProductionPage.jsx"
    ).read_text(encoding="utf-8")
    analytics_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "production"
        / "utils"
        / "productionAnalytics.js"
    ).read_text(encoding="utf-8")
    validation_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "production"
        / "utils"
        / "validateProductionRecord.js"
    ).read_text(encoding="utf-8")

    # Conecta con /producciones mediante apiRequest y limpia únicamente sabores-del-llano-production-v1
    assert "apiRequest" in storage_code
    assert "/producciones" in storage_code
    assert "sabores-del-llano-production-v1" in storage_code
    assert "localStorage.removeItem" in storage_code
    assert "localStorage.clear" not in storage_code

    # Hook asíncrono y filtros 'all', 'week', '15days', 'month'
    assert "getProductionRecords" in hook_code
    assert "createProductionRecord" in hook_code
    assert "Todo el historial" in page_code
    for period_key in ("all", "week", "15days", "month"):
        assert re.search(rf"['\"]{period_key}['\"]", page_code)
    assert "period === 'all'" in analytics_code

    # Validación leftovers <= quantity en frontend
    assert "Number(form.leftovers) > Number(form.quantity)" in validation_code

    # Verificar que los 482 registros históricos reales en MySQL permanecen intactos
    engine = get_engine()
    with engine.connect() as conn:
        hist_prod_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM producciones WHERE observaciones LIKE '%IMPORTACION_EXCEL|%'"
            )
        ).scalar_one()
        hist_cierres_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM cierres_diarios WHERE observaciones LIKE '%IMPORTACION_EXCEL|%'"
            )
        ).scalar_one()
        hist_mov_prod_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM movimientos_inventario WHERE tipo = 'produccion' AND observaciones LIKE '%IMPORTACION_EXCEL|%'"
            )
        ).scalar_one()

    assert hist_prod_count == 482
    assert hist_cierres_count == 482
    assert hist_mov_prod_count == 482


def test_production_edit_and_delete_actions_and_history_protection(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    """
    Verifica los requerimientos de MEDIO-03:
    1. Existencia e integración de DeleteProductionDialog y ProductionFormModal con soporte de edición.
    2. Columna Acciones en ProductionHistory mostrando 'Solo lectura' para registros históricos
       y botones de editar/eliminar para registros operativos.
    3. Flujo funcional: actualización de producción operativa sincroniza inventario y cierre diario.
    4. Eliminación de producción operativa elimina movimiento y recalcula cierre diario.
    5. Protección estricta: PATCH y DELETE sobre registros históricos devuelven 409 Conflict.
    """
    page_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "production"
        / "pages"
        / "ProductionPage.jsx"
    ).read_text(encoding="utf-8")
    modal_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "production"
        / "components"
        / "ProductionFormModal.jsx"
    ).read_text(encoding="utf-8")
    dialog_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "production"
        / "components"
        / "DeleteProductionDialog.jsx"
    ).read_text(encoding="utf-8")
    css_code = (
        PROJECT_ROOT
        / "src"
        / "styles"
        / "index.css"
    ).read_text(encoding="utf-8")

    # 1. Componentes y columna de acciones
    assert "DeleteProductionDialog" in page_code
    assert "onEdit=" in page_code
    assert "onDelete=" in page_code
    assert "Acciones" in page_code
    assert "Solo lectura" in page_code
    assert "status-badge" in page_code
    assert "EditIcon" in page_code
    assert "TrashIcon" in page_code

    # 2. Modal con soporte para edición y precarga
    assert "isEditing" in modal_code
    assert "Editar producción" in modal_code
    assert "Registrar producción" in modal_code
    assert "Guardar cambios" in modal_code
    assert "production-product-fixed" in modal_code
    assert "Unidad" in modal_code
    assert "Plato" in modal_code
    assert "isSaving" in modal_code

    # 3. Diálogo de confirmación de eliminación
    assert "¿Eliminar registro de producción?" in dialog_code
    assert "orders-confirm-dialog" in dialog_code
    assert "Eliminar producción" in dialog_code
    assert "isDeleting" in dialog_code

    # 4. Estilos de tabla y acciones
    assert ".production-table__actions-heading" in css_code
    assert ".production-table__actions" in css_code

    # 5. Flujo en Backend: Crear registro operativo, actualizarlo y eliminarlo
    create_resp = api_client.post(
        "/producciones",
        headers=auth_headers,
        json={
            "producto_nombre": "Hayaca",
            "fecha_produccion": "2026-11-09T08:00:00",
            "cantidad_producida_base": 75,
            "sobrante_real_base": 8,
        },
    )
    assert create_resp.status_code == 201
    prod_data = create_resp.json()
    prod_id = prod_data["id"]
    assert prod_data["es_historico"] is False
    assert prod_data["origen_registro"] == "operativo"

    # Editar registro operativo
    update_resp = api_client.patch(
        f"/producciones/{prod_id}",
        headers=auth_headers,
        json={
            "cantidad_producida_base": 85,
            "sobrante_real_base": 10,
        },
    )
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert Decimal(str(updated_data["cantidad_producida_base"])) == Decimal("85.000")
    assert Decimal(str(updated_data["sobrante_real_base"])) == Decimal("10.000")

    # Validar que inventario y cierre diario se hayan sincronizado
    mov = isolated_session.scalar(
        select(MovimientoInventario).where(
            MovimientoInventario.produccion_id == prod_id
        )
    )
    assert mov is not None
    assert Decimal(mov.cantidad_base) == Decimal("85.000")

    cierre = isolated_session.scalar(
        select(CierreDiario).where(
            CierreDiario.fecha == datetime(2026, 11, 9).date(),
            CierreDiario.producto_id == prod_data["producto_id"],
        )
    )
    assert cierre is not None
    assert Decimal(cierre.sobrante_real_base) == Decimal("10.000")

    # Rechazo en caso de intento de modificación de registro histórico
    hayaca = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Hayaca")
    )
    hist_tag = build_trace_tag(
        hoja="Consolidado historico",
        fila=180,
        es_sintetico=False,
    )
    hist_prod = Produccion(
        producto_id=hayaca.id,
        fecha_produccion=datetime(2026, 10, 26, 8, 0, 0),
        cantidad_producida_base=Decimal("90.000"),
        observaciones=hist_tag,
    )
    isolated_session.add(hist_prod)
    isolated_session.commit()

    bad_hist_patch = api_client.patch(
        f"/producciones/{hist_prod.id}",
        headers=auth_headers,
        json={"cantidad_producida_base": 999},
    )
    assert bad_hist_patch.status_code == 409
    assert "históricos" in bad_hist_patch.json()["detail"]

    bad_hist_del = api_client.delete(
        f"/producciones/{hist_prod.id}",
        headers=auth_headers,
    )
    assert bad_hist_del.status_code == 409
    assert "históricos" in bad_hist_del.json()["detail"]

    # Eliminar registro operativo
    del_resp = api_client.delete(
        f"/producciones/{prod_id}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 204

    # Verificar que el registro operativo fue eliminado y su movimiento limpiado
    assert (
        isolated_session.scalar(
            select(Produccion).where(Produccion.id == prod_id)
        )
        is None
    )
    assert (
        isolated_session.scalar(
            select(MovimientoInventario).where(
                MovimientoInventario.produccion_id == prod_id
            )
        )
        is None
    )


