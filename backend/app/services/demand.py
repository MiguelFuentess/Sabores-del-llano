from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import math
import statistics
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CierreDiario,
    DetalleVenta,
    Presentacion,
    Producto,
    Venta,
)
from app.schemas.demand import (
    DemandForecastRequest,
    DemandForecastResponse,
    DemandHistoricalContextResponse,
    DiaPlanificacionDemanda,
    HorizonteEstimacionLiteral,
    MetricasPrecisionModelo,
    NivelConfianzaLiteral,
    OrigenEvaluacionLiteral,
    PerfilTipoDiaResponse,
    ProductoContextoDemanda,
    RecomendacionDemanda,
    ResumenHistoricoDemanda,
    TipoDiaOperativoLiteral,
)
from app.services.colombian_calendar import (
    OperationDateInfo,
    inspect_operation_date,
)
from app.services.customers import classify_trace_origin

MIN_HISTORICAL_OPERATION_DAYS = 3
OPTIMAL_HISTORICAL_OPERATION_DAYS = 8

try:
    COLOMBIA_TZ: timezone | ZoneInfo = ZoneInfo("America/Bogota")
except ZoneInfoNotFoundError:
    COLOMBIA_TZ = timezone(timedelta(hours=-5))

# Parámetros estadísticos explicables y reproducibles (calibrados por validación walk-forward)
RECENCY_HALF_LIFE_DAYS = 63.0  # 9 semanas calendario para nivel base por tipo de jornada
SHORT_MOMENTUM_HALF_LIFE_DAYS = 28.0  # 4 semanas calendario para impulso reciente
DAY_TYPE_SHRINKAGE_K = 3.0
SHORT_MOMENTUM_SHRINKAGE_K = 4.0
TREND_DAMPING_FACTOR = 0.35
WEEKLY_HORIZON_DECAY = 0.84
STRUCTURAL_DRIFT_WEIGHT = 0.25
MONTHLY_SEASONALITY_MIN_SPAN_DAYS = 330
MONTHLY_SEASONALITY_MIN_OBS = 6
MONTHLY_SEASONALITY_SHRINKAGE_K = 30.0

_MODEL_METHOD_DESCRIPTION = (
    "Descomposición por tipo de jornada con suavizamiento exponencial por recencia, "
    "impulso reciente amortiguado y estacionalidad mensual regularizada"
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

_HORIZON_DAYS_MAP: dict[HorizonteEstimacionLiteral, int] = {
    "proxima_semana": 7,
    "proximo_mes": 30,
    "proximo_trimestre": 90,
}

_HORIZON_LABELS: dict[HorizonteEstimacionLiteral, str] = {
    "proxima_semana": "Próxima semana",
    "proximo_mes": "Próximo mes",
    "proximo_trimestre": "Próximo trimestre",
}

_WEEKDAY_NAMES_ES = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)

_MONTH_NAMES_ES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_DAY_TYPE_LABELS: dict[TipoDiaOperativoLiteral, str] = {
    "sabado": "Sábados",
    "domingo": "Domingos",
    "festivo": "Festivos nacionales",
}


@dataclass(frozen=True)
class _DailyDemandPoint:
    fecha: date
    cantidad_base: float
    tipo_dia: TipoDiaOperativoLiteral
    es_historico: bool
    es_sintetico: bool
    es_operativo: bool
    cal_info: OperationDateInfo


@dataclass(frozen=True)
class _PointForecastComponents:
    base_tipo_dia: float
    impulso_reciente_ratio: float
    deriva_estructural_ratio: float
    estacionalidad_mensual_ratio: float
    factor_ajuste_total: float
    demanda_continua: float


def get_colombia_today() -> date:
    """Obtiene la fecha calendario actual en la zona horaria oficial de Colombia (America/Bogota, UTC-5)."""
    return datetime.now(COLOMBIA_TZ).date()


def _resolve_horizon_dates(
    ref_date: date,
    horizonte: HorizonteEstimacionLiteral,
) -> tuple[date, date]:
    """Calcula el período proyectado [inicio, fin] a partir de la fecha local de referencia.

    - 'proxima_semana': inicia en ref_date y abarca hasta el cierre de la semana en curso
      (domingo inmediato cuando ref_date es lunes a sábado; p. ej. viernes 6 de noviembre de 2026
      proyecta viernes 6, sábado 7 y domingo 8 de noviembre de 2026). Si la consulta ocurre en
      domingo, abarca desde ese domingo hasta el domingo siguiente inclusive.
    - 'proximo_mes': ventana de 30 días calendario iniciando en ref_date.
    - 'proximo_trimestre': ventana de 90 días calendario iniciando en ref_date.
    """
    fecha_inicio = ref_date
    if horizonte == "proxima_semana":
        weekday = ref_date.weekday()  # 0=Lunes ... 4=Viernes, 5=Sábado, 6=Domingo
        days_ahead = (6 - weekday) if weekday < 6 else 7
        fecha_fin = fecha_inicio + timedelta(days=days_ahead)
    else:
        horizon_days = _HORIZON_DAYS_MAP[horizonte]
        fecha_fin = fecha_inicio + timedelta(days=horizon_days - 1)
    return fecha_inicio, fecha_fin


def _quantize_dec(value: float | Decimal, pattern: str = "0.01") -> Decimal:
    return Decimal(str(value)).quantize(Decimal(pattern))


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


def _classify_operation_day_type(
    cal_info: OperationDateInfo,
) -> TipoDiaOperativoLiteral:
    if cal_info.es_festivo_nacional:
        return "festivo"
    if cal_info.es_sabado:
        return "sabado"
    return "domingo"


