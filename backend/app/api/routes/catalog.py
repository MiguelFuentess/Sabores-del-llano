from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Usuario
from app.schemas.catalog import (
    CatalogSeedResult,
    PresentacionCreate,
    PresentacionResponse,
    PresentacionUpdate,
    ProductoCreate,
    ProductoResponse,
    ProductoUpdate,
)
from app.services import catalog as catalog_service

router = APIRouter(tags=["catalog"])


@router.get("/productos", response_model=list[ProductoResponse])
def get_productos(
    solo_activos: bool = Query(
        default=False,
        description="Si es True, devuelve únicamente los productos activos.",
    ),
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[ProductoResponse]:
    return catalog_service.list_productos(session, solo_activos=solo_activos)


@router.get("/productos/activos", response_model=list[ProductoResponse])
def get_productos_activos(
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[ProductoResponse]:
    return catalog_service.list_productos(session, solo_activos=True)


@router.get("/productos/{producto_id}", response_model=ProductoResponse)
def get_producto(
    producto_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ProductoResponse:
    return catalog_service.get_producto_or_404(session, producto_id)


@router.post(
    "/productos",
    response_model=ProductoResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_producto(
    payload: ProductoCreate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ProductoResponse:
    return catalog_service.create_producto(session, payload)


@router.patch("/productos/{producto_id}", response_model=ProductoResponse)
def patch_producto(
    producto_id: int,
    payload: ProductoUpdate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ProductoResponse:
    return catalog_service.update_producto(session, producto_id, payload)


@router.get(
    "/productos/{producto_id}/presentaciones",
    response_model=list[PresentacionResponse],
)
def get_presentaciones_por_producto(
    producto_id: int,
    solo_activas: bool = Query(
        default=False,
        description="Si es True, devuelve únicamente las presentaciones activas del producto.",
    ),
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[PresentacionResponse]:
    return catalog_service.list_presentaciones(
        session, producto_id=producto_id, solo_activas=solo_activas
    )


@router.get("/presentaciones", response_model=list[PresentacionResponse])
def get_presentaciones(
    producto_id: int | None = Query(
        default=None,
        description="Filtra las presentaciones por el ID del producto.",
    ),
    solo_activas: bool = Query(
        default=False,
        description="Si es True, devuelve únicamente las presentaciones activas.",
    ),
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[PresentacionResponse]:
    return catalog_service.list_presentaciones(
        session, producto_id=producto_id, solo_activas=solo_activas
    )


@router.get(
    "/presentaciones/{presentacion_id}",
    response_model=PresentacionResponse,
)
def get_presentacion(
    presentacion_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> PresentacionResponse:
    return catalog_service.get_presentacion_or_404(session, presentacion_id)


@router.post(
    "/presentaciones",
    response_model=PresentacionResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_presentacion(
    payload: PresentacionCreate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> PresentacionResponse:
    return catalog_service.create_presentacion(session, payload)


@router.patch(
    "/presentaciones/{presentacion_id}",
    response_model=PresentacionResponse,
)
def patch_presentacion(
    presentacion_id: int,
    payload: PresentacionUpdate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> PresentacionResponse:
    return catalog_service.update_presentacion(session, presentacion_id, payload)


@router.post("/catalogo/inicializar", response_model=CatalogSeedResult)
def post_inicializar_catalogo(
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> CatalogSeedResult:
    return catalog_service.seed_initial_catalog(session)
