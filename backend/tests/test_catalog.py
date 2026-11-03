from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db, get_engine
from app.main import app
from app.models import Presentacion, Producto
from app.services.catalog import seed_initial_catalog


@pytest.fixture
def catalog_session():
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
def catalog_client(client, catalog_session):
    def override_get_db():
        yield catalog_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_seed_initial_catalog_is_idempotent(catalog_client):
    first = catalog_client.post("/catalogo/inicializar")
    assert first.status_code == 200
    data1 = first.json()
    assert data1["productos_creados"] == ["Hayaca", "Lechona"]
    assert data1["productos_existentes"] == []
    assert data1["presentaciones_creadas"] == [
        "Hayaca:individual",
        "Lechona:individual",
    ]
    assert data1["presentaciones_existentes"] == []
    assert data1["revisiones_manuales"] == []

    # Segunda ejecución: no duplica ni sobrescribe
    second = catalog_client.post("/catalogo/inicializar")
    assert second.status_code == 200
    data2 = second.json()
    assert data2["productos_creados"] == []
    assert data2["productos_existentes"] == ["Hayaca", "Lechona"]
    assert data2["presentaciones_creadas"] == []
    assert data2["presentaciones_existentes"] == [
        "Hayaca:individual",
        "Lechona:individual",
    ]
    assert data2["revisiones_manuales"] == []

    productos = catalog_client.get("/productos").json()
    assert len(productos) == 2
    by_name = {p["nombre"]: p for p in productos}
    assert by_name["Hayaca"]["unidad_base"] == "Unidad"
    assert Decimal(by_name["Hayaca"]["presentaciones"][0]["precio_actual"]) == Decimal(
        "10000.00"
    )
    assert by_name["Lechona"]["unidad_base"] == "Plato"
    assert Decimal(by_name["Lechona"]["presentaciones"][0]["precio_actual"]) == Decimal(
        "12000.00"
    )


def test_seed_initial_catalog_does_not_overwrite_existing_price_and_warns(
    catalog_session,
):
    hayaca = Producto(nombre="Hayaca", unidad_base="Unidad", activo=True)
    catalog_session.add(hayaca)
    catalog_session.flush()
    custom_pres = Presentacion(
        producto_id=hayaca.id,
        nombre="individual",
        unidad_venta="Unidad",
        factor_conversion=Decimal("1.0000"),
        precio_actual=Decimal("11500.00"),
        activo=True,
    )
    extra_prod = Producto(nombre="Tamal", unidad_base="Unidad", activo=True)
    catalog_session.add_all([custom_pres, extra_prod])
    catalog_session.commit()

    result = seed_initial_catalog(catalog_session)

    assert result.productos_creados == ["Lechona"]
    assert result.productos_existentes == ["Hayaca"]
    assert result.presentaciones_creadas == ["Lechona:individual"]
    assert result.presentaciones_existentes == ["Hayaca:individual"]

    # Verifica que el precio personalizado NO fue sobrescrito
    catalog_session.refresh(custom_pres)
    assert Decimal(custom_pres.precio_actual) == Decimal("11500.00")

    # Verifica advertencias de revisión manual (precio distinto y producto extra)
    warning_fields = {(w.entidad, w.nombre, w.campo) for w in result.revisiones_manuales}
    assert ("presentacion", "Hayaca:individual", "precio_actual") in warning_fields
    assert ("producto", "Tamal", "nombre") in warning_fields


