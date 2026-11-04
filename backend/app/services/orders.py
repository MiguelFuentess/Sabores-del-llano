from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Cliente, DetallePedido, Pedido, Presentacion, Producto
from app.schemas.orders import (
    DetallePedidoItemInput,
    DetallePedidoResponse,
    ModalidadEntregaLiteral,
    PedidoCreate,
    PedidoResponse,
    PedidoUpdate,
)
from app.services.customers import (
    classify_trace_origin,
    resolve_or_create_cliente_for_order,
)

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


def _load_pedido_query():
    return select(Pedido).options(
        selectinload(Pedido.cliente),
        selectinload(Pedido.venta),
        selectinload(Pedido.detalles)
        .selectinload(DetallePedido.presentacion)
        .selectinload(Presentacion.producto),
    )


def get_pedido_Model_or_404(session: Session, pedido_id: int) -> Pedido:
    stmt = _load_pedido_query().where(Pedido.id == pedido_id)
    pedido = session.scalar(stmt)
    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El pedido con id {pedido_id} no existe.",
        )
    return pedido


def derive_modalidad_entrega(pedido: Pedido) -> ModalidadEntregaLiteral:
    if pedido.direccion_entrega and pedido.direccion_entrega.strip():
        return "domicilio"
    return "retiro"


def serialize_detalle_pedido(detalle: DetallePedido) -> DetallePedidoResponse:
    presentacion = detalle.presentacion
    producto = presentacion.producto
    cantidad = Decimal(detalle.cantidad)
    precio_unitario = Decimal(detalle.precio_unitario)
    factor = Decimal(detalle.factor_conversion_snapshot)
    cantidad_base = (cantidad * factor).quantize(Decimal("0.001"))
    subtotal = (cantidad * precio_unitario).quantize(Decimal("0.01"))

    return DetallePedidoResponse(
        id=detalle.id,
        pedido_id=detalle.pedido_id,
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
        observaciones=detalle.observaciones,
    )


def serialize_pedido(pedido: Pedido) -> PedidoResponse:
    es_historico, es_sintetico, origen = classify_trace_origin(pedido.observaciones)
    detalles_resp = [serialize_detalle_pedido(d) for d in pedido.detalles]
    cantidad_total_base = sum(
        (d.cantidad_base for d in detalles_resp), Decimal("0.000")
    )
    total = sum((d.subtotal for d in detalles_resp), Decimal("0.00"))
    cliente_nombre = (
        pedido.cliente.nombre
        if pedido.cliente is not None
        else pedido.nombre_contacto
    )

    return PedidoResponse(
        id=pedido.id,
        cliente_id=pedido.cliente_id,
        cliente_nombre=cliente_nombre,
        fecha_pedido=pedido.fecha_pedido,
        fecha_entrega_prevista=pedido.fecha_entrega_prevista,
        estado=pedido.estado,  # type: ignore[arg-type]
        modalidad_entrega=derive_modalidad_entrega(pedido),
        nombre_contacto=pedido.nombre_contacto,
        telefono_contacto=pedido.telefono_contacto,
        direccion_entrega=pedido.direccion_entrega,
        observaciones=pedido.observaciones,
        es_historico=es_historico,
        es_sintetico=es_sintetico,
        origen_registro=origen,
        cantidad_total_base=cantidad_total_base,
        total=total,
        detalles=detalles_resp,
        creado_en=pedido.creado_en,
        actualizado_en=pedido.actualizado_en,
    )