def _build_day_label(cal_info: OperationDateInfo) -> str:
    w_name = _WEEKDAY_NAMES_ES[cal_info.fecha.weekday()]
    if cal_info.es_festivo_nacional and cal_info.nombre_festivo:
        return f"{w_name} festivo · {cal_info.nombre_festivo}"
    return w_name


def _count_operation_days_in_range(start_date: date, end_date: date) -> int:
    if start_date > end_date:
        return 0
    total = 0
    cursor = start_date
    while cursor <= end_date:
        if inspect_operation_date(cursor).es_dia_operacion:
            total += 1
        cursor += timedelta(days=1)
    return total


def _compute_observation_weights(
    points: list[_DailyDemandPoint],
    half_life_days: float = RECENCY_HALF_LIFE_DAYS,
) -> list[float]:
    """Calcula pesos de recencia con decaimiento exponencial por distancia calendario (en días)."""
    if not points:
        return []
    last_date = points[-1].fecha
    ln2 = math.log(2.0)
    return [
        math.exp(-ln2 * max(0, (last_date - p.fecha).days) / half_life_days)
        for p in points
    ]


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    if not values:
        return 0.0
    total_w = sum(weights)
    if total_w <= 0:
        return statistics.mean(values)
    return sum(v * w for v, w in zip(values, weights)) / total_w


def _effective_sample_size(weights: list[float]) -> float:
    if not weights:
        return 0.0
    sw = sum(weights)
    sw2 = sum(w * w for w in weights)
    return (sw * sw) / sw2 if sw2 > 0 else float(len(weights))


def _compute_smoothed_day_type_means(
    points: list[_DailyDemandPoint],
    weights: list[float],
) -> tuple[float, dict[TipoDiaOperativoLiteral, float]]:
    """Calcula niveles base por tipo de jornada regularizados por tamaño muestral efectivo."""
    global_w_mean = _weighted_mean(
        [p.cantidad_base for p in points], weights
    )
    smoothed: dict[TipoDiaOperativoLiteral, float] = {}
    for dtype in ("sabado", "domingo", "festivo"):
        sub_vals = [
            p.cantidad_base for p in points if p.tipo_dia == dtype
        ]
        sub_w = [
            w for p, w in zip(points, weights) if p.tipo_dia == dtype
        ]
        if not sub_vals:
            smoothed[dtype] = global_w_mean
        else:
            raw_w_mean = _weighted_mean(sub_vals, sub_w)
            n_eff = _effective_sample_size(sub_w)
            alpha = n_eff / (n_eff + DAY_TYPE_SHRINKAGE_K)
            smoothed[dtype] = alpha * raw_w_mean + (1.0 - alpha) * global_w_mean
    return global_w_mean, smoothed


def _predict_demand_for_date(
    train_points: list[_DailyDemandPoint],
    target_date: date,
    target_dtype: TipoDiaOperativoLiteral,
    *,
    precomputed_weights: list[float] | None = None,
    precomputed_smoothed: tuple[float, dict[TipoDiaOperativoLiteral, float]] | None = None,
) -> _PointForecastComponents:
    """Estima la demanda continua de una fecha futura combinando:
    1. Nivel base exponencial por tipo de jornada (semivida 63 días) con contracción bayesiana.
    2. Impulso reciente específico del tipo de jornada + global (semivida 28 días), amortiguado por horizonte.
    3. Deriva estructural amortiguada por regresión lineal cuando existen >= 12 jornadas y >= 60 días.
    4. Estacionalidad mensual desestacionalizada con contracción bayesiana cuando la serie cubre >= 330 días.
    """
    n = len(train_points)
    weights_med = (
        precomputed_weights
        if precomputed_weights is not None
        else _compute_observation_weights(train_points, RECENCY_HALF_LIFE_DAYS)
    )
    global_med, smoothed = (
        precomputed_smoothed
        if precomputed_smoothed is not None
        else _compute_smoothed_day_type_means(train_points, weights_med)
    )
    base_dt = smoothed[target_dtype]

    t_first = train_points[0].fecha
    t_last = train_points[-1].fecha
    span_days = max(0, (t_last - t_first).days)
    lead_days = max(0, (target_date - t_last).days)
    lead_weeks = lead_days / 7.0

    # 1. Impulso reciente específico por tipo de jornada combinado con impulso global
    impulso_ratio = 0.0
    if n >= 6:
        w_short = _compute_observation_weights(
            train_points, SHORT_MOMENTUM_HALF_LIFE_DAYS
        )
        global_short = _weighted_mean(
            [p.cantidad_base for p in train_points], w_short
        )
        global_mom = (
            (global_short - global_med) / global_med if global_med > 0 else 0.0
        )

        sub_short_vals = [
            p.cantidad_base for p in train_points if p.tipo_dia == target_dtype
        ]
        sub_short_w = [
            w for p, w in zip(train_points, w_short) if p.tipo_dia == target_dtype
        ]
        if len(sub_short_vals) >= 3 and base_dt > 0:
            neff_s = _effective_sample_size(sub_short_w)
            raw_dt_short = _weighted_mean(sub_short_vals, sub_short_w)
            dt_mom = (raw_dt_short - base_dt) / base_dt
            blend = neff_s / (neff_s + SHORT_MOMENTUM_SHRINKAGE_K)
            combined_mom = blend * dt_mom + (1.0 - blend) * global_mom
        else:
            combined_mom = global_mom

        horizon_decay = WEEKLY_HORIZON_DECAY ** max(0.0, lead_weeks - 0.5)
        impulso_ratio = max(
            -0.08,
            min(0.08, combined_mom * TREND_DAMPING_FACTOR * horizon_decay),
        )

    # 2. Deriva estructural amortiguada sobre la ventana histórica completa
    deriva_ratio = 0.0
    slope_ols = 0.0
    intercept_ols = global_med
    xs_ols = [float((p.fecha - t_first).days) for p in train_points]
    if n >= 12 and span_days >= 60:
        mx = statistics.mean(xs_ols)
        my = statistics.mean(p.cantidad_base for p in train_points)
        sxx = sum((x - mx) ** 2 for x in xs_ols)
        if sxx > 0:
            sxy = sum(
                (x - mx) * (p.cantidad_base - my)
                for x, p in zip(xs_ols, train_points)
            )
            slope_ols = sxy / sxx
            intercept_ols = my - slope_ols * mx
            if lead_weeks > 0 and base_dt > 0:
                phi = 0.92
                eff_weeks = (1.0 - (phi ** lead_weeks)) / (1.0 - phi)
                raw_drift = (
                    slope_ols * 7.0 * eff_weeks * STRUCTURAL_DRIFT_WEIGHT
                ) / base_dt
                deriva_ratio = max(-0.06, min(0.06, raw_drift))

    # 3. Estacionalidad mensual desestacionalizada regularizada (cuando >= 330 días y >= 6 obs en el mes)
    estacional_ratio = 0.0
    if span_days >= MONTHLY_SEASONALITY_MIN_SPAN_DAYS:
        month_ratios: list[float] = []
        for p, x in zip(train_points, xs_ols):
            if p.fecha.month == target_date.month:
                trend_hat = intercept_ols + slope_ols * x
                if trend_hat > 0:
                    month_ratios.append(p.cantidad_base / trend_hat)
        if len(month_ratios) >= MONTHLY_SEASONALITY_MIN_OBS:
            raw_seas = statistics.mean(month_ratios) - 1.0
            shrink_s = len(month_ratios) / (
                len(month_ratios) + MONTHLY_SEASONALITY_SHRINKAGE_K
            )
            estacional_ratio = max(-0.06, min(0.06, raw_seas * shrink_s))

    factor_total = (1.0 + impulso_ratio + deriva_ratio) * (1.0 + estacional_ratio)
    demanda_continua = max(1.0, base_dt * factor_total)
    return _PointForecastComponents(
        base_tipo_dia=base_dt,
        impulso_reciente_ratio=impulso_ratio,
        deriva_estructural_ratio=deriva_ratio,
        estacionalidad_mensual_ratio=estacional_ratio,
        factor_ajuste_total=factor_total,
        demanda_continua=demanda_continua,
    )