def test_create_update_and_filter_productos(catalog_client):
    create_resp = catalog_client.post(
        "/productos",
        json={
            "nombre": "Hayaca",
            "descripcion": "Hayaca tradicional llanera",
            "unidad_base": "Unidad",
            "activo": True,
        },
    )
    assert create_resp.status_code == 201
    hayaca = create_resp.json()
    assert hayaca["nombre"] == "Hayaca"
    assert hayaca["unidad_base"] == "Unidad"
    assert hayaca["activo"] is True

    # Duplicado devuelve 409
    dup_resp = catalog_client.post(
        "/productos",
        json={"nombre": "Hayaca", "unidad_base": "Unidad"},
    )
    assert dup_resp.status_code == 409

    # Crear segundo producto inactivo
    lechona_resp = catalog_client.post(
        "/productos",
        json={"nombre": "Lechona", "unidad_base": "Plato", "activo": False},
    )
    assert lechona_resp.status_code == 201
    lechona_id = lechona_resp.json()["id"]

    # Consultar todos vs consultar activos
    all_prods = catalog_client.get("/productos").json()
    assert len(all_prods) == 2

    active_prods = catalog_client.get("/productos/activos").json()
    assert [p["nombre"] for p in active_prods] == ["Hayaca"]

    active_query = catalog_client.get("/productos?solo_activos=true").json()
    assert [p["nombre"] for p in active_query] == ["Hayaca"]

    # Actualizar producto
    patch_resp = catalog_client.patch(
        f"/productos/{lechona_id}",
        json={"activo": True, "descripcion": "Lechona tradicional"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["activo"] is True
    assert patch_resp.json()["descripcion"] == "Lechona tradicional"


def test_create_update_and_query_presentaciones(catalog_client):
    prod = catalog_client.post(
        "/productos",
        json={"nombre": "Lechona", "unidad_base": "Plato"},
    ).json()
    prod_id = prod["id"]

    pres_resp = catalog_client.post(
        "/presentaciones",
        json={
            "producto_id": prod_id,
            "nombre": "individual",
            "unidad_venta": "Plato",
            "factor_conversion": "1.0000",
            "precio_actual": "12000.00",
            "activo": True,
        },
    )
    assert pres_resp.status_code == 201
    pres = pres_resp.json()
    pres_id = pres["id"]
    assert Decimal(pres["precio_actual"]) == Decimal("12000.00")

    # Duplicado para el mismo producto devuelve 409
    dup_pres = catalog_client.post(
        "/presentaciones",
        json={
            "producto_id": prod_id,
            "nombre": "individual",
            "unidad_venta": "Plato",
            "factor_conversion": "1.0000",
            "precio_actual": "12000.00",
        },
    )
    assert dup_pres.status_code == 409

    # Consultar presentaciones por producto
    by_prod = catalog_client.get(f"/productos/{prod_id}/presentaciones").json()
    assert len(by_prod) == 1
    assert by_prod[0]["id"] == pres_id

    # Actualizar presentación
    upd_resp = catalog_client.patch(
        f"/presentaciones/{pres_id}",
        json={"precio_actual": "12500.00"},
    )
    assert upd_resp.status_code == 200
    assert Decimal(upd_resp.json()["precio_actual"]) == Decimal("12500.00")


def test_catalog_validations_reject_invalid_payloads(catalog_client):
    # Nombre vacío o en blanco
    bad_prod = catalog_client.post(
        "/productos",
        json={"nombre": "   ", "unidad_base": "Unidad"},
    )
    assert bad_prod.status_code == 422

    prod = catalog_client.post(
        "/productos",
        json={"nombre": "Hayaca", "unidad_base": "Unidad"},
    ).json()

    # Factor de conversión <= 0
    bad_factor = catalog_client.post(
        "/presentaciones",
        json={
            "producto_id": prod["id"],
            "nombre": "individual",
            "unidad_venta": "Unidad",
            "factor_conversion": "0",
            "precio_actual": "10000",
        },
    )
    assert bad_factor.status_code == 422

    # Precio negativo
    bad_price = catalog_client.post(
        "/presentaciones",
        json={
            "producto_id": prod["id"],
            "nombre": "individual",
            "unidad_venta": "Unidad",
            "factor_conversion": "1",
            "precio_actual": "-100",
        },
    )
    assert bad_price.status_code == 422
