from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Presentacion, Producto
from app.schemas.catalog import (
    CatalogSeedResult,
    CatalogSeedWarning,
    PresentacionCreate,
    PresentacionUpdate,
    ProductoCreate,
    ProductoUpdate,
)


@dataclass(frozen=True)
class InitialCatalogEntry:
    nombre_producto: str
    unidad_base: str
    nombre_presentacion: str
    unidad_venta: str
    factor_conversion: Decimal
    precio_referencia: Decimal


# Catálogo inicial confirmado en las reglas de negocio y la hoja 'Productos'
# del Excel histórico (Sabores_del_Llano_Datos_Ampliados_Ajustado.xlsx):
# - Hayaca: Unidad base 'Unidad', presentación 'individual', factor 1, $10.000 COP
# - Lechona: Unidad base 'Plato', presentación 'individual', factor 1, $12.000 COP
INITIAL_CATALOG_ENTRIES: tuple[InitialCatalogEntry, ...] = (
    InitialCatalogEntry(
        nombre_producto="Hayaca",
        unidad_base="Unidad",
        nombre_presentacion="individual",
        unidad_venta="Unidad",
        factor_conversion=Decimal("1.0000"),
        precio_referencia=Decimal("10000.00"),
    ),
    InitialCatalogEntry(
        nombre_producto="Lechona",
        unidad_base="Plato",
        nombre_presentacion="individual",
        unidad_venta="Plato",
        factor_conversion=Decimal("1.0000"),
        precio_referencia=Decimal("12000.00"),
    ),
)


def list_productos(
    session: Session, *, solo_activos: bool = False
) -> list[Producto]:
    stmt = (
        select(Producto)
        .options(selectinload(Producto.presentaciones))
        .order_by(Producto.id)
    )
    if solo_activos:
        stmt = stmt.where(Producto.activo.is_(True))
    return list(session.scalars(stmt).all())


def get_producto_or_404(session: Session, producto_id: int) -> Producto:
    stmt = (
        select(Producto)
        .options(selectinload(Producto.presentaciones))
        .where(Producto.id == producto_id)
    )
    producto = session.scalar(stmt)
    if producto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el producto con id {producto_id}.",
        )
    return producto


def create_producto(session: Session, payload: ProductoCreate) -> Producto:
    existing = session.scalar(
        select(Producto).where(Producto.nombre == payload.nombre)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un producto con el nombre '{payload.nombre}'.",
        )
    producto = Producto(
        nombre=payload.nombre,
        descripcion=payload.descripcion,
        unidad_base=payload.unidad_base,
        activo=payload.activo,
    )
    session.add(producto)
    session.commit()
    session.refresh(producto)
    return get_producto_or_404(session, producto.id)


def update_producto(
    session: Session, producto_id: int, payload: ProductoUpdate
) -> Producto:
    producto = get_producto_or_404(session, producto_id)
    updates = payload.model_dump(exclude_unset=True)

    if "nombre" in updates and updates["nombre"] != producto.nombre:
        duplicate = session.scalar(
            select(Producto).where(
                Producto.nombre == updates["nombre"], Producto.id != producto_id
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un producto con el nombre '{updates['nombre']}'.",
            )

    for field_name, field_value in updates.items():
        setattr(producto, field_name, field_value)

    session.commit()
    session.refresh(producto)
    return get_producto_or_404(session, producto.id)


def list_presentaciones(
    session: Session,
    *,
    producto_id: int | None = None,
    solo_activas: bool = False,
) -> list[Presentacion]:
    if producto_id is not None:
        get_producto_or_404(session, producto_id)

    stmt = select(Presentacion).order_by(Presentacion.producto_id, Presentacion.id)
    if producto_id is not None:
        stmt = stmt.where(Presentacion.producto_id == producto_id)
    if solo_activas:
        stmt = stmt.where(Presentacion.activo.is_(True))
    return list(session.scalars(stmt).all())


def get_presentacion_or_404(session: Session, presentacion_id: int) -> Presentacion:
    presentacion = session.get(Presentacion, presentacion_id)
    if presentacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró la presentación con id {presentacion_id}.",
        )
    return presentacion


