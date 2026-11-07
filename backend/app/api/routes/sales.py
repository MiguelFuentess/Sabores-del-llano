from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Usuario
from app.schemas.sales import (
    DetalleVentaResponse,
    VentaCreate,
    VentaEstadoLiteral,
    VentaResponse,
    VentaUpdate,
)
from app.services import reports as reports_service
from app.services import sales as sales_service

router = APIRouter(tags=["sales"])

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get("/ventas", response_model=list[VentaResponse])
def get_ventas(
    q: str | None = Query(
        default=None,
        description="Búsqueda por número de recibo/venta, producto u observaciones.",
    ),
    estado: VentaEstadoLiteral | None = Query(default=None),
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
) -> list[VentaResponse]:
    return sales_service.list_ventas(
        session,
        q=q,
        estado=estado,
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


@router.get("/ventas/reporte")
def get_ventas_reporte(
    q: str | None = Query(default=None),
    estado: VentaEstadoLiteral | None = Query(default="concretada"),
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
    content, filename = reports_service.generate_sales_report_xlsx(
        session,
        q=q,
        estado=estado,
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


@router.get("/ventas/{venta_id}", response_model=VentaResponse)
def get_venta(
    venta_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> VentaResponse:
    return sales_service.get_venta(session, venta_id)


@router.get(
    "/ventas/{venta_id}/detalles",
    response_model=list[DetalleVentaResponse],
)
def get_venta_detalles(
    venta_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[DetalleVentaResponse]:
    return sales_service.get_venta_detalles(session, venta_id)


@router.post(
    "/ventas",
    response_model=VentaResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_venta(
    payload: VentaCreate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> VentaResponse:
    return sales_service.create_venta(session, payload)


@router.patch("/ventas/{venta_id}", response_model=VentaResponse)
def patch_venta(
    venta_id: int,
    payload: VentaUpdate,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> VentaResponse:
    return sales_service.update_venta(session, venta_id, payload)


@router.delete(
    "/ventas/{venta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_venta(
    venta_id: int,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> None:
    sales_service.delete_venta(session, venta_id)
