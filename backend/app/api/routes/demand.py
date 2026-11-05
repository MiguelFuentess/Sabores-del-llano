from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Usuario
from app.schemas.demand import (
    DemandForecastRequest,
    DemandForecastResponse,
    DemandHistoricalContextResponse,
)
from app.services import demand as demand_service

router = APIRouter(tags=["demand"])


@router.get(
    "/prediccion/contexto-historico",
    response_model=DemandHistoricalContextResponse,
)
def get_contexto_historico_demanda(
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> DemandHistoricalContextResponse:
    return demand_service.get_demand_historical_context(session)


@router.post(
    "/prediccion/estimar",
    response_model=DemandForecastResponse,
    status_code=status.HTTP_200_OK,
)
def post_estimar_demanda(
    payload: DemandForecastRequest,
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> DemandForecastResponse:
    return demand_service.generate_demand_forecast(session, payload)


@router.get(
    "/prediccion/estimacion",
    response_model=DemandForecastResponse,
)
def get_estimacion_demanda(
    fecha_desde: date = Query(...),
    fecha_hasta: date = Query(...),
    producto_id: int | None = Query(default=None, gt=0),
    producto_nombre: str | None = Query(default=None),
    horizonte: str = Query(default="proxima_semana"),
    incluir_sinteticos: bool = Query(default=True),
    fecha_referencia: date | None = Query(default=None),
    sobrante_disponible_inicial: int | None = Query(default=None, ge=0),
    session: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> DemandForecastResponse:
    try:
        payload = DemandForecastRequest(
            producto_id=producto_id,
            producto_nombre=producto_nombre,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            horizonte=horizonte,  # type: ignore[arg-type]
            incluir_sinteticos=incluir_sinteticos,
            fecha_referencia=fecha_referencia,
            sobrante_disponible_inicial=sobrante_disponible_inicial,
        )
    except ValidationError as exc:
        first_msg = (
            exc.errors()[0].get("msg", "Parámetros de estimación inválidos.")
            if exc.errors()
            else "Parámetros de estimación inválidos."
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=first_msg,
        ) from exc

    return demand_service.generate_demand_forecast(session, payload)
