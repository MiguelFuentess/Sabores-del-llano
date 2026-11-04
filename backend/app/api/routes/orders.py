from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Usuario
from app.schemas.orders import (
    DetallePedidoResponse,
    PedidoCreate,
    PedidoEstadoLiteral,
    PedidoResponse,
    PedidoUpdate,
)
from app.services import orders as orders_service

router = APIRouter(tags=["orders"])


@router.get("/pedidos", response_model=list[PedidoResponse])
def get_pedidos(
    q: str | None = Query(
        default=None,
        description="Búsqueda por cliente, número de pedido o dirección.",
    ),
    estado: PedidoEstadoLiteral | None = Query(default=None),
    cliente_id: int | None = Query(default=None, gt=0),
    fecha_entrega_desde: date | None = Query(default=None),
    fecha_entrega_hasta: date | None = Query(default=None),
    incluir_historicos: bool = Query(default=True),
    incluir_sinteticos: bool = Query(default=True),
    solo_operativos: bool = Query(default=False),
    limit: int = Query(default=2000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[PedidoResponse]:
    return orders_service.list_pedidos(
        session,
        q=q,
        estado=estado,
        cliente_id=cliente_id,
        fecha_entrega_desde=fecha_entrega_desde,
        fecha_entrega_hasta=fecha_entrega_hasta,
        incluir_historicos=incluir_historicos,
        incluir_sinteticos=incluir_sinteticos,
        solo_operativos=solo_operativos,
        limit=limit,
        offset=offset,
    )


@router.get("/pedidos/{pedido_id}", response_model=PedidoResponse)
def get_pedido(
    pedido_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> PedidoResponse:
    return orders_service.get_pedido(session, pedido_id)


@router.get(
    "/pedidos/{pedido_id}/detalles",
    response_model=list[DetallePedidoResponse],
)
def get_pedido_detalles(
    pedido_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[DetallePedidoResponse]:
    return orders_service.get_pedido_detalles(session, pedido_id)


@router.post(
    "/pedidos",
    response_model=PedidoResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_pedido(
    payload: PedidoCreate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> PedidoResponse:
    return orders_service.create_pedido(session, payload)


@router.patch("/pedidos/{pedido_id}", response_model=PedidoResponse)
def patch_pedido(
    pedido_id: int,
    payload: PedidoUpdate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> PedidoResponse:
    return orders_service.update_pedido(session, pedido_id, payload)


@router.delete(
    "/pedidos/{pedido_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_pedido(
    pedido_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> None:
    orders_service.delete_pedido(session, pedido_id)
