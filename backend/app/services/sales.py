from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DetalleVenta,
    MovimientoInventario,
    Pedido,
    Presentacion,
    Producto,
    Venta,
)
from app.schemas.sales import (
    DetalleVentaItemInput,
    DetalleVentaResponse,
    VentaCreate,
    VentaResponse,
    VentaUpdate,
)
from app.services.customers import classify_trace_origin

_PRODUCT_NAME_ALIASES = {
    "hayaca": "Hayaca",
    "hayacas": "Hayaca",
    "hayacas-individual": "Hayaca",
    "lechona": "Lechona",
    "lechona-personal": "Lechona",
}

_EXPECTED_BASE_UNITS = {
    "Hayaca": "Unidad",
    "Lechona": "Plato",
}


def _load_venta_query():
    return select(Venta).options(
        selectinload(Venta.pedido).selectinload(Pedido.cliente),
        selectinload(Venta.detalles)
        .selectinload(DetalleVenta.presentacion)
        .selectinload(Presentacion.producto),
        selectinload(Venta.detalles).selectinload(
            DetalleVenta.movimientos_inventario
        ),
    )


def get_venta_model_or_404(session: Session, venta_id: int) -> Venta:
    stmt = _load_venta_query().where(Venta.id == venta_id)
    venta = session.scalar(stmt)
    if venta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La venta con id {venta_id} no existe.",
        )
    return venta


def serialize_detalle_venta(detalle: DetalleVenta) -> DetalleVentaResponse:
    presentacion = detalle.presentacion
    producto = presentacion.producto
    cantidad = Decimal(detalle.cantidad)
    precio_unitario = Decimal(detalle.precio_unitario)
    factor = Decimal(detalle.factor_conversion_snapshot)
    cantidad_base = (cantidad * factor).quantize(Decimal("0.001"))
    subtotal = (cantidad * precio_unitario).quantize(Decimal("0.01"))

    return DetalleVentaResponse(
        id=detalle.id,
        venta_id=detalle.venta_id,
        presentacion_id=detalle.presentacion_id,
        producto_id=producto.id,
        producto_nombre=producto.nombre,
        presentacion_nombre=presentacion.nombre,
        unidad_base=producto.unidad_base,
        unidad_venta=presentacion.unidad_venta,
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        factor_conversion_snapshot=factor,
        cantidad_base=cantidad_base,
        subtotal=subtotal,
    )


def serialize_venta(venta: Venta) -> VentaResponse:
    es_historico, es_sintetico, origen = classify_trace_origin(venta.observaciones)
    detalles_resp = [serialize_detalle_venta(d) for d in venta.detalles]
    cantidad_total_base = sum(
        (d.cantidad_base for d in detalles_resp), Decimal("0.000")
    )
    total = sum((d.subtotal for d in detalles_resp), Decimal("0.00"))

    return VentaResponse(
        id=venta.id,
        pedido_id=venta.pedido_id,
        fecha_venta=venta.fecha_venta,
        estado=venta.estado,  # type: ignore[arg-type]
        observaciones=venta.observaciones,
        es_historico=es_historico,
        es_sintetico=es_sintetico,
        origen_registro=origen,
        cantidad_total_base=cantidad_total_base,
        total=total,
        detalles=detalles_resp,
        creado_en=venta.creado_en,
    )


def _resolve_presentacion_individual(
    session: Session, item: DetalleVentaItemInput
) -> Presentacion:
    presentacion: Presentacion | None = None

    if item.presentacion_id is not None:
        presentacion = session.scalar(
            select(Presentacion)
            .options(selectinload(Presentacion.producto))
            .where(Presentacion.id == item.presentacion_id)
        )
        if presentacion is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La presentación con id {item.presentacion_id} no existe.",
            )
        if (
            item.producto_id is not None
            and presentacion.producto_id != item.producto_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"La presentación {item.presentacion_id} no pertenece "
                    f"al producto {item.producto_id}."
                ),
            )
        if item.producto_nombre:
            canonical = _PRODUCT_NAME_ALIASES.get(
                item.producto_nombre.strip().lower(), item.producto_nombre.strip()
            )
            if presentacion.producto.nombre.lower() != canonical.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"La presentación {item.presentacion_id} no corresponde "
                        f"al producto '{item.producto_nombre}'."
                    ),
                )
    else:
        producto: Producto | None = None
        if item.producto_id is not None:
            producto = session.get(Producto, item.producto_id)
            if producto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"El producto con id {item.producto_id} no existe.",
                )
        elif item.producto_nombre:
            canonical = _PRODUCT_NAME_ALIASES.get(
                item.producto_nombre.strip().lower(), item.producto_nombre.strip()
            )
            producto = session.scalar(
                select(Producto).where(
                    func.lower(Producto.nombre) == canonical.lower()
                )
            )
            if producto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"El producto '{item.producto_nombre}' no existe en el catálogo.",
                )

        assert producto is not None
        presentacion = session.scalar(
            select(Presentacion)
            .options(selectinload(Presentacion.producto))
            .where(
                Presentacion.producto_id == producto.id,
                func.lower(Presentacion.nombre) == "individual",
            )
        )
        if presentacion is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"El producto '{producto.nombre}' no tiene una presentación "
                    "individual configurada en el catálogo."
                ),
            )

    producto = presentacion.producto
    if not producto.activo or not presentacion.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El producto '{producto.nombre}' o su presentación "
                f"'{presentacion.nombre}' se encuentra inactivo."
            ),
        )

    if presentacion.nombre.lower() != "individual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Las ventas deben registrarse en presentación individual "
                f"(recibido: '{presentacion.nombre}')."
            ),
        )

    expected_unit = _EXPECTED_BASE_UNITS.get(producto.nombre)
    if expected_unit and producto.unidad_base != expected_unit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"La unidad base de '{producto.nombre}' debe ser '{expected_unit}' "
                f"(actual: '{producto.unidad_base}')."
            ),
        )

    return presentacion