def create_presentacion(
    session: Session, payload: PresentacionCreate
) -> Presentacion:
    get_producto_or_404(session, payload.producto_id)
    duplicate = session.scalar(
        select(Presentacion).where(
            Presentacion.producto_id == payload.producto_id,
            Presentacion.nombre == payload.nombre,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya existe la presentación '{payload.nombre}' "
                f"para el producto {payload.producto_id}."
            ),
        )
    presentacion = Presentacion(
        producto_id=payload.producto_id,
        nombre=payload.nombre,
        unidad_venta=payload.unidad_venta,
        factor_conversion=payload.factor_conversion,
        precio_actual=payload.precio_actual,
        activo=payload.activo,
    )
    session.add(presentacion)
    session.commit()
    session.refresh(presentacion)
    return presentacion


def update_presentacion(
    session: Session, presentacion_id: int, payload: PresentacionUpdate
) -> Presentacion:
    presentacion = get_presentacion_or_404(session, presentacion_id)
    updates = payload.model_dump(exclude_unset=True)

    if "nombre" in updates and updates["nombre"] != presentacion.nombre:
        duplicate = session.scalar(
            select(Presentacion).where(
                Presentacion.producto_id == presentacion.producto_id,
                Presentacion.nombre == updates["nombre"],
                Presentacion.id != presentacion_id,
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Ya existe la presentación '{updates['nombre']}' "
                    f"para el producto {presentacion.producto_id}."
                ),
            )

    for field_name, field_value in updates.items():
        setattr(presentacion, field_name, field_value)

    session.commit()
    session.refresh(presentacion)
    return presentacion


