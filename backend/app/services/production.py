from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CierreDiario,
    DetalleVenta,
    MovimientoInventario,
    Presentacion,
    Produccion,
    Producto,
    Venta,
)
from app.schemas.production import (
    ProduccionCreate,
    ProduccionResponse,
    ProduccionUpdate,
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


def _load_produccion_query():
    return select(Produccion).options(
        selectinload(Produccion.producto),
        selectinload(Produccion.movimientos_inventario),
    )


def get_produccion_model_or_404(
    session: Session, produccion_id: int
) -> Produccion:
    stmt = _load_produccion_query().where(Produccion.id == produccion_id)
    produccion = session.scalar(stmt)
    if produccion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El registro de producción con id {produccion_id} no existe.",
        )
    return produccion


def _resolve_producto(
    session: Session,
    *,
    producto_id: int | None,
    producto_nombre: str | None,
) -> Producto:
    producto: Producto | None = None
    if producto_id is not None:
        producto = session.get(Producto, producto_id)
        if producto is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El producto con id {producto_id} no existe.",
            )
    elif producto_nombre:
        canonical = _PRODUCT_NAME_ALIASES.get(
            producto_nombre.strip().lower(), producto_nombre.strip()
        )
        producto = session.scalar(
            select(Producto).where(
                func.lower(Producto.nombre) == canonical.lower()
            )
        )
        if producto is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El producto '{producto_nombre}' no existe en el catálogo.",
            )

    assert producto is not None
    if not producto.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El producto '{producto.nombre}' se encuentra inactivo.",
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

    return producto


def _compute_daily_produced_base(
    session: Session, producto_id: int, fecha_jornada: date
) -> Decimal:
    start_dt = datetime.combine(fecha_jornada, datetime.min.time())
    end_dt = datetime.combine(fecha_jornada, datetime.max.time())
    total = session.scalar(
        select(func.coalesce(func.sum(Produccion.cantidad_producida_base), 0)).where(
            Produccion.producto_id == producto_id,
            Produccion.fecha_produccion >= start_dt,
            Produccion.fecha_produccion <= end_dt,
        )
    )
    return Decimal(total or 0).quantize(Decimal("0.001"))


def _compute_daily_sold_base(
    session: Session, producto_id: int, fecha_jornada: date
) -> Decimal:
    start_dt = datetime.combine(fecha_jornada, datetime.min.time())
    end_dt = datetime.combine(fecha_jornada, datetime.max.time())
    total = session.scalar(
        select(
            func.coalesce(
                func.sum(
                    DetalleVenta.cantidad * DetalleVenta.factor_conversion_snapshot
                ),
                0,
            )
        )
        .join(Venta, Venta.id == DetalleVenta.venta_id)
        .join(Presentacion, Presentacion.id == DetalleVenta.presentacion_id)
        .where(
            Presentacion.producto_id == producto_id,
            Venta.estado == "concretada",
            Venta.fecha_venta >= start_dt,
            Venta.fecha_venta <= end_dt,
        )
    )
    return Decimal(total or 0).quantize(Decimal("0.001"))


def _sync_inventory_movement_for_produccion(
    session: Session, produccion: Produccion
) -> None:
    existing_movs = list(
        session.scalars(
            select(MovimientoInventario)
            .where(MovimientoInventario.produccion_id == produccion.id)
            .order_by(MovimientoInventario.id.asc())
        ).all()
    )
    cantidad_base = Decimal(produccion.cantidad_producida_base).quantize(
        Decimal("0.001")
    )
    if existing_movs:
        primary = existing_movs[0]
        primary.producto_id = produccion.producto_id
        primary.tipo = "produccion"
        primary.fecha_movimiento = produccion.fecha_produccion
        primary.cantidad_base = cantidad_base
        primary.observaciones = (
            f"Entrada por producción operativa #{produccion.id}"
        )
        for extra in existing_movs[1:]:
            session.delete(extra)
    else:
        session.add(
            MovimientoInventario(
                producto_id=produccion.producto_id,
                produccion_id=produccion.id,
                detalle_venta_id=None,
                tipo="produccion",
                fecha_movimiento=produccion.fecha_produccion,
                cantidad_base=cantidad_base,
                observaciones=f"Entrada por producción operativa #{produccion.id}",
            )
        )
    session.flush()