def _compute_backtest_metrics(
    points: list[_DailyDemandPoint],
) -> MetricasPrecisionModelo:
    n = len(points)
    if n < 5:
        return MetricasPrecisionModelo(
            metodo=_MODEL_METHOD_DESCRIPTION,
            origen_evaluacion="muestra_insuficiente",
            muestras_evaluadas=0,
            mae_base=None,
            rmse_base=None,
            mape_porcentaje=None,
            precision_estimada_porcentaje=None,
            nivel_confianza="baja",
            nota_metodologica=(
                f"El período seleccionado cuenta con solo {n} jornadas operativas válidas. "
                f"Se recomiendan al menos {OPTIMAL_HISTORICAL_OPERATION_DAYS} jornadas operativas "
                "para calcular métricas de precisión por validación retrospectiva (walk-forward)."
            ),
        )

    eval_indices = list(range(3, n))
    if len(eval_indices) > 20:
        eval_indices = eval_indices[-20:]
    origen_eval: OrigenEvaluacionLiteral = "datos_reales_y_operativos"

    abs_errors: list[float] = []
    sq_errors: list[float] = []
    ape_values: list[float] = []

    for test_idx in eval_indices:
        train_pts = points[:test_idx]
        target_pt = points[test_idx]
        comp = _predict_demand_for_date(
            train_pts,
            target_pt.fecha,
            target_pt.tipo_dia,
        )
        pred = comp.demanda_continua
        actual = target_pt.cantidad_base

        err = abs(actual - pred)
        abs_errors.append(err)
        sq_errors.append(err * err)
        if actual > 0:
            ape_values.append((err / actual) * 100.0)

    mae = statistics.mean(abs_errors)
    rmse = math.sqrt(statistics.mean(sq_errors))
    mape: float | None = statistics.mean(ape_values) if ape_values else None
    precision_pct: float | None = (
        max(0.0, min(100.0, 100.0 - mape)) if mape is not None else None
    )

    small_sample_warning = n < OPTIMAL_HISTORICAL_OPERATION_DAYS

    if (
        not small_sample_warning
        and n >= 15
        and mape is not None
        and mape <= 12.0
    ):
        confianza: NivelConfianzaLiteral = "alta"
    elif (
        not small_sample_warning
        and n >= 6
        and mape is not None
        and mape <= 18.0
    ):
        confianza = "media"
    else:
        confianza = "baja"

    mape_str = f"{mape:.2f}% MAPE" if mape is not None else "MAPE no disponible"
    nota = (
        f"Validación walk-forward evaluada sobre {len(eval_indices)} "
        "jornadas del historial operativo. "
        f"Error medio absoluto de {mae:.2f} unidades base ({mape_str})."
    )

    if small_sample_warning:
        nota = (
            f"ADVERTENCIA DE MUESTRA REDUCIDA: El período seleccionado cuenta con solo {n} "
            f"jornadas operativas válidas (se recomiendan al menos {OPTIMAL_HISTORICAL_OPERATION_DAYS}). "
            f"{nota}"
        )

    return MetricasPrecisionModelo(
        metodo=_MODEL_METHOD_DESCRIPTION,
        origen_evaluacion=origen_eval,
        muestras_evaluadas=len(eval_indices),
        mae_base=_quantize_dec(mae, "0.01"),
        rmse_base=_quantize_dec(rmse, "0.01"),
        mape_porcentaje=_quantize_dec(mape, "0.01") if mape is not None else None,
        precision_estimada_porcentaje=(
            _quantize_dec(precision_pct, "0.01")
            if precision_pct is not None
            else None
        ),
        nivel_confianza=confianza,
        nota_metodologica=nota,
    )