def seed_initial_catalog(
    session: Session, *, commit: bool = True
) -> CatalogSeedResult:
    """Registra Hayaca y Lechona junto con sus presentaciones base de forma idempotente.

    - No duplica productos ni presentaciones si se ejecuta múltiples veces.
    - No sobrescribe precios ni atributos existentes en la base de datos.
    - Informa en `revisiones_manuales` cualquier diferencia detectada en registros
      preexistentes o productos adicionales no contemplados en la semilla inicial.
    """
    result = CatalogSeedResult()
    expected_product_names = {entry.nombre_producto for entry in INITIAL_CATALOG_ENTRIES}

    for entry in INITIAL_CATALOG_ENTRIES:
        producto = session.scalar(
            select(Producto).where(Producto.nombre == entry.nombre_producto)
        )
        if producto is None:
            producto = Producto(
                nombre=entry.nombre_producto,
                descripcion=None,
                unidad_base=entry.unidad_base,
                activo=True,
            )
            session.add(producto)
            session.flush()
            result.productos_creados.append(entry.nombre_producto)
        else:
            result.productos_existentes.append(entry.nombre_producto)
            if producto.unidad_base != entry.unidad_base:
                result.revisiones_manuales.append(
                    CatalogSeedWarning(
                        entidad="producto",
                        nombre=entry.nombre_producto,
                        campo="unidad_base",
                        valor_actual=str(producto.unidad_base),
                        valor_esperado=entry.unidad_base,
                        mensaje=(
                            f"El producto '{entry.nombre_producto}' tiene unidad_base "
                            f"'{producto.unidad_base}' en lugar de '{entry.unidad_base}'. "
                            "No se sobrescribió automáticamente."
                        ),
                    )
                )
            if not producto.activo:
                result.revisiones_manuales.append(
                    CatalogSeedWarning(
                        entidad="producto",
                        nombre=entry.nombre_producto,
                        campo="activo",
                        valor_actual=str(producto.activo),
                        valor_esperado="True",
                        mensaje=(
                            f"El producto '{entry.nombre_producto}' se encuentra inactivo. "
                            "No se modificó automáticamente."
                        ),
                    )
                )

        presentacion_key = f"{entry.nombre_producto}:{entry.nombre_presentacion}"
        presentacion = session.scalar(
            select(Presentacion).where(
                Presentacion.producto_id == producto.id,
                Presentacion.nombre == entry.nombre_presentacion,
            )
        )
        if presentacion is None:
            presentacion = Presentacion(
                producto_id=producto.id,
                nombre=entry.nombre_presentacion,
                unidad_venta=entry.unidad_venta,
                factor_conversion=entry.factor_conversion,
                precio_actual=entry.precio_referencia,
                activo=True,
            )
            session.add(presentacion)
            session.flush()
            result.presentaciones_creadas.append(presentacion_key)
        else:
            result.presentaciones_existentes.append(presentacion_key)
            if presentacion.unidad_venta != entry.unidad_venta:
                result.revisiones_manuales.append(
                    CatalogSeedWarning(
                        entidad="presentacion",
                        nombre=presentacion_key,
                        campo="unidad_venta",
                        valor_actual=str(presentacion.unidad_venta),
                        valor_esperado=entry.unidad_venta,
                        mensaje=(
                            f"La presentación '{presentacion_key}' tiene unidad_venta "
                            f"'{presentacion.unidad_venta}' en lugar de '{entry.unidad_venta}'. "
                            "No se sobrescribió automáticamente."
                        ),
                    )
                )
            if Decimal(presentacion.factor_conversion) != entry.factor_conversion:
                result.revisiones_manuales.append(
                    CatalogSeedWarning(
                        entidad="presentacion",
                        nombre=presentacion_key,
                        campo="factor_conversion",
                        valor_actual=str(presentacion.factor_conversion),
                        valor_esperado=str(entry.factor_conversion),
                        mensaje=(
                            f"La presentación '{presentacion_key}' tiene factor_conversion "
                            f"{presentacion.factor_conversion} en lugar de {entry.factor_conversion}. "
                            "No se sobrescribió automáticamente."
                        ),
                    )
                )
            if Decimal(presentacion.precio_actual) != entry.precio_referencia:
                result.revisiones_manuales.append(
                    CatalogSeedWarning(
                        entidad="presentacion",
                        nombre=presentacion_key,
                        campo="precio_actual",
                        valor_actual=str(presentacion.precio_actual),
                        valor_esperado=str(entry.precio_referencia),
                        mensaje=(
                            f"La presentación '{presentacion_key}' tiene precio_actual "
                            f"{presentacion.precio_actual} en lugar del precio de referencia "
                            f"{entry.precio_referencia}. No se sobrescribió automáticamente."
                        ),
                    )
                )
            if not presentacion.activo:
                result.revisiones_manuales.append(
                    CatalogSeedWarning(
                        entidad="presentacion",
                        nombre=presentacion_key,
                        campo="activo",
                        valor_actual=str(presentacion.activo),
                        valor_esperado="True",
                        mensaje=(
                            f"La presentación '{presentacion_key}' se encuentra inactiva. "
                            "No se modificó automáticamente."
                        ),
                    )
                )

    all_products = list(session.scalars(select(Producto).order_by(Producto.id)).all())
    for prod in all_products:
        if prod.nombre not in expected_product_names:
            result.revisiones_manuales.append(
                CatalogSeedWarning(
                    entidad="producto",
                    nombre=prod.nombre,
                    campo="nombre",
                    valor_actual=prod.nombre,
                    valor_esperado="Hayaca | Lechona",
                    mensaje=(
                        f"Se encontró el producto adicional '{prod.nombre}' que no forma parte "
                        "del catálogo inicial base. Requiere revisión manual."
                    ),
                )
            )

    if commit:
        session.commit()
    else:
        session.flush()
    return result
