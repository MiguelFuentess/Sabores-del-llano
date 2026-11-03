from __future__ import annotations

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db, get_engine
from app.models import (
    Base,
    CierreDiario,
    Cliente,
    DetallePedido,
    DetalleVenta,
    Gasto,
    MovimientoInventario,
    Pedido,
    Presentacion,
    Produccion,
    Producto,
    Usuario,
    Venta,
)

EXPECTED_TABLES = {
    "clientes",
    "usuarios",
    "productos",
    "presentaciones",
    "pedidos",
    "detalle_pedidos",
    "ventas",
    "detalle_ventas",
    "producciones",
    "movimientos_inventario",
    "cierres_diarios",
    "gastos",
}


def test_all_12_models_are_registered_in_metadata():
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES
    assert len(Base.metadata.tables) == 12


def test_models_define_expected_foreign_keys_and_rules():
    presentaciones_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in Presentacion.__table__.foreign_keys
    }
    assert presentaciones_fks == {
        "fk_presentaciones_producto": ("productos.id", "RESTRICT", "CASCADE"),
    }

    pedidos_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in Pedido.__table__.foreign_keys
    }
    assert pedidos_fks == {
        "pedidos_ibfk_1": ("clientes.id", "RESTRICT", "CASCADE"),
    }

    detalle_pedidos_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in DetallePedido.__table__.foreign_keys
    }
    assert detalle_pedidos_fks == {
        "detalle_pedidos_ibfk_1": ("pedidos.id", "CASCADE", "CASCADE"),
        "detalle_pedidos_ibfk_2": ("presentaciones.id", "RESTRICT", "CASCADE"),
    }

    ventas_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in Venta.__table__.foreign_keys
    }
    assert ventas_fks == {
        "ventas_ibfk_1": ("pedidos.id", "RESTRICT", "CASCADE"),
    }

    detalle_ventas_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in DetalleVenta.__table__.foreign_keys
    }
    assert detalle_ventas_fks == {
        "detalle_ventas_ibfk_1": ("ventas.id", "CASCADE", "CASCADE"),
        "detalle_ventas_ibfk_2": ("presentaciones.id", "RESTRICT", "CASCADE"),
    }

    producciones_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in Produccion.__table__.foreign_keys
    }
    assert producciones_fks == {
        "producciones_ibfk_1": ("productos.id", "RESTRICT", "CASCADE"),
    }

    movimientos_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in MovimientoInventario.__table__.foreign_keys
    }
    assert movimientos_fks == {
        "fk_movimientos_producto": ("productos.id", "RESTRICT", "CASCADE"),
        "fk_movimientos_produccion": ("producciones.id", "RESTRICT", "CASCADE"),
        "fk_movimientos_detalle_venta": ("detalle_ventas.id", "RESTRICT", "CASCADE"),
    }

    cierres_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in CierreDiario.__table__.foreign_keys
    }
    assert cierres_fks == {
        "fk_cierres_producto": ("productos.id", "RESTRICT", "CASCADE"),
        "fk_cierres_usuario": ("usuarios.id", "SET NULL", "CASCADE"),
    }

    gastos_fks = {
        fk.name: (fk.target_fullname, fk.ondelete, fk.onupdate)
        for fk in Gasto.__table__.foreign_keys
    }
    assert gastos_fks == {
        "fk_gastos_usuario": ("usuarios.id", "SET NULL", "CASCADE"),
    }


def test_models_define_enums_checks_and_computed_column():
    assert Pedido.__table__.c.estado.type.enums == [
        "pendiente",
        "confirmado",
        "en_preparacion",
        "entregado",
        "cancelado",
    ]
    assert Venta.__table__.c.estado.type.enums == ["concretada", "anulada"]
    assert MovimientoInventario.__table__.c.tipo.type.enums == [
        "saldo_inicial",
        "produccion",
        "venta",
        "ajuste_entrada",
        "ajuste_salida",
    ]
    assert Gasto.__table__.c.categoria.type.enums == [
        "ingredientes",
        "empaques",
        "servicios",
        "transporte",
        "equipos",
        "otros",
    ]
    assert Gasto.__table__.c.tipo.type.enums == ["gasto", "inversion"]

    diff_col = CierreDiario.__table__.c.diferencia_base
    assert diff_col.computed is not None
    assert diff_col.computed.persisted is True


def test_models_match_physical_mysql_schema_and_read_queries(client):
    settings = get_settings()
    if not settings.database_url:
        pytest.skip("DATABASE_URL no está configurada.")

    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"MySQL no accesible en este entorno de ejecución: {exc}")

    inspector = inspect(engine)
    db_tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(db_tables)

    for table_name, orm_table in Base.metadata.tables.items():
        db_cols = {col["name"]: col for col in inspector.get_columns(table_name)}
        orm_cols = {col.name: col for col in orm_table.columns}
        assert set(orm_cols.keys()) == set(db_cols.keys()), (
            f"Diferencia de columnas en {table_name}"
        )

        for col_name, orm_col in orm_cols.items():
            if orm_col.primary_key or orm_col.computed is not None:
                continue
            assert orm_col.nullable == db_cols[col_name]["nullable"], (
                f"Diferencia de nulabilidad en {table_name}.{col_name}"
            )

        pk_constraint = inspector.get_pk_constraint(table_name)
        orm_pks = [col.name for col in orm_table.primary_key.columns]
        assert orm_pks == pk_constraint["constrained_columns"]

        db_fks = {
            fk["name"]: (
                f"{fk['referred_table']}.{fk['referred_columns'][0]}",
                fk.get("options", {}).get("ondelete", "RESTRICT"),
                fk.get("options", {}).get("onupdate", "RESTRICT"),
            )
            for fk in inspector.get_foreign_keys(table_name)
        }
        orm_fks = {
            fk.name: (
                fk.target_fullname,
                fk.ondelete or "RESTRICT",
                fk.onupdate or "RESTRICT",
            )
            for fk in orm_table.foreign_keys
        }
        assert orm_fks == db_fks, f"Diferencia de claves foráneas en {table_name}"

    # Verificar creación/cierre de sesión con get_db() y lectura de las 12 tablas
    db_gen = get_db()
    session = next(db_gen)
    try:
        assert isinstance(session, Session)
        for model in (
            Cliente,
            Usuario,
            Producto,
            Presentacion,
            Pedido,
            DetallePedido,
            Venta,
            DetalleVenta,
            Produccion,
            MovimientoInventario,
            CierreDiario,
            Gasto,
        ):
            rows = session.scalars(select(model).limit(1)).all()
            assert isinstance(rows, list)
    finally:
        with pytest.raises(StopIteration):
            next(db_gen)

    # Verificar health check real contra MySQL sin exponer credenciales
    health_resp = client.get("/health/db")
    assert health_resp.status_code == 200
    body = health_resp.json()
    assert body == {"status": "ok", "database": "reachable"}
    assert "mysql" not in str(body).lower()
    assert "password" not in str(body).lower()