def _sync_inventory_movements_for_venta(
    session: Session, venta: Venta
) -> None:
    """Sincroniza los movimientos de inventario (tipo='venta') para los detalles de una venta."""
    for detalle in venta.detalles:
        existing_movs = list(
            session.scalars(
                select(MovimientoInventario)
                .where(MovimientoInventario.detalle_venta_id == detalle.id)
                .order_by(MovimientoInventario.id.asc())
            ).all()
        )
        if venta.estado != "concretada":
            for mov in existing_movs:
                session.delete(mov)
            continue

        cantidad_base = (
            Decimal(detalle.cantidad) * Decimal(detalle.factor_conversion_snapshot)
        ).quantize(Decimal("0.001"))
        producto_id = detalle.presentacion.producto_id

        if existing_movs:
            primary = existing_movs[0]
            primary.producto_id = producto_id
            primary.tipo = "venta"
            primary.fecha_movimiento = venta.fecha_venta
            primary.cantidad_base = cantidad_base
            primary.observaciones = f"Salida por venta operativa #{venta.id}"
            for extra in existing_movs[1:]:
                session.delete(extra)
        else:
            session.add(
                MovimientoInventario(
                    producto_id=producto_id,
                    produccion_id=None,
                    detalle_venta_id=detalle.id,
                    tipo="venta",
                    fecha_movimiento=venta.fecha_venta,
                    cantidad_base=cantidad_base,
                    observaciones=f"Salida por venta operativa #{venta.id}",
                )
            )
    session.flush()


def _clear_inventory_movements_for_venta(
    session: Session, venta: Venta
) -> None:
    """Elimina los movimientos de inventario asociados a los detalles de una venta antes de borrarlos."""
    detalle_ids = [d.id for d in venta.detalles if d.id is not None]
    if detalle_ids:
        session.execute(
            delete(MovimientoInventario).where(
                MovimientoInventario.detalle_venta_id.in_(detalle_ids)
            )
        )
        session.flush()


