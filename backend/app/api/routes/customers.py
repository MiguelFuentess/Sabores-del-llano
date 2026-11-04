from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Usuario
from app.schemas.customers import ClienteCreate, ClienteResponse, ClienteUpdate
from app.services import customers as customers_service

router = APIRouter(tags=["customers"])


@router.get("/clientes", response_model=list[ClienteResponse])
def get_clientes(
    q: str | None = Query(
        default=None,
        description="Búsqueda parcial por nombre, teléfono o correo.",
    ),
    solo_activos: bool = Query(default=False),
    incluir_sinteticos: bool = Query(default=True),
    solo_operativos: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[ClienteResponse]:
    return customers_service.list_clientes(
        session,
        q=q,
        solo_activos=solo_activos,
        incluir_sinteticos=incluir_sinteticos,
        solo_operativos=solo_operativos,
        limit=limit,
        offset=offset,
    )


@router.get("/clientes/{cliente_id}", response_model=ClienteResponse)
def get_cliente(
    cliente_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ClienteResponse:
    cliente = customers_service.get_cliente_or_404(session, cliente_id)
    return customers_service.serialize_cliente(cliente)


@router.post(
    "/clientes",
    response_model=ClienteResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_cliente(
    payload: ClienteCreate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ClienteResponse:
    return customers_service.create_cliente(session, payload)


@router.patch("/clientes/{cliente_id}", response_model=ClienteResponse)
def patch_cliente(
    cliente_id: int,
    payload: ClienteUpdate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ClienteResponse:
    return customers_service.update_cliente(session, cliente_id, payload)
