from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import math
import statistics

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
) -> list[float]:
    n = len(points)
    if n == 0:
        return []
    has_non_synthetic = any(not p.es_sintetico for p in points)
    has_synthetic = any(p.es_sintetico for p in points)
    mixed_origins = has_non_synthetic and has_synthetic

    weights: list[float] = []
    for idx, pt in enumerate(points):
        recency_w = 0.5 + 0.5 * (idx / (n - 1)) if n > 1 else 1.0
        origin_w = 0.65 if (mixed_origins and pt.es_sintetico) else 1.0
        weights.append(recency_w * origin_w)
    return weights


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    if not values:
        return 0.0
    total_w = sum(weights)
    if total_w <= 0:
        return statistics.mean(values)
    return sum(v * w for v, w in zip(values, weights)) / total_w


def _compute_smoothed_day_type_means(
    points: list[_DailyDemandPoint],
    weights: list[float],
) -> tuple[float, dict[TipoDiaOperativoLiteral, float]]:
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
            alpha = min(1.0, len(sub_vals) / 5.0)
            smoothed[dtype] = alpha * raw_w_mean + (1.0 - alpha) * global_w_mean
    return global_w_mean, smoothed


def _compute_damped_trend_ratio(
    points: list[_DailyDemandPoint],
    weights: list[float],
) -> float:
    """Calcula un ajuste relativo de tendencia reciente acotado a [-0.06, +0.06]."""
    n = len(points)
    if n < 6:
        return 0.0
    global_w_mean = _weighted_mean([p.cantidad_base for p in points], weights)
    if global_w_mean <= 0:
        return 0.0

    recent_slice = max(3, min(10, n // 3))
    recent_points = points[-recent_slice:]
    recent_weights = weights[-recent_slice:]
    recent_w_mean = _weighted_mean(
        [p.cantidad_base for p in recent_points], recent_weights
    )
    raw_diff_ratio = (recent_w_mean - global_w_mean) / global_w_mean
    damped = raw_diff_ratio * 0.35
    return max(-0.06, min(0.06, damped))


def _compute_backtest_metrics(
    points: list[_DailyDemandPoint],
) -> MetricasPrecisionModelo:
    n = len(points)
    non_synthetic_indices = [
        idx for idx, p in enumerate(points) if not p.es_sintetico
    ]

    # Seleccionar índices de prueba priorizando observaciones reales/operativas
    if len(non_synthetic_indices) >= 4:
        eval_indices = [idx for idx in non_synthetic_indices if idx >= 3]
        if len(eval_indices) > 20:
            eval_indices = eval_indices[-20:]
        origen_eval: OrigenEvaluacionLiteral = "datos_reales_y_operativos"
    elif n >= 5:
        eval_count = min(15, max(2, n // 3))
        eval_indices = list(range(max(3, n - eval_count), n))
        origen_eval = "datos_sinteticos_advertencia"
    else:
        return MetricasPrecisionModelo(
            metodo="Descomposición por tipo de día operativo ponderada por recencia",
            origen_evaluacion="muestra_insuficiente",
            muestras_evaluadas=0,
            mae_base=None,
            rmse_base=None,
            mape_porcentaje=None,
            precision_estimada_porcentaje=None,
            nivel_confianza="baja",
            nota_metodologica=(
                f"El período seleccionado cuenta con solo {n} jornadas operativas válidas. "
                f"Se recomiendan al menos {OPTIMAL_HISTORICAL_OPERATION_DAYS} jornadas reales u operativas "
                "para calcular métricas de precisión por validación retrospectiva (walk-forward)."
            ),
        )

    abs_errors: list[float] = []
    sq_errors: list[float] = []
    ape_values: list[float] = []

    for test_idx in eval_indices:
        train_pts = points[:test_idx]
        train_w = _compute_observation_weights(train_pts)
        _, smoothed_by_type = _compute_smoothed_day_type_means(
            train_pts, train_w
        )
        trend_ratio = _compute_damped_trend_ratio(train_pts, train_w)

        target_pt = points[test_idx]
        pred = smoothed_by_type[target_pt.tipo_dia] * (1.0 + trend_ratio)
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
        and origen_eval == "datos_reales_y_operativos"
        and len(non_synthetic_indices) >= 15
        and mape is not None
        and mape <= 12.0
    ):
        confianza: NivelConfianzaLiteral = "alta"
    elif (
        not small_sample_warning
        and origen_eval == "datos_reales_y_operativos"
        and len(non_synthetic_indices) >= 6
        and mape is not None
        and mape <= 18.0
    ):
        confianza = "media"
    else:
        confianza = "baja"

    mape_str = f"{mape:.2f}% MAPE" if mape is not None else "MAPE no disponible"
    if origen_eval == "datos_reales_y_operativos":
        nota = (
            f"Validación walk-forward evaluada exclusivamente sobre {len(eval_indices)} "
            "jornadas reales/operativas (sin usar registros sintéticos como verdad de prueba). "
            f"Error medio absoluto de {mae:.2f} unidades base ({mape_str})."
        )
    else:
        nota = (
            "ADVERTENCIA METODOLÓGICA: El rango histórico seleccionado contiene menos de 4 "
            "jornadas reales u operativas. Las métricas se calcularon sobre registros sintéticos "
            "y se reportan únicamente como referencia interna; no representan precisión sobre "
            "observaciones reales del negocio."
        )

    if small_sample_warning:
        nota = (
            f"ADVERTENCIA DE MUESTRA REDUCIDA: El período seleccionado cuenta con solo {n} "
            f"jornadas operativas válidas (se recomiendan al menos {OPTIMAL_HISTORICAL_OPERATION_DAYS}). "
            f"{nota}"
        )

    return MetricasPrecisionModelo(
        metodo="Descomposición por tipo de día operativo ponderada por recencia",
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

    start_dt = datetime.combine(payload.fecha_desde, datetime.min.time())
    end_dt = datetime.combine(payload.fecha_hasta, datetime.max.time())

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
        if not payload.incluir_sinteticos and es_sintetico:
            continue

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
        filtro_msg = (
            " (excluyendo datos sintéticos)"
            if not payload.incluir_sinteticos
            else ""
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"El período histórico seleccionado ({payload.fecha_desde.isoformat()} a "
                f"{payload.fecha_hasta.isoformat()}){filtro_msg} solo contiene "
                f"{len(valid_points)} jornadas operativas válidas con ventas para '{producto.nombre}'. "
                f"Se requieren al menos {MIN_HISTORICAL_OPERATION_DAYS} jornadas operativas "
                "para generar una estimación estadística verificable."
            ),
        )

    # Consultar cierres diarios en el periodo para analizar sobrantes históricos
    cierres_rows = list(
        session.scalars(
            select(CierreDiario)
            .where(
                CierreDiario.producto_id == producto.id,
                CierreDiario.fecha >= payload.fecha_desde,
                CierreDiario.fecha <= payload.fecha_hasta,
            )
            .order_by(CierreDiario.fecha.asc())
        ).all()
    )
    sobrantes_hist_vals: list[float] = []
    for c in cierres_rows:
        _, c_sin, _ = classify_trace_origin(c.observaciones)
        if not payload.incluir_sinteticos and c_sin:
            continue
        sobrantes_hist_vals.append(float(c.sobrante_real_base))

    promedio_sobrante_hist = (
        statistics.mean(sobrantes_hist_vals) if sobrantes_hist_vals else 0.0
    )

    # Pesos por recencia y origen de dato
    weights = _compute_observation_weights(valid_points)
    all_quantities = [p.cantidad_base for p in valid_points]
    global_simple_mean = statistics.mean(all_quantities)
    global_std = (
        statistics.stdev(all_quantities) if len(all_quantities) > 1 else 0.0
    )
    global_w_mean, smoothed_by_type = _compute_smoothed_day_type_means(
        valid_points, weights
    )
    trend_ratio = _compute_damped_trend_ratio(valid_points, weights)

    # Perfiles por tipo de día (sábado, domingo, festivo)
    perfiles_tipo_dia: list[PerfilTipoDiaResponse] = []
    for dtype in ("sabado", "domingo", "festivo"):
        pts_d = [p for p in valid_points if p.tipo_dia == dtype]
        w_d = [w for p, w in zip(valid_points, weights) if p.tipo_dia == dtype]
        if pts_d:
            vals_d = [p.cantidad_base for p in pts_d]
            s_mean = statistics.mean(vals_d)
            w_mean = smoothed_by_type[dtype]
            min_v = min(vals_d)
            max_v = max(vals_d)
        else:
            s_mean = global_simple_mean
            w_mean = smoothed_by_type[dtype]
            min_v = min(all_quantities)
            max_v = max(all_quantities)

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

    # Determinar fecha de inicio y fin del horizonte futuro
    ref_date = payload.fecha_referencia or payload.fecha_hasta
    fecha_inicio_horizonte = ref_date + timedelta(days=1)
    horizon_days = _HORIZON_DAYS_MAP[payload.horizonte]
    fecha_fin_horizonte = fecha_inicio_horizonte + timedelta(
        days=horizon_days - 1
    )

    # Consultar último cierre diario disponible hasta ref_date para sobrantes iniciales
    ultimo_cierre = session.scalar(
        select(CierreDiario)
        .where(
            CierreDiario.producto_id == producto.id,
            CierreDiario.fecha <= ref_date,
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

    # Generar las fechas operativas futuras dentro del horizonte
    future_op_dates: list[OperationDateInfo] = []
    cursor = fecha_inicio_horizonte
    while cursor <= fecha_fin_horizonte:
        info = inspect_operation_date(cursor)
        if info.es_dia_operacion:
            future_op_dates.append(info)
        cursor += timedelta(days=1)

    # Determinar sobrante disponible inicial aplicable a la primera jornada proyectada
    if payload.sobrante_disponible_inicial is not None:
        sobrante_remanente = int(payload.sobrante_disponible_inicial)
    elif (
        ultimo_cierre is not None
        and future_op_dates
        and 0 <= (future_op_dates[0].fecha - ultimo_cierre.fecha).days <= 7
    ):
        sobrante_remanente = int(round(ultimo_sobrante_reg))
    else:
        sobrante_remanente = 0

    first_op_date = future_op_dates[0].fecha if future_op_dates else None

    # Construir la tabla de planificación diaria
    planificacion_diaria: list[DiaPlanificacionDemanda] = []
    for info in future_op_dates:
        dtype = _classify_operation_day_type(info)
        base_demand = smoothed_by_type[dtype]

        # Factor de ajuste combinando tendencia reciente acotada
        factor_ajuste = 1.0 + trend_ratio
        raw_est = base_demand * factor_ajuste
        demanda_estimada = max(1, int(round(raw_est)))

        # El sobrante inicial solo se aprovecha en el ciclo inmediato (máx 2 días del primer bloque operativo)
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
        band = max(3.0, global_std if global_std > 0 else base_demand * 0.08)
        rango_min = max(1, int(round(raw_est - band)))
        rango_max = max(demanda_estimada, int(round(raw_est + band)))

        etiqueta_dia = _build_day_label(info)
        if info.es_festivo_nacional and info.nombre_festivo:
            motivo_dia = (
                f"Jornada festiva nacional ({info.nombre_festivo}): base histórica ponderada de "
                f"{base_demand:.1f} {producto.unidad_base.lower()}(s) para festivos"
            )
        elif info.es_sabado:
            motivo_dia = (
                f"Jornada de sábado: base histórica ponderada de {base_demand:.1f} "
                f"{producto.unidad_base.lower()}(s)"
            )
        else:
            motivo_dia = (
                f"Jornada de domingo: base histórica ponderada de {base_demand:.1f} "
                f"{producto.unidad_base.lower()}(s)"
            )

        if abs(trend_ratio) >= 0.005:
            signo = "+" if trend_ratio > 0 else ""
            motivo_dia += f", ajuste por tendencia reciente de {signo}{trend_ratio * 100:.1f}%"

        if sobrante_dia > 0:
            motivo_dia += (
                f". Se descuentan {sobrante_dia} {producto.unidad_base.lower()}(s) de sobrantes "
                f"disponibles, sugiriendo producir {produccion_sugerida}."
            )
        else:
            motivo_dia += f". Sin sobrantes previos aplicables; producción sugerida de {produccion_sugerida}."

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

    total_dias_cal = (payload.fecha_hasta - payload.fecha_desde).days + 1
    dias_op_cal = _count_operation_days_in_range(
        payload.fecha_desde, payload.fecha_hasta
    )
    dias_op_sin_ventas = max(0, dias_op_cal - total_valid)

    resumen_historico = ResumenHistoricoDemanda(
        fecha_desde=payload.fecha_desde,
        fecha_hasta=payload.fecha_hasta,
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
        tendencia_porcentual_aplicada=_quantize_dec(trend_ratio * 100.0, "0.01"),
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
        generado_en=datetime.now(timezone.utc).replace(tzinfo=None),
    )


def _build_explainable_recommendations(
    *,
    producto: Producto,
    horizonte_label: str,
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

    # 1. Recomendación principal de producción y sobrantes disponibles
    if sobrantes_totales > 0:
        recs.append(
            RecomendacionDemanda(
                tipo="produccion",
                titulo=f"Planificación neta para {horizonte_label.lower()}",
                detalle=(
                    f"Se proyecta una demanda total de {demanda_total} {unidad_plural} de {producto.nombre} "
                    f"en {len(planificacion)} jornadas operativas. Al aprovechar {sobrantes_totales} {unidad_plural} "
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
                    f"Se proyecta una demanda total de {demanda_total} {unidad_plural} de {producto.nombre} "
                    f"distribuida en {len(planificacion)} jornadas operativas (promedio estimado de "
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