def _resolve_presentacion_individual(
    session: Session, item: DetallePedidoItemInput
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
                "Los pedidos nuevos deben registrarse en presentación individual "
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


def list_pedidos(
    session: Session,
    *,
    q: str | None = None,
    estado: str | None = None,
    cliente_id: int | None = None,
    fecha_entrega_desde: date | None = None,
    fecha_entrega_hasta: date | None = None,
    incluir_historicos: bool = True,
    incluir_sinteticos: bool = True,
    solo_operativos: bool = False,
    limit: int = 2000,
    offset: int = 0,
) -> list[PedidoResponse]:
    stmt = _load_pedido_query().outerjoin(Cliente, Pedido.cliente_id == Cliente.id)

    if estado:
        stmt = stmt.where(Pedido.estado == estado)

    if cliente_id is not None:
        stmt = stmt.where(Pedido.cliente_id == cliente_id)

    if fecha_entrega_desde is not None:
        stmt = stmt.where(
            Pedido.fecha_entrega_prevista
            >= datetime.combine(fecha_entrega_desde, datetime.min.time())
        )
    if fecha_entrega_hasta is not None:
        stmt = stmt.where(
            Pedido.fecha_entrega_prevista
            <= datetime.combine(fecha_entrega_hasta, datetime.max.time())
        )

    if solo_operativos or not incluir_historicos:
        stmt = stmt.where(
            or_(
                Pedido.observaciones.is_(None),
                ~Pedido.observaciones.like("%IMPORTACION_EXCEL|%"),
            )
        )
    elif not incluir_sinteticos:
        stmt = stmt.where(
            or_(
                Pedido.observaciones.is_(None),
                ~Pedido.observaciones.like("%|es_sintetico=1%"),
            )
        )

    if q and q.strip():
        cleaned_q = q.strip()
        pattern = f"%{cleaned_q}%"
        conditions = [
            Cliente.nombre.ilike(pattern),
            Pedido.nombre_contacto.ilike(pattern),
            Pedido.direccion_entrega.ilike(pattern),
        ]
        numeric_id = cleaned_q.lstrip("#0")
        if numeric_id.isdigit():
            conditions.append(Pedido.id == int(numeric_id))
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.order_by(
        Pedido.fecha_entrega_prevista.desc(),
        Pedido.id.desc(),
    ).offset(offset).limit(limit)

    pedidos = session.scalars(stmt).all()
    return [serialize_pedido(p) for p in pedidos]


def get_pedido(session: Session, pedido_id: int) -> PedidoResponse:
    pedido = get_pedido_Model_or_404(session, pedido_id)
    return serialize_pedido(pedido)


def get_pedido_detalles(
    session: Session, pedido_id: int
) -> list[DetallePedidoResponse]:
    pedido = get_pedido_Model_or_404(session, pedido_id)
    return [serialize_detalle_pedido(d) for d in pedido.detalles]


def create_pedido(
    session: Session,
    payload: PedidoCreate,
    *,
    commit: bool = True,
) -> PedidoResponse:
    cliente = resolve_or_create_cliente_for_order(
        session,
        cliente_id=payload.cliente_id,
        cliente_nombre=payload.cliente_nombre,
        telefono_contacto=payload.telefono_contacto,
        forzar_nuevo_cliente=payload.forzar_nuevo_cliente,
    )

    fecha_pedido = payload.fecha_pedido or datetime.now(timezone.utc).replace(
        tzinfo=None
    )
    if payload.fecha_entrega_prevista.date() < fecha_pedido.date():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de entrega prevista no puede ser anterior a la fecha del pedido.",
        )

    resolved_items: list[tuple[Presentacion, DetallePedidoItemInput]] = []
    for item in payload.detalles:
        pres = _resolve_presentacion_individual(session, item)
        resolved_items.append((pres, item))

    direccion_entrega = (
        payload.direccion_entrega if payload.modalidad_entrega == "domicilio" else None
    )
    nombre_contacto = payload.nombre_contacto or cliente.nombre

    pedido = Pedido(
        cliente_id=cliente.id,
        fecha_pedido=fecha_pedido,
        fecha_entrega_prevista=payload.fecha_entrega_prevista,
        estado=payload.estado,
        nombre_contacto=nombre_contacto,
        telefono_contacto=payload.telefono_contacto,
        direccion_entrega=direccion_entrega,
        observaciones=payload.observaciones,
    )
    session.add(pedido)
    session.flush()

    for pres, item in resolved_items:
        detalle = DetallePedido(
            pedido_id=pedido.id,
            presentacion_id=pres.id,
            cantidad=Decimal(int(item.cantidad)),
            precio_unitario=Decimal(pres.precio_actual),
            factor_conversion_snapshot=Decimal(pres.factor_conversion),
            observaciones=item.observaciones,
        )
        session.add(detalle)

    if commit:
        session.commit()
    else:
        session.flush()

    loaded = get_pedido_Model_or_404(session, pedido.id)
    return serialize_pedido(loaded)