def list_ventas(
    session: Session,
    *,
    q: str | None = None,
    estado: str | None = None,
    producto_id: int | None = None,
    producto_nombre: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    incluir_historicos: bool = True,
    incluir_sinteticos: bool = True,
    solo_operativos: bool = False,
    limit: int = 2000,
    offset: int = 0,
) -> list[VentaResponse]:
    stmt = _load_venta_query()

    if estado:
        stmt = stmt.where(Venta.estado == estado)

    if fecha_desde is not None:
        stmt = stmt.where(
            Venta.fecha_venta >= datetime.combine(fecha_desde, datetime.min.time())
        )
    if fecha_hasta is not None:
        stmt = stmt.where(
            Venta.fecha_venta <= datetime.combine(fecha_hasta, datetime.max.time())
        )

    if producto_id is not None:
        stmt = stmt.where(
            Venta.detalles.any(
                DetalleVenta.presentacion.has(Presentacion.producto_id == producto_id)
            )
        )
    elif producto_nombre and producto_nombre.strip():
        canonical = _PRODUCT_NAME_ALIASES.get(
            producto_nombre.strip().lower(), producto_nombre.strip()
        )
        stmt = stmt.where(
            Venta.detalles.any(
                DetalleVenta.presentacion.has(
                    Presentacion.producto.has(
                        func.lower(Producto.nombre) == canonical.lower()
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

    if q and q.strip():
        cleaned_q = q.strip()
        pattern = f"%{cleaned_q}%"
        conditions = [
            Venta.observaciones.ilike(pattern),
            Venta.detalles.any(
                DetalleVenta.presentacion.has(
                    Presentacion.producto.has(Producto.nombre.ilike(pattern))
                )
            ),
        ]
        numeric_id = cleaned_q.lstrip("#0")
        if numeric_id.isdigit():
            conditions.append(Venta.id == int(numeric_id))
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.order_by(
        Venta.fecha_venta.desc(),
        Venta.id.desc(),
    ).offset(offset).limit(limit)

    ventas = session.scalars(stmt).all()
    return [serialize_venta(v) for v in ventas]


def get_venta(session: Session, venta_id: int) -> VentaResponse:
    venta = get_venta_model_or_404(session, venta_id)
    return serialize_venta(venta)


def get_venta_detalles(
    session: Session, venta_id: int
) -> list[DetalleVentaResponse]:
    venta = get_venta_model_or_404(session, venta_id)
    return [serialize_detalle_venta(d) for d in venta.detalles]


def create_venta(
    session: Session,
    payload: VentaCreate,
    *,
    commit: bool = True,
) -> VentaResponse:
    pedido: Pedido | None = None
    if payload.pedido_id is not None:
        pedido = session.get(Pedido, payload.pedido_id)
        if pedido is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El pedido con id {payload.pedido_id} no existe.",
            )
        es_hist_pedido, _, _ = classify_trace_origin(pedido.observaciones)
        if es_hist_pedido:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se permite vincular nuevas ventas a pedidos históricos importados.",
            )
        existing_venta_id = session.scalar(
            select(Venta.id).where(Venta.pedido_id == payload.pedido_id)
        )
        if existing_venta_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El pedido #{payload.pedido_id} ya tiene una venta asociada.",
            )
        if pedido.estado == "cancelado":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No se puede registrar una venta para el pedido #{payload.pedido_id} porque está cancelado.",
            )

    fecha_venta = payload.fecha_venta or datetime.now(timezone.utc).replace(
        tzinfo=None
    )

    resolved_items: list[tuple[Presentacion, DetalleVentaItemInput, Decimal]] = []
    for item in payload.detalles:
        pres = _resolve_presentacion_individual(session, item)
        unit_price = (
            Decimal(item.precio_unitario)
            if item.precio_unitario is not None
            else Decimal(pres.precio_actual)
        )
        resolved_items.append((pres, item, unit_price))

    venta = Venta(
        pedido_id=payload.pedido_id,
        fecha_venta=fecha_venta,
        estado=payload.estado,
        observaciones=payload.observaciones,
    )
    session.add(venta)
    session.flush()

    for pres, item, unit_price in resolved_items:
        detalle = DetalleVenta(
            venta_id=venta.id,
            presentacion_id=pres.id,
            cantidad=Decimal(int(item.cantidad)),
            precio_unitario=unit_price,
            factor_conversion_snapshot=Decimal(pres.factor_conversion),
        )
        detalle.presentacion = pres
        session.add(detalle)
        venta.detalles.append(detalle)

    session.flush()

    if pedido is not None and payload.estado == "concretada":
        pedido.estado = "entregado"

    _sync_inventory_movements_for_venta(session, venta)

    if commit:
        session.commit()
    else:
        session.flush()

    loaded = get_venta_model_or_404(session, venta.id)
    return serialize_venta(loaded)


def update_venta(
    session: Session,
    venta_id: int,
    payload: VentaUpdate,
    *,
    commit: bool = True,
) -> VentaResponse:
    venta = get_venta_model_or_404(session, venta_id)
    es_historico, _, _ = classify_trace_origin(venta.observaciones)

    if es_historico:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se permite modificar ni duplicar ventas históricas importadas.",
        )

    updates = payload.model_dump(exclude_unset=True)

    if "fecha_venta" in updates and updates["fecha_venta"] is not None:
        venta.fecha_venta = updates["fecha_venta"]

    if "observaciones" in updates:
        venta.observaciones = updates["observaciones"]

    if "estado" in updates and updates["estado"] is not None:
        venta.estado = updates["estado"]

    if payload.detalles is not None:
        resolved_items: list[tuple[Presentacion, DetalleVentaItemInput, Decimal]] = []
        for item in payload.detalles:
            pres = _resolve_presentacion_individual(session, item)
            unit_price = (
                Decimal(item.precio_unitario)
                if item.precio_unitario is not None
                else Decimal(pres.precio_actual)
            )
            resolved_items.append((pres, item, unit_price))

        _clear_inventory_movements_for_venta(session, venta)
        venta.detalles.clear()
        session.flush()

        for pres, item, unit_price in resolved_items:
            detalle = DetalleVenta(
                venta_id=venta.id,
                presentacion_id=pres.id,
                cantidad=Decimal(int(item.cantidad)),
                precio_unitario=unit_price,
                factor_conversion_snapshot=Decimal(pres.factor_conversion),
            )
            detalle.presentacion = pres
            venta.detalles.append(detalle)
        session.flush()

    loaded_for_sync = get_venta_model_or_404(session, venta.id)
    _sync_inventory_movements_for_venta(session, loaded_for_sync)

    if commit:
        session.commit()
    else:
        session.flush()

    loaded = get_venta_model_or_404(session, venta.id)
    return serialize_venta(loaded)


def delete_venta(
    session: Session,
    venta_id: int,
    *,
    commit: bool = True,
) -> None:
    venta = get_venta_model_or_404(session, venta_id)
    es_historico, _, _ = classify_trace_origin(venta.observaciones)

    if es_historico:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se permite eliminar ventas históricas importadas.",
        )

    _clear_inventory_movements_for_venta(session, venta)
    session.delete(venta)

    if commit:
        session.commit()
    else:
        session.flush()