def get_demand_historical_context(
    session: Session,
) -> DemandHistoricalContextResponse:
    productos = list(
        session.scalars(
            select(Producto)
            .where(Producto.activo.is_(True))
            .order_by(Producto.id.asc())
        ).all()
    )

    ventas = list(
        session.scalars(
            select(Venta)
            .options(
                selectinload(Venta.detalles).selectinload(
                    DetalleVenta.presentacion
                )
            )
            .where(Venta.estado == "concretada")
        ).all()
    )

    cierres = list(
        session.scalars(
            select(CierreDiario).order_by(CierreDiario.fecha.desc())
        ).all()
    )
    latest_cierre_by_prod: dict[int, CierreDiario] = {}
    for c in cierres:
        if c.producto_id not in latest_cierre_by_prod:
            latest_cierre_by_prod[c.producto_id] = c

    prod_dates: dict[int, dict[str, set[date]]] = {
        p.id: {"all": set(), "real": set(), "syn": set(), "op": set()}
        for p in productos
    }

    for v in ventas:
        v_date = v.fecha_venta.date()
        es_hist, es_sin, _ = classify_trace_origin(v.observaciones)
        for d in v.detalles:
            pid = d.presentacion.producto_id
            if pid not in prod_dates:
                continue
            prod_dates[pid]["all"].add(v_date)
            if not es_hist:
                prod_dates[pid]["op"].add(v_date)
            elif es_sin:
                prod_dates[pid]["syn"].add(v_date)
            else:
                prod_dates[pid]["real"].add(v_date)

    all_dates_global: set[date] = set()
    real_dates_global: set[date] = set()
    productos_ctx: list[ProductoContextoDemanda] = []

    for p in productos:
        dsets = prod_dates[p.id]
        all_d = dsets["all"]
        real_and_op = dsets["real"] | dsets["op"]
        all_dates_global |= all_d
        real_dates_global |= real_and_op

        last_cierre = latest_cierre_by_prod.get(p.id)
        ultimo_sob = (
            int(round(float(last_cierre.sobrante_real_base)))
            if last_cierre is not None
            else 0
        )

        productos_ctx.append(
            ProductoContextoDemanda(
                producto_id=p.id,
                producto_nombre=p.nombre,
                unidad_base=p.unidad_base,
                fecha_minima_ventas=min(all_d) if all_d else None,
                fecha_maxima_ventas=max(all_d) if all_d else None,
                fecha_minima_reales=min(real_and_op) if real_and_op else None,
                fecha_maxima_reales=max(real_and_op) if real_and_op else None,
                dias_operativos_totales=len(all_d),
                dias_reales=len(dsets["real"]),
                dias_sinteticos=len(dsets["syn"]),
                dias_operativos_app=len(dsets["op"]),
                ultimo_sobrante_real_base=ultimo_sob,
                fecha_ultimo_cierre=(
                    last_cierre.fecha if last_cierre is not None else None
                ),
            )
        )

    return DemandHistoricalContextResponse(
        fecha_minima_global=min(all_dates_global) if all_dates_global else None,
        fecha_maxima_global=max(all_dates_global) if all_dates_global else None,
        fecha_inicio_datos_reales=(
            min(real_dates_global) if real_dates_global else None
        ),
        fecha_maxima_datos_reales=(
            max(real_dates_global) if real_dates_global else None
        ),
        minimo_dias_operativos_requeridos=MIN_HISTORICAL_OPERATION_DAYS,
        dias_operativos_recomendados=OPTIMAL_HISTORICAL_OPERATION_DAYS,
        productos=productos_ctx,
    )


