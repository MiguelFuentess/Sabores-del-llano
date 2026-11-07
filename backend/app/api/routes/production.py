from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Usuario
from app.schemas.production import (
    ProduccionCreate,
    ProduccionResponse,
    ProduccionUpdate,
)
from app.services import production as production_service
from app.services import reports as reports_service

router = APIRouter(tags=["production"])

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get("/producciones", response_model=list[ProduccionResponse])
def get_producciones(
    producto_id: int | None = Query(default=None, gt=0),
    producto_nombre: str | None = Query(default=None),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    incluir_historicos: bool = Query(default=True),
    incluir_sinteticos: bool = Query(default=True),
    solo_operativos: bool = Query(default=False),
    limit: int = Query(default=2000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[ProduccionResponse]:
    return production_service.list_producciones(
        session,
        producto_id=producto_id,
        producto_nombre=producto_nombre,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        incluir_historicos=incluir_historicos,
        incluir_sinteticos=incluir_sinteticos,
        solo_operativos=solo_operativos,
        limit=limit,
        offset=offset,
    )


@router.get("/producciones/reporte")
def get_producciones_reporte(
    producto_id: int | None = Query(default=None, gt=0),
    producto_nombre: str | None = Query(default=None),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    periodo: str | None = Query(default=None),
    incluir_historicos: bool = Query(default=True),
    incluir_sinteticos: bool = Query(default=True),
    solo_operativos: bool = Query(default=False),
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> Response:
    content, filename = reports_service.generate_production_report_xlsx(
        session,
        producto_id=producto_id,
        producto_nombre=producto_nombre,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        periodo=periodo,
        incluir_historicos=incluir_historicos,
        incluir_sinteticos=incluir_sinteticos,
        solo_operativos=solo_operativos,
    )
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/producciones/{produccion_id}", response_model=ProduccionResponse)
def get_produccion(
    produccion_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ProduccionResponse:
    return production_service.get_produccion(session, produccion_id)


@router.post(
    "/producciones",
    response_model=ProduccionResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_produccion(
    payload: ProduccionCreate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ProduccionResponse:
    return production_service.create_produccion(
        session,
        payload,
        usuario_id=current_user.id,
    )


@router.patch(
    "/producciones/{produccion_id}",
    response_model=ProduccionResponse,
)
def patch_produccion(
    produccion_id: int,
    payload: ProduccionUpdate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> ProduccionResponse:
    return production_service.update_produccion(
        session,
        produccion_id,
        payload,
        usuario_id=current_user.id,
    )


@router.delete(
    "/producciones/{produccion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_produccion(
    produccion_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> None:
    production_service.delete_produccion(
        session,
        produccion_id,
        usuario_id=current_user.id,
    )