def _clear_inventory_movement_for_produccion(
    session: Session, produccion: Produccion
) -> None:
    session.execute(
        delete(MovimientoInventario).where(
            MovimientoInventario.produccion_id == produccion.id
        )
    )
    session.flush()


def _sync_cierre_diario_for_date(
    session: Session,
    *,
    producto_id: int,
    fecha_jornada: date,
    sobrante_real_base: Decimal | None,
    usuario_id: int | None,
) -> CierreDiario | None:
    cierre = session.scalar(
        select(CierreDiario).where(
            CierreDiario.producto_id == producto_id,
            CierreDiario.fecha == fecha_jornada,
        )
    )

    total_producido = _compute_daily_produced_base(
        session, producto_id, fecha_jornada
    )
    total_vendido = _compute_daily_sold_base(
        session, producto_id, fecha_jornada
    )
    existencia_calc = max(
        Decimal("0.000"),
        (total_producido - total_vendido).quantize(Decimal("0.001")),
    )

    if total_producido <= Decimal("0.000"):
        if cierre is not None:
            session.delete(cierre)
            session.flush()
        return None

    target_sobrante = (
        Decimal(sobrante_real_base).quantize(Decimal("0.001"))
        if sobrante_real_base is not None
        else (
            Decimal(cierre.sobrante_real_base).quantize(Decimal("0.001"))
            if cierre is not None
            else Decimal("0.000")
        )
    )

    if target_sobrante > total_producido:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Los sobrantes registrados no pueden superar la cantidad producida en la jornada.",
        )

    if cierre is None:
        cierre = CierreDiario(
            producto_id=producto_id,
            fecha=fecha_jornada,
            existencia_calculada_base=existencia_calc,
            sobrante_real_base=target_sobrante,
            observaciones="Cierre operativo sincronizado desde Producción",
            usuario_id=usuario_id,
        )
        session.add(cierre)
    else:
        cierre.existencia_calculada_base = existencia_calc
        cierre.sobrante_real_base = target_sobrante
        if usuario_id is not None:
            cierre.usuario_id = usuario_id

    session.flush()
    return cierre


def serialize_produccion(
    produccion: Produccion,
    *,
    cierre: CierreDiario | None,
    cantidad_vendida_fecha: Decimal,
) -> ProduccionResponse:
    es_historico, es_sintetico, origen = classify_trace_origin(
        produccion.observaciones
    )
    producto = produccion.producto
    fecha_jornada = produccion.fecha_produccion.date()
    producida = Decimal(produccion.cantidad_producida_base).quantize(
        Decimal("0.001")
    )
    vendida = Decimal(cantidad_vendida_fecha).quantize(Decimal("0.001"))
    existencia_calc = (
        Decimal(cierre.existencia_calculada_base).quantize(Decimal("0.001"))
        if cierre is not None
        else max(Decimal("0.000"), producida - vendida)
    )
    sobrante_real = (
        Decimal(cierre.sobrante_real_base).quantize(Decimal("0.001"))
        if cierre is not None
        else Decimal("0.000")
    )
    diferencia = (sobrante_real - existencia_calc).quantize(Decimal("0.001"))

    return ProduccionResponse(
        id=produccion.id,
        producto_id=produccion.producto_id,
        producto_nombre=producto.nombre,
        unidad_base=producto.unidad_base,
        fecha_produccion=produccion.fecha_produccion,
        fecha_jornada=fecha_jornada,
        cantidad_producida_base=producida,
        cantidad_vendida_fecha=vendida,
        existencia_calculada_base=existencia_calc,
        sobrante_real_base=sobrante_real,
        diferencia_base=diferencia,
        observaciones=produccion.observaciones,
        es_historico=es_historico,
        es_sintetico=es_sintetico,
        origen_registro=origen,
        creado_en=produccion.creado_en,
    )


def _serialize_single_produccion(
    session: Session, produccion: Produccion
) -> ProduccionResponse:
    fecha_jornada = produccion.fecha_produccion.date()
    cierre = session.scalar(
        select(CierreDiario).where(
            CierreDiario.producto_id == produccion.producto_id,
            CierreDiario.fecha == fecha_jornada,
        )
    )
    vendida = _compute_daily_sold_base(
        session, produccion.producto_id, fecha_jornada
    )
    return serialize_produccion(
        produccion,
        cierre=cierre,
        cantidad_vendida_fecha=vendida,
    )