def generate_demand_forecast(
    session: Session,
    payload: DemandForecastRequest,
) -> DemandForecastResponse:
    producto = _resolve_producto(
        session,
        producto_id=payload.producto_id,
        producto_nombre=payload.producto_nombre,
    )

    if payload.fecha_desde > payload.fecha_hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La fecha inicial del período histórico no puede ser posterior a la fecha final.",
        )

    # Determinar fecha local de referencia en Colombia y rango del horizonte futuro
    ref_date = (
        payload.fecha_referencia
        if payload.fecha_referencia is not None
        else get_colombia_today()
    )
    fecha_inicio_horizonte, fecha_fin_horizonte = _resolve_horizon_dates(
        ref_date, payload.horizonte
    )

    # Garantizar estrictamente que el entrenamiento histórico sea anterior al horizonte proyectado
    if payload.fecha_desde >= fecha_inicio_horizonte:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"La fecha inicial del período histórico ({payload.fecha_desde.isoformat()}) "
                f"debe ser anterior al inicio del horizonte proyectado ({fecha_inicio_horizonte.isoformat()}) "
                "para evitar filtración de información futura."
            ),
        )

    effective_fecha_hasta = min(
        payload.fecha_hasta,
        fecha_inicio_horizonte - timedelta(days=1),
    )

    start_dt = datetime.combine(payload.fecha_desde, datetime.min.time())
    end_dt = datetime.combine(effective_fecha_hasta, datetime.max.time())

    ventas_stmt = (
        select(Venta)
        .options(
            selectinload(Venta.detalles).selectinload(DetalleVenta.presentacion)
        )
        .where(
            Venta.estado == "concretada",
            Venta.fecha_venta >= start_dt,
            Venta.fecha_venta <= end_dt,
            Venta.detalles.any(
                DetalleVenta.presentacion.has(
                    Presentacion.producto_id == producto.id
                )
            ),
        )
        .order_by(Venta.fecha_venta.asc(), Venta.id.asc())
    )
    ventas_rows = list(session.scalars(ventas_stmt).all())

    # Agrupar demanda por fecha operativa
    daily_buckets: dict[date, dict[str, object]] = {}
    for venta in ventas_rows:
        es_historico, es_sintetico, _ = classify_trace_origin(
            venta.observaciones
        )

        qty_venta_prod = sum(
            float(d.cantidad * d.factor_conversion_snapshot)
            for d in venta.detalles
            if d.presentacion.producto_id == producto.id
        )
        if qty_venta_prod <= 0:
            continue

        fecha_v = venta.fecha_venta.date()
        has_calendar_alert = bool(
            venta.observaciones and "alerta_calendario=" in venta.observaciones
        )
        bucket = daily_buckets.get(fecha_v)
        if bucket is None:
            bucket = {
                "qty": 0.0,
                "es_historico": es_historico,
                "es_sintetico": es_sintetico,
                "es_operativo": not es_historico,
                "has_alert": has_calendar_alert,
            }
            daily_buckets[fecha_v] = bucket
        bucket["qty"] = float(bucket["qty"]) + qty_venta_prod
        if not es_historico:
            bucket["es_operativo"] = True
            bucket["es_sintetico"] = False
        elif not es_sintetico:
            bucket["es_sintetico"] = False
        if has_calendar_alert:
            bucket["has_alert"] = True

    fechas_no_operativas_excluidas: list[date] = []
    valid_points: list[_DailyDemandPoint] = []

    for fecha_k in sorted(daily_buckets.keys()):
        b = daily_buckets[fecha_k]
        cal_info = inspect_operation_date(fecha_k)
        if not cal_info.es_dia_operacion or bool(b["has_alert"]):
            fechas_no_operativas_excluidas.append(fecha_k)
            continue

        valid_points.append(
            _DailyDemandPoint(
                fecha=fecha_k,
                cantidad_base=float(b["qty"]),
                tipo_dia=_classify_operation_day_type(cal_info),
                es_historico=bool(b["es_historico"]),
                es_sintetico=bool(b["es_sintetico"]),
                es_operativo=bool(b["es_operativo"]),
                cal_info=cal_info,
            )
        )

    if len(valid_points) < MIN_HISTORICAL_OPERATION_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"El período histórico seleccionado ({payload.fecha_desde.isoformat()} a "
                f"{effective_fecha_hasta.isoformat()}) solo contiene "
                f"{len(valid_points)} jornadas operativas válidas con ventas para '{producto.nombre}'. "
                f"Se requieren al menos {MIN_HISTORICAL_OPERATION_DAYS} jornadas operativas "
                "para generar una estimación estadística verificable."
            ),
        )

    # Consultar cierres diarios anteriores al horizonte para analizar sobrantes históricos
    cierres_rows = list(
        session.scalars(
            select(CierreDiario)
            .where(
                CierreDiario.producto_id == producto.id,
                CierreDiario.fecha >= payload.fecha_desde,
                CierreDiario.fecha <= effective_fecha_hasta,
            )
            .order_by(CierreDiario.fecha.asc())
        ).all()
    )
    sobrantes_hist_vals: list[float] = [
        float(c.sobrante_real_base) for c in cierres_rows
    ]

    promedio_sobrante_hist = (
        statistics.mean(sobrantes_hist_vals) if sobrantes_hist_vals else 0.0
    )

    # Pesos exponenciales por recencia y niveles base por tipo de jornada
    weights = _compute_observation_weights(valid_points, RECENCY_HALF_LIFE_DAYS)
    all_quantities = [p.cantidad_base for p in valid_points]
    global_simple_mean = statistics.mean(all_quantities)
    global_std = (
        statistics.stdev(all_quantities) if len(all_quantities) > 1 else 0.0
    )
    global_w_mean, smoothed_by_type = _compute_smoothed_day_type_means(
        valid_points, weights
    )

    # Perfiles y dispersión por tipo de día (sábado, domingo, festivo)
    perfiles_tipo_dia: list[PerfilTipoDiaResponse] = []
    std_by_type: dict[TipoDiaOperativoLiteral, float] = {}
    for dtype in ("sabado", "domingo", "festivo"):
        pts_d = [p for p in valid_points if p.tipo_dia == dtype]
        if pts_d:
            vals_d = [p.cantidad_base for p in pts_d]
            s_mean = statistics.mean(vals_d)
            w_mean = smoothed_by_type[dtype]
            min_v = min(vals_d)
            max_v = max(vals_d)
            std_by_type[dtype] = (
                statistics.stdev(vals_d) if len(vals_d) >= 5 else global_std
            )
        else:
            s_mean = global_simple_mean
            w_mean = smoothed_by_type[dtype]
            min_v = min(all_quantities)
            max_v = max(all_quantities)
            std_by_type[dtype] = global_std

        perfiles_tipo_dia.append(
            PerfilTipoDiaResponse(
                tipo_dia=dtype,
                etiqueta=_DAY_TYPE_LABELS[dtype],
                dias_observados=len(pts_d),
                promedio_simple_base=_quantize_dec(s_mean, "0.01"),
                promedio_ponderado_base=_quantize_dec(w_mean, "0.01"),
                minimo_observado_base=_quantize_dec(min_v, "0.01"),
                maximo_observado_base=_quantize_dec(max_v, "0.01"),
            )
        )

    # Consultar último cierre diario estrictamente anterior al horizonte para sobrantes iniciales
    ultimo_cierre = session.scalar(
        select(CierreDiario)
        .where(
            CierreDiario.producto_id == producto.id,
            CierreDiario.fecha <= effective_fecha_hasta,
        )
        .order_by(CierreDiario.fecha.desc())
        .limit(1)
    )
    ultimo_sobrante_reg = (
        float(ultimo_cierre.sobrante_real_base)
        if ultimo_cierre is not None
        else 0.0
    )
    fecha_ultimo_cierre = (
        ultimo_cierre.fecha if ultimo_cierre is not None else None
    )

    # Generar las fechas operativas futuras dentro del horizonte [fecha_inicio_horizonte, fecha_fin_horizonte]
    future_op_dates: list[OperationDateInfo] = []
    cursor = fecha_inicio_horizonte
    while cursor <= fecha_fin_horizonte:
        info = inspect_operation_date(cursor)
        if info.es_dia_operacion:
            future_op_dates.append(info)
        cursor += timedelta(days=1)

    # Determinar sobrante disponible inicial aplicable por única vez al inicio del horizonte
    if payload.sobrante_disponible_inicial is not None:
        sobrante_remanente = int(payload.sobrante_disponible_inicial)
    elif (
        ultimo_cierre is not None
        and future_op_dates
        and 0 < (future_op_dates[0].fecha - ultimo_cierre.fecha).days <= 7
    ):
        sobrante_remanente = int(round(ultimo_sobrante_reg))
    else:
        sobrante_remanente = 0

    first_op_date = future_op_dates[0].fecha if future_op_dates else None

    # Construir la tabla de planificación diaria sin redondeos intermedios
    planificacion_diaria: list[DiaPlanificacionDemanda] = []
    applied_trend_ratios: list[float] = []
    for info in future_op_dates:
        dtype = _classify_operation_day_type(info)
        comp = _predict_demand_for_date(
            valid_points,
            info.fecha,
            dtype,
            precomputed_weights=weights,
            precomputed_smoothed=(global_w_mean, smoothed_by_type),
        )
        base_demand = comp.base_tipo_dia
        factor_ajuste = comp.factor_ajuste_total
        raw_est = comp.demanda_continua
        demanda_estimada = max(1, int(round(raw_est)))
        net_trend_day = comp.impulso_reciente_ratio + comp.deriva_estructural_ratio
        applied_trend_ratios.append(net_trend_day)

        # El sobrante inicial se descuenta como máximo una sola vez (en el primer bloque inmediato <= 2 días)
        if (
            sobrante_remanente > 0
            and first_op_date is not None
            and (info.fecha - first_op_date).days <= 2
        ):
            sobrante_dia = min(demanda_estimada, sobrante_remanente)
            sobrante_remanente = max(0, sobrante_remanente - sobrante_dia)
        else:
            sobrante_dia = 0

        produccion_sugerida = max(0, demanda_estimada - sobrante_dia)
        dtype_std = std_by_type[dtype]
        band = max(3.0, dtype_std if dtype_std > 0 else base_demand * 0.08)
        rango_min = max(1, int(round(raw_est - band)))
        rango_max = max(demanda_estimada, int(round(raw_est + band)))

        etiqueta_dia = _build_day_label(info)
        if info.es_festivo_nacional and info.nombre_festivo:
            motivo_dia = (
                f"Jornada festiva nacional ({info.nombre_festivo}): nivel base exponencial de "
                f"{base_demand:.1f} {producto.unidad_base.lower()}(s) para festivos"
            )
        elif info.es_sabado:
            motivo_dia = (
                f"Jornada de sábado: nivel base exponencial de {base_demand:.1f} "
                f"{producto.unidad_base.lower()}(s)"
            )
        else:
            motivo_dia = (
                f"Jornada de domingo: nivel base exponencial de {base_demand:.1f} "
                f"{producto.unidad_base.lower()}(s)"
            )

        if abs(net_trend_day) >= 0.002:
            signo = "+" if net_trend_day > 0 else ""
            motivo_dia += (
                f", ajuste por dinámica y tendencia de {signo}{net_trend_day * 100:.1f}%"
            )

        if abs(comp.estacionalidad_mensual_ratio) >= 0.002:
            signo_s = "+" if comp.estacionalidad_mensual_ratio > 0 else ""
            mes_nombre = _MONTH_NAMES_ES[info.fecha.month]
            motivo_dia += (
                f", factor estacional de {mes_nombre} ({signo_s}"
                f"{comp.estacionalidad_mensual_ratio * 100:.1f}%)"
            )

        if sobrante_dia > 0:
            motivo_dia += (
                f". Se descuentan {sobrante_dia} {producto.unidad_base.lower()}(s) de sobrantes "
                f"disponibles, sugiriendo producir {produccion_sugerida}."
            )
        else:
            motivo_dia += (
                f". Sin sobrantes previos aplicables; producción sugerida de {produccion_sugerida}."
            )

        planificacion_diaria.append(
            DiaPlanificacionDemanda(
                fecha=info.fecha,
                dia_semana=_WEEKDAY_NAMES_ES[info.fecha.weekday()],
                etiqueta_dia=etiqueta_dia,
                tipo_dia=dtype,
                es_sabado=info.es_sabado,
                es_domingo=info.es_domingo,
                es_festivo_nacional=info.es_festivo_nacional,
                nombre_festivo=info.nombre_festivo,
                producto_id=producto.id,
                producto_nombre=producto.nombre,
                unidad_base=producto.unidad_base,
                demanda_base_tipo_dia=_quantize_dec(base_demand, "0.01"),
                factor_ajuste_aplicado=_quantize_dec(factor_ajuste, "0.0001"),
                demanda_estimada=demanda_estimada,
                sobrantes_disponibles=sobrante_dia,
                produccion_sugerida=produccion_sugerida,
                rango_minimo_esperado=rango_min,
                rango_maximo_esperado=rango_max,
                explicacion_dia=motivo_dia,
            )
        )

    if applied_trend_ratios:
        representative_trend_pct = statistics.mean(applied_trend_ratios) * 100.0
    else:
        fallback_comp = _predict_demand_for_date(
            valid_points,
            fecha_inicio_horizonte,
            "domingo",
            precomputed_weights=weights,
            precomputed_smoothed=(global_w_mean, smoothed_by_type),
        )
        representative_trend_pct = (
            fallback_comp.impulso_reciente_ratio
            + fallback_comp.deriva_estructural_ratio
        ) * 100.0

    # Métricas de resumen histórico
    registros_reales = sum(
        1 for p in valid_points if p.es_historico and not p.es_sintetico
    )
    registros_sinteticos = sum(1 for p in valid_points if p.es_sintetico)
    registros_operativos = sum(1 for p in valid_points if p.es_operativo)
    total_valid = len(valid_points)
    prop_reales = (
        ((registros_reales + registros_operativos) / total_valid) * 100.0
        if total_valid > 0
        else 0.0
    )

    total_dias_cal = (effective_fecha_hasta - payload.fecha_desde).days + 1
    dias_op_cal = _count_operation_days_in_range(
        payload.fecha_desde, effective_fecha_hasta
    )
    dias_op_sin_ventas = max(0, dias_op_cal - total_valid)

    resumen_historico = ResumenHistoricoDemanda(
        fecha_desde=payload.fecha_desde,
        fecha_hasta=effective_fecha_hasta,
        fecha_minima_observada=valid_points[0].fecha,
        fecha_maxima_observada=valid_points[-1].fecha,
        total_dias_calendario_rango=total_dias_cal,
        dias_operativos_calendario_rango=dias_op_cal,
        dias_operativos_con_ventas=total_valid,
        dias_operativos_sin_ventas=dias_op_sin_ventas,
        fechas_no_operativas_excluidas=fechas_no_operativas_excluidas,
        registros_reales=registros_reales,
        registros_sinteticos=registros_sinteticos,
        registros_operativos=registros_operativos,
        proporcion_datos_reales=_quantize_dec(prop_reales, "0.01"),
        total_vendido_base=_quantize_dec(sum(all_quantities), "0.01"),
        promedio_diario_simple_base=_quantize_dec(global_simple_mean, "0.01"),
        promedio_diario_ponderado_base=_quantize_dec(global_w_mean, "0.01"),
        desviacion_estandar_base=_quantize_dec(global_std, "0.01"),
        tendencia_porcentual_aplicada=_quantize_dec(
            representative_trend_pct, "0.01"
        ),
        promedio_sobrante_historico_base=_quantize_dec(
            promedio_sobrante_hist, "0.01"
        ),
        ultimo_sobrante_registrado_base=_quantize_dec(
            ultimo_sobrante_reg, "0.01"
        ),
        fecha_ultimo_cierre=fecha_ultimo_cierre,
        perfiles_por_tipo_dia=perfiles_tipo_dia,
    )

    metricas_precision = _compute_backtest_metrics(valid_points)

    demanda_total_est = sum(d.demanda_estimada for d in planificacion_diaria)
    sobrantes_totales_disp = sum(
        d.sobrantes_disponibles for d in planificacion_diaria
    )
    produccion_total_sug = sum(
        d.produccion_sugerida for d in planificacion_diaria
    )

    # Construir recomendaciones explicables basadas en los resultados reales
    recomendaciones = _build_explainable_recommendations(
        producto=producto,
        horizonte_label=_HORIZON_LABELS[payload.horizonte],
        fecha_inicio_horizonte=fecha_inicio_horizonte,
        fecha_fin_horizonte=fecha_fin_horizonte,
        planificacion=planificacion_diaria,
        resumen=resumen_historico,
        metricas=metricas_precision,
        demanda_total=demanda_total_est,
        sobrantes_totales=sobrantes_totales_disp,
        produccion_total=produccion_total_sug,
    )

    return DemandForecastResponse(
        producto_id=producto.id,
        producto_nombre=producto.nombre,
        unidad_base=producto.unidad_base,
        horizonte=payload.horizonte,
        horizonte_etiqueta=_HORIZON_LABELS[payload.horizonte],
        fecha_inicio_horizonte=fecha_inicio_horizonte,
        fecha_fin_horizonte=fecha_fin_horizonte,
        total_dias_operativos_proyectados=len(planificacion_diaria),
        demanda_total_estimada=demanda_total_est,
        sobrantes_totales_disponibles=sobrantes_totales_disp,
        produccion_total_sugerida=produccion_total_sug,
        incluir_sinteticos=payload.incluir_sinteticos,
        resumen_historico=resumen_historico,
        metricas_precision=metricas_precision,
        planificacion_diaria=planificacion_diaria,
        recomendaciones=recomendaciones,
        generado_en=datetime.now(COLOMBIA_TZ).replace(tzinfo=None),
    )