def update_pedido(
    session: Session,
    pedido_id: int,
    payload: PedidoUpdate,
    *,
    commit: bool = True,
) -> PedidoResponse:
    pedido = get_pedido_Model_or_404(session, pedido_id)
    es_historico, _, _ = classify_trace_origin(pedido.observaciones)

    if es_historico:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se permite modificar ni duplicar pedidos históricos importados.",
        )

    if pedido.venta is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se permite modificar un pedido que ya tiene una venta registrada.",
        )

    if pedido.estado in {"entregado", "cancelado"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se permite modificar un pedido que ya se encuentra en estado '{pedido.estado}'.",
        )

    updates = payload.model_dump(exclude_unset=True)

    if (
        "fecha_entrega_prevista" in updates
        and updates["fecha_entrega_prevista"] is not None
    ):
        nueva_entrega: datetime = updates["fecha_entrega_prevista"]
        if nueva_entrega.date() < pedido.fecha_pedido.date():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de entrega prevista no puede ser anterior a la fecha del pedido.",
            )
        pedido.fecha_entrega_prevista = nueva_entrega

    current_modalidad = derive_modalidad_entrega(pedido)
    target_modalidad: ModalidadEntregaLiteral = (
        updates.get("modalidad_entrega") or current_modalidad
    )

    target_direccion = updates.get("direccion_entrega", pedido.direccion_entrega)
    target_telefono = updates.get("telefono_contacto", pedido.telefono_contacto)

    if target_modalidad == "domicilio":
        if not target_direccion or not target_direccion.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La dirección de entrega es obligatoria cuando la modalidad es domicilio.",
            )
        if not target_telefono or not target_telefono.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El teléfono de contacto es obligatorio cuando la modalidad es domicilio.",
            )
        pedido.direccion_entrega = target_direccion.strip()
        pedido.telefono_contacto = target_telefono.strip()
    else:
        pedido.direccion_entrega = None
        if "telefono_contacto" in updates:
            pedido.telefono_contacto = target_telefono

    if "nombre_contacto" in updates:
        pedido.nombre_contacto = updates["nombre_contacto"]

    if "observaciones" in updates:
        pedido.observaciones = updates["observaciones"]

    if "estado" in updates and updates["estado"] is not None:
        pedido.estado = updates["estado"]

    if payload.detalles is not None:
        resolved_items: list[tuple[Presentacion, DetallePedidoItemInput]] = []
        for item in payload.detalles:
            pres = _resolve_presentacion_individual(session, item)
            resolved_items.append((pres, item))

        pedido.detalles.clear()
        session.flush()
        for pres, item in resolved_items:
            pedido.detalles.append(
                DetallePedido(
                    presentacion_id=pres.id,
                    cantidad=Decimal(int(item.cantidad)),
                    precio_unitario=Decimal(pres.precio_actual),
                    factor_conversion_snapshot=Decimal(pres.factor_conversion),
                    observaciones=item.observaciones,
                )
            )

    if commit:
        session.commit()
    else:
        session.flush()

    loaded = get_pedido_Model_or_404(session, pedido.id)
    return serialize_pedido(loaded)


def delete_pedido(
    session: Session,
    pedido_id: int,
    *,
    commit: bool = True,
) -> None:
    pedido = get_pedido_Model_or_404(session, pedido_id)
    es_historico, _, _ = classify_trace_origin(pedido.observaciones)

    if es_historico:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se permite eliminar pedidos históricos importados.",
        )

    if pedido.venta is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se permite eliminar un pedido que ya tiene una venta registrada.",
        )

    if pedido.estado == "entregado":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se permite eliminar un pedido que ya fue entregado.",
        )

    session.delete(pedido)
    if commit:
        session.commit()
    else:
        session.flush()