def list_producciones(
    session: Session,
    *,
    producto_id: int | None = None,
    producto_nombre: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    incluir_historicos: bool = True,
    incluir_sinteticos: bool = True,
    solo_operativos: bool = False,
    limit: int = 2000,
    offset: int = 0,
) -> list[ProduccionResponse]:
    stmt = _load_produccion_query()

    if producto_id is not None:
        stmt = stmt.where(Produccion.producto_id == producto_id)
    elif producto_nombre and producto_nombre.strip():
        canonical = _PRODUCT_NAME_ALIASES.get(
            producto_nombre.strip().lower(), producto_nombre.strip()
        )
        stmt = stmt.where(
            Produccion.producto.has(
                func.lower(Producto.nombre) == canonical.lower()
            )
        )

    if fecha_desde is not None:
        stmt = stmt.where(
            Produccion.fecha_produccion
            >= datetime.combine(fecha_desde, datetime.min.time())
        )
    if fecha_hasta is not None:
        stmt = stmt.where(
            Produccion.fecha_produccion
            <= datetime.combine(fecha_hasta, datetime.max.time())
        )

    if solo_operativos or not incluir_historicos:
        stmt = stmt.where(
            or_(
                Produccion.observaciones.is_(None),
                ~Produccion.observaciones.like("%IMPORTACION_EXCEL|%"),
            )
        )
    elif not incluir_sinteticos:
        stmt = stmt.where(
            or_(
                Produccion.observaciones.is_(None),
                ~Produccion.observaciones.like("%|es_sintetico=1%"),
            )
        )

    stmt = stmt.order_by(
        Produccion.fecha_produccion.desc(),
        Produccion.id.desc(),
    ).offset(offset).limit(limit)

    producciones = list(session.scalars(stmt).all())
    if not producciones:
        return []

    fechas = [p.fecha_produccion.date() for p in producciones]
    min_date, max_date = min(fechas), max(fechas)

    cierres_rows = session.scalars(
        select(CierreDiario).where(
            CierreDiario.fecha >= min_date,
            CierreDiario.fecha <= max_date,
        )
    ).all()
    cierres_by_key = {(c.producto_id, c.fecha): c for c in cierres_rows}

    sales_stmt = (
        select(
            Presentacion.producto_id,
            func.date(Venta.fecha_venta).label("fecha_v"),
            func.coalesce(
                func.sum(
                    DetalleVenta.cantidad * DetalleVenta.factor_conversion_snapshot
                ),
                0,
            ).label("vendido_base"),
        )
        .join(Venta, Venta.id == DetalleVenta.venta_id)
        .join(Presentacion, Presentacion.id == DetalleVenta.presentacion_id)
        .where(
            Venta.estado == "concretada",
            Venta.fecha_venta >= datetime.combine(min_date, datetime.min.time()),
            Venta.fecha_venta <= datetime.combine(max_date, datetime.max.time()),
        )
        .group_by(Presentacion.producto_id, func.date(Venta.fecha_venta))
    )
    sales_by_key: dict[tuple[int, date], Decimal] = {}
    for prod_id_row, fecha_row, vendido_row in session.execute(sales_stmt).all():
        parsed_date = (
            fecha_row
            if isinstance(fecha_row, date)
            else date.fromisoformat(str(fecha_row)[:10])
        )
        sales_by_key[(int(prod_id_row), parsed_date)] = Decimal(
            vendido_row or 0
        ).quantize(Decimal("0.001"))

    return [
        serialize_produccion(
            p,
            cierre=cierres_by_key.get((p.producto_id, p.fecha_produccion.date())),
            cantidad_vendida_fecha=sales_by_key.get(
                (p.producto_id, p.fecha_produccion.date()), Decimal("0.000")
            ),
        )
        for p in producciones
    ]


def get_produccion(session: Session, produccion_id: int) -> ProduccionResponse:
    produccion = get_produccion_model_or_404(session, produccion_id)
    return _serialize_single_produccion(session, produccion)