def _build_explainable_recommendations(
    *,
    producto: Producto,
    horizonte_label: str,
    fecha_inicio_horizonte: date,
    fecha_fin_horizonte: date,
    planificacion: list[DiaPlanificacionDemanda],
    resumen: ResumenHistoricoDemanda,
    metricas: MetricasPrecisionModelo,
    demanda_total: int,
    sobrantes_totales: int,
    produccion_total: int,
) -> list[RecomendacionDemanda]:
    recs: list[RecomendacionDemanda] = []
    unidad_plural = (
        "unidades" if producto.unidad_base.lower() == "unidad" else "platos"
    )
    rango_horizonte_str = (
        f"{fecha_inicio_horizonte.isoformat()} a {fecha_fin_horizonte.isoformat()}"
    )

    # 1. Recomendación principal de producción y sobrantes disponibles
    if sobrantes_totales > 0:
        recs.append(
            RecomendacionDemanda(
                tipo="produccion",
                titulo=f"Planificación neta para {horizonte_label.lower()}",
                detalle=(
                    f"Para el período proyectado ({rango_horizonte_str}), se estima una demanda total de "
                    f"{demanda_total} {unidad_plural} de {producto.nombre} en {len(planificacion)} "
                    f"jornada(s) operativa(s). Al descontar por única vez {sobrantes_totales} {unidad_plural} "
                    f"de sobrantes disponibles del cierre previo ({resumen.fecha_ultimo_cierre}), "
                    f"la producción neta sugerida es de {produccion_total} {unidad_plural}."
                ),
            )
        )
    else:
        recs.append(
            RecomendacionDemanda(
                tipo="produccion",
                titulo=f"Planificación para {horizonte_label.lower()}",
                detalle=(
                    f"Para el período proyectado ({rango_horizonte_str}), se estima una demanda total de "
                    f"{demanda_total} {unidad_plural} de {producto.nombre} distribuida en "
                    f"{len(planificacion)} jornada(s) operativa(s) (promedio estimado de "
                    f"{round(demanda_total / max(1, len(planificacion)))} {unidad_plural} por jornada)."
                ),
            )
        )

    # 2. Comportamiento de calendario (sábados, domingos y festivos nacionales en el horizonte)
    festivos_horizonte = [
        f"{d.fecha.isoformat()} ({d.nombre_festivo})"
        for d in planificacion
        if d.es_festivo_nacional and d.nombre_festivo
    ]
    perfiles_map = {p.tipo_dia: p for p in resumen.perfiles_por_tipo_dia}
    sab_prom = perfiles_map["sabado"].promedio_ponderado_base
    dom_prom = perfiles_map["domingo"].promedio_ponderado_base
    fest_prom = perfiles_map["festivo"].promedio_ponderado_base

    if festivos_horizonte:
        recs.append(
            RecomendacionDemanda(
                tipo="calendario",
                titulo="Efecto de fines de semana y festivos colombianos",
                detalle=(
                    f"El horizonte incluye {len(festivos_horizonte)} festivo(s) nacional(es) oficial(es): "
                    f"{', '.join(festivos_horizonte[:4])}. El modelo diferencia el nivel esperado según "
                    f"el tipo de jornada: Sábados ({sab_prom} {unidad_plural}), "
                    f"Domingos ({dom_prom} {unidad_plural}) y Festivos ({fest_prom} {unidad_plural})."
                ),
            )
        )
    else:
        recs.append(
            RecomendacionDemanda(
                tipo="calendario",
                titulo="Comportamiento por día de operación",
                detalle=(
                    f"En el horizonte seleccionado no se presentan festivos nacionales adicionales; "
                    f"la operación se concentra en sábados (base ponderada de {sab_prom} {unidad_plural}) "
                    f"y domingos ({dom_prom} {unidad_plural})."
                ),
            )
        )

    # 3. Control de sobrantes históricos vs. producción
    if resumen.promedio_sobrante_historico_base > Decimal("0"):
        recs.append(
            RecomendacionDemanda(
                tipo="sobrantes",
                titulo="Control de sobrantes de producción",
                detalle=(
                    f"En el período histórico analizado, los cierres diarios de {producto.nombre} "
                    f"registraron un sobrante promedio de {resumen.promedio_sobrante_historico_base} {unidad_plural} "
                    "por jornada (cumpliendo Producción = Ventas + Sobrantes). Ajustar las tandas a la "
                    "producción sugerida permite cubrir la demanda evitando excedentes sistemáticos."
                ),
            )
        )

    # 4. Composición y calidad de los datos históricos
    excl_note = (
        f" Se excluyeron automáticamente {len(resumen.fechas_no_operativas_excluidas)} "
        "fecha(s) fuera del calendario operativo oficial para evitar sesgos."
        if resumen.fechas_no_operativas_excluidas
        else ""
    )
    recs.append(
        RecomendacionDemanda(
            tipo="datos",
            titulo="Trazabilidad de fuentes históricas utilizadas",
            detalle=(
                f"Cálculo respaldado por {resumen.dias_operativos_con_ventas} jornadas operativas "
                f"({resumen.registros_reales} históricas reales, {resumen.registros_operativos} operativas "
                f"y {resumen.registros_sinteticos} sintéticas; {resumen.proporcion_datos_reales}% datos reales/operativos)."
                f"{excl_note}"
            ),
        )
    )

    # 5. Precisión y nivel de confianza
    if metricas.mape_porcentaje is not None and metricas.mae_base is not None:
        recs.append(
            RecomendacionDemanda(
                tipo="precision",
                titulo=f"Confiabilidad del modelo: {metricas.nivel_confianza.upper()}",
                detalle=(
                    f"{metricas.nota_metodologica} Banda esperada por jornada de "
                    f"±{max(3, round(float(resumen.desviacion_estandar_base)))} {unidad_plural}."
                ),
            )
        )
    else:
        recs.append(
            RecomendacionDemanda(
                tipo="precision",
                titulo="Advertencia de tamaño muestral",
                detalle=metricas.nota_metodologica,
            )
        )

    return recs