def create_produccion(
    session: Session,
    payload: ProduccionCreate,
    *,
    usuario_id: int | None = None,
    commit: bool = True,
) -> ProduccionResponse:
    producto = _resolve_producto(
        session,
        producto_id=payload.producto_id,
        producto_nombre=payload.producto_nombre,
    )
    fecha_produccion = payload.fecha_produccion or datetime.now(
        timezone.utc
    ).replace(tzinfo=None)
    fecha_jornada = fecha_produccion.date()

    # Verificar que no exista un cierre histórico en esa fecha para el mismo producto
    existing_cierre = session.scalar(
        select(CierreDiario).where(
            CierreDiario.producto_id == producto.id,
            CierreDiario.fecha == fecha_jornada,
        )
    )
    if existing_cierre is not None:
        es_hist_cierre, _, _ = classify_trace_origin(existing_cierre.observaciones)
        if es_hist_cierre:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"La jornada del {fecha_jornada.isoformat()} para '{producto.nombre}' "
                    "pertenece al historial importado y no puede sobrescribirse."
                ),
            )

    produccion = Produccion(
        producto_id=producto.id,
        fecha_produccion=fecha_produccion,
        cantidad_producida_base=Decimal(int(payload.cantidad_producida_base)),
        observaciones=payload.observaciones,
    )
    produccion.producto = producto
    session.add(produccion)
    session.flush()

    _sync_inventory_movement_for_produccion(session, produccion)
    _sync_cierre_diario_for_date(
        session,
        producto_id=producto.id,
        fecha_jornada=fecha_jornada,
        sobrante_real_base=Decimal(int(payload.sobrante_real_base)),
        usuario_id=usuario_id,
    )

    if commit:
        session.commit()
    else:
        session.flush()

    loaded = get_produccion_model_or_404(session, produccion.id)
    return _serialize_single_produccion(session, loaded)


def update_produccion(
    session: Session,
    produccion_id: int,
    payload: ProduccionUpdate,
    *,
    usuario_id: int | None = None,
    commit: bool = True,
) -> ProduccionResponse:
    produccion = get_produccion_model_or_404(session, produccion_id)

    old_date = produccion.fecha_produccion.date()
    updates = payload.model_dump(exclude_unset=True)

    target_cantidad = (
        Decimal(int(updates["cantidad_producida_base"]))
        if "cantidad_producida_base" in updates
        and updates["cantidad_producida_base"] is not None
        else Decimal(produccion.cantidad_producida_base)
    )
    target_sobrante = (
        Decimal(int(updates["sobrante_real_base"]))
        if "sobrante_real_base" in updates
        and updates["sobrante_real_base"] is not None
        else None
    )

    if target_sobrante is not None and target_sobrante > target_cantidad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Los sobrantes registrados no pueden superar la cantidad producida.",
        )

    if (
        "fecha_produccion" in updates
        and updates["fecha_produccion"] is not None
    ):
        produccion.fecha_produccion = updates["fecha_produccion"]

    if (
        "cantidad_producida_base" in updates
        and updates["cantidad_producida_base"] is not None
    ):
        produccion.cantidad_producida_base = target_cantidad

    if "observaciones" in updates:
        produccion.observaciones = updates["observaciones"]

    session.flush()

    new_date = produccion.fecha_produccion.date()
    _sync_inventory_movement_for_produccion(session, produccion)

    if old_date != new_date:
        _sync_cierre_diario_for_date(
            session,
            producto_id=produccion.producto_id,
            fecha_jornada=old_date,
            sobrante_real_base=None,
            usuario_id=usuario_id,
        )

    _sync_cierre_diario_for_date(
        session,
        producto_id=produccion.producto_id,
        fecha_jornada=new_date,
        sobrante_real_base=target_sobrante,
        usuario_id=usuario_id,
    )

    if commit:
        session.commit()
    else:
        session.flush()

    loaded = get_produccion_model_or_404(session, produccion.id)
    return _serialize_single_produccion(session, loaded)


def delete_produccion(
    session: Session,
    produccion_id: int,
    *,
    usuario_id: int | None = None,
    commit: bool = True,
) -> None:
    produccion = get_produccion_model_or_404(session, produccion_id)

    producto_id = produccion.producto_id
    fecha_jornada = produccion.fecha_produccion.date()

    _clear_inventory_movement_for_produccion(session, produccion)
    session.delete(produccion)
    session.flush()

    _sync_cierre_diario_for_date(
        session,
        producto_id=producto_id,
        fecha_jornada=fecha_jornada,
        sobrante_real_base=None,
        usuario_id=usuario_id,
    )

    if commit:
        session.commit()
    else:
        session.flush()
