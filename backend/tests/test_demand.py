from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db, get_engine
from app.main import app
from app.models import (
    CierreDiario,
    DetalleVenta,
    Presentacion,
    Producto,
    Usuario,
    Venta,
)
from app.schemas.demand import DemandForecastRequest
from app.services.catalog import seed_initial_catalog
from app.services.colombian_calendar import (
    inspect_operation_date,
    is_valid_operation_date,
)
from app.services.demand import (
    MIN_HISTORICAL_OPERATION_DAYS,
    _DailyDemandPoint,
    _compute_backtest_metrics,
    generate_demand_forecast,
    get_demand_historical_context,
)
from app.services.excel_import import build_trace_tag

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def isolated_session():
    """Sesión transaccional aislada con SAVEPOINT y ROLLBACK automático al finalizar."""
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        for table_name in (
            "movimientos_inventario",
            "detalle_ventas",
            "ventas",
            "detalle_pedidos",
            "pedidos",
            "cierres_diarios",
            "producciones",
            "gastos",
            "presentaciones",
            "productos",
            "clientes",
            "usuarios",
        ):
            session.execute(text(f"DELETE FROM {table_name}"))
        session.flush()
        seed_initial_catalog(session, commit=False)
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def auth_headers(isolated_session: Session) -> dict[str, str]:
    user = Usuario(
        nombre_usuario="admin.demanda",
        nombre_completo="Administradora Demanda",
        password_hash=hash_password("ClaveSeguraDemanda2026!"),
        activo=True,
    )
    isolated_session.add(user)
    isolated_session.commit()
    token, _ = create_access_token(
        user_id=user.id,
        username=user.nombre_usuario,
        secret_key=get_settings().auth_secret_key,
        expires_delta=timedelta(minutes=60),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api_client(client, isolated_session: Session):
    def override_get_db():
        yield isolated_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_demand_request_schema_validations():
    # Normaliza alias de horizonte ("Próxima semana", "Próximo mes", "Próximo trimestre")
    req1 = DemandForecastRequest(
        producto_nombre="Hayacas",
        fecha_desde=date(2026, 6, 6),
        fecha_hasta=date(2026, 10, 31),
        horizonte="Próxima semana",  # type: ignore[arg-type]
    )
    assert req1.horizonte == "proxima_semana"

    req2 = DemandForecastRequest(
        producto_nombre="Lechona",
        fecha_desde=date(2026, 6, 6),
        fecha_hasta=date(2026, 10, 31),
        horizonte="Próximo trimestre",  # type: ignore[arg-type]
    )
    assert req2.horizonte == "proximo_trimestre"

    # Rechaza rango con fecha_desde > fecha_hasta
    with pytest.raises(ValidationError):
        DemandForecastRequest(
            producto_nombre="Hayaca",
            fecha_desde=date(2026, 10, 31),
            fecha_hasta=date(2026, 6, 6),
        )

    # Rechaza si no se especifica producto_id ni producto_nombre
    with pytest.raises(ValidationError):
        DemandForecastRequest(
            fecha_desde=date(2026, 6, 6),
            fecha_hasta=date(2026, 10, 31),
        )

    # Rechaza horizonte desconocido
    with pytest.raises(ValidationError):
        DemandForecastRequest(
            producto_nombre="Hayaca",
            fecha_desde=date(2026, 6, 6),
            fecha_hasta=date(2026, 10, 31),
            horizonte="proximo_lustro",  # type: ignore[arg-type]
        )


def test_historical_context_and_forecast_with_real_mysql_dataset():
    """Verifica en modo de solo lectura el motor estadístico sobre los 482 registros reales/sintéticos de MySQL."""
    engine = get_engine()
    with Session(engine) as session:
        ctx = get_demand_historical_context(session)
        assert ctx.fecha_minima_global == date(2024, 11, 2)
        assert ctx.fecha_maxima_global == date(2026, 10, 31)
        assert ctx.fecha_inicio_datos_reales == date(2026, 6, 6)
        assert ctx.fecha_maxima_datos_reales == date(2026, 10, 31)
        assert ctx.minimo_dias_operativos_requeridos == MIN_HISTORICAL_OPERATION_DAYS
        assert len(ctx.productos) == 2

        by_name = {p.producto_nombre: p for p in ctx.productos}
        assert by_name["Hayaca"].dias_reales == 49
        assert by_name["Hayaca"].dias_sinteticos == 192
        assert by_name["Lechona"].dias_reales == 49
        assert by_name["Lechona"].dias_sinteticos == 192

        # Probar los tres horizontes (proxima_semana, proximo_mes, proximo_trimestre) para Hayaca y Lechona
        for prod_name, expected_unit in (("Hayaca", "Unidad"), ("Lechona", "Plato")):
            for hor in ("proxima_semana", "proximo_mes", "proximo_trimestre"):
                req = DemandForecastRequest(
                    producto_nombre=prod_name,
                    fecha_desde=date(2026, 6, 6),
                    fecha_hasta=date(2026, 10, 31),
                    horizonte=hor,  # type: ignore[arg-type]
                )
                res = generate_demand_forecast(session, req)
                assert res.producto_nombre == prod_name
                assert res.unidad_base == expected_unit
                assert res.horizonte == hor
                assert res.resumen_historico.registros_reales == 49
                assert res.resumen_historico.registros_sinteticos == 0
                assert res.resumen_historico.proporcion_datos_reales == Decimal("100.00")
                assert res.metricas_precision.origen_evaluacion == "datos_reales_y_operativos"
                assert res.metricas_precision.mae_base is not None
                assert res.metricas_precision.mape_porcentaje is not None
                assert len(res.recomendaciones) >= 4
                assert any(prod_name in r.detalle for r in res.recomendaciones)

                # Verificar determinismo (segunda ejecución idéntica da exactamente los mismos valores)
                res_repeat = generate_demand_forecast(session, req)
                assert res.demanda_total_estimada == res_repeat.demanda_total_estimada
                assert res.produccion_total_sugerida == res_repeat.produccion_total_sugerida
                assert res.metricas_precision.mae_base == res_repeat.metricas_precision.mae_base
                assert res.metricas_precision.mape_porcentaje == res_repeat.metricas_precision.mape_porcentaje

                for d in res.planificacion_diaria:
                    assert is_valid_operation_date(d.fecha)
                    assert d.produccion_sugerida == max(0, d.demanda_estimada - d.sobrantes_disponibles)

        # Verificar tratamiento de la fecha anómala 2025-11-11 al incluir todo el historial
        req_full = DemandForecastRequest(
            producto_nombre="Lechona",
            fecha_desde=date(2024, 11, 2),
            fecha_hasta=date(2026, 10, 31),
            horizonte="proximo_trimestre",
            incluir_sinteticos=True,
        )
        res_full = generate_demand_forecast(session, req_full)
        assert date(2025, 11, 11) in res_full.resumen_historico.fechas_no_operativas_excluidas
        assert res_full.resumen_historico.registros_reales == 49
        assert res_full.resumen_historico.registros_sinteticos == 191


def test_synthetic_only_window_flags_methodological_warning():
    """Cuando el usuario elige un rango exclusivamente sintético, el modelo advierte que la precisión no es sobre datos reales."""
    engine = get_engine()
    with Session(engine) as session:
        req = DemandForecastRequest(
            producto_nombre="Hayaca",
            fecha_desde=date(2025, 1, 1),
            fecha_hasta=date(2025, 6, 30),
            horizonte="proximo_mes",
            incluir_sinteticos=True,
        )
        res = generate_demand_forecast(session, req)
        assert res.resumen_historico.registros_reales == 0
        assert res.resumen_historico.registros_sinteticos > 20
        assert res.metricas_precision.origen_evaluacion == "datos_sinteticos_advertencia"
        assert res.metricas_precision.nivel_confianza == "baja"
        assert "ADVERTENCIA METODOLÓGICA" in res.metricas_precision.nota_metodologica


def test_insufficient_historical_days_raises_422_and_small_sample_3_to_7_warns(
    isolated_session: Session,
):
    """Verifica rechazo con < 3 fechas operativas y advertencia con entre 3 y 7 fechas operativas."""
    hayaca = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Hayaca")
    )
    assert hayaca is not None
    pres = isolated_session.scalar(
        select(Presentacion).where(Presentacion.producto_id == hayaca.id)
    )
    assert pres is not None

    real_hist_tag = build_trace_tag(hoja="Ventas", fila=10, es_sintetico=False)
    synth_hist_tag = build_trace_tag(hoja="Ventas", fila=11, es_sintetico=True)

    # 1. Insertar solo 2 jornadas operativas -> debe fallar con 422
    op_dates = [
        (date(2026, 10, 3), 140, synth_hist_tag),
        (date(2026, 10, 4), 150, real_hist_tag),
    ]
    for d_op, qty, obs in op_dates:
        v = Venta(
            fecha_venta=datetime.combine(d_op, datetime.min.time()).replace(hour=12),
            estado="concretada",
            observaciones=obs,
        )
        isolated_session.add(v)
        isolated_session.flush()
        isolated_session.add(
            DetalleVenta(
                venta_id=v.id,
                presentacion_id=pres.id,
                cantidad=Decimal(str(qty)),
                precio_unitario=Decimal("10000"),
                factor_conversion_snapshot=Decimal("1"),
            )
        )
    isolated_session.commit()

    req_two = DemandForecastRequest(
        producto_id=hayaca.id,
        fecha_desde=date(2026, 10, 1),
        fecha_hasta=date(2026, 10, 31),
        horizonte="proxima_semana",
    )
    with pytest.raises(HTTPException) as exc_info:
        generate_demand_forecast(isolated_session, req_two)
    assert exc_info.value.status_code == 422
    assert "jornadas operativas" in str(exc_info.value.detail)

    # 2. Agregar 3 jornadas más (total = 5 jornadas: entre 3 y 7) con mezcla de orígenes:
    # 1 sintética, 2 históricas reales y 2 operativas
    more_dates = [
        (date(2026, 10, 10), 145, real_hist_tag),
        (date(2026, 10, 11), 155, "Venta operativa 1"),
        (date(2026, 10, 12), 148, "Venta operativa 2"),  # Festivo Día de la Raza
    ]
    for d_op, qty, obs in more_dates:
        v = Venta(
            fecha_venta=datetime.combine(d_op, datetime.min.time()).replace(hour=12),
            estado="concretada",
            observaciones=obs,
        )
        isolated_session.add(v)
        isolated_session.flush()
        isolated_session.add(
            DetalleVenta(
                venta_id=v.id,
                presentacion_id=pres.id,
                cantidad=Decimal(str(qty)),
                precio_unitario=Decimal("10000"),
                factor_conversion_snapshot=Decimal("1"),
            )
        )
    isolated_session.commit()

    res_five = generate_demand_forecast(isolated_session, req_two)
    assert res_five.resumen_historico.dias_operativos_con_ventas == 5
    assert res_five.resumen_historico.registros_sinteticos == 1
    assert res_five.resumen_historico.registros_reales == 2
    assert res_five.resumen_historico.registros_operativos == 2
    assert res_five.metricas_precision.nivel_confianza == "baja"
    assert (
        "ADVERTENCIA DE MUESTRA REDUCIDA" in res_five.metricas_precision.nota_metodologica
        or "solo 5 jornadas operativas" in res_five.metricas_precision.nota_metodologica
    )


def test_mape_excludes_zero_actual_observations_preserving_sample_count():
    """Verifica que observaciones con valor real 0 se excluyan del cálculo de MAPE sin alterar muestras_evaluadas."""
    sample_dates = [
        date(2026, 10, 3),
        date(2026, 10, 4),
        date(2026, 10, 10),
        date(2026, 10, 11),
        date(2026, 10, 12),
        date(2026, 10, 17),
        date(2026, 10, 18),
    ]
    # Caso A: algunas observaciones de prueba son 0 y otras > 0
    quantities_mixed = [120.0, 130.0, 125.0, 0.0, 140.0, 0.0, 135.0]
    pts_mixed = [
        _DailyDemandPoint(
            fecha=d,
            cantidad_base=q,
            tipo_dia="sabado" if d.weekday() == 5 else "domingo",
            es_historico=False,
            es_sintetico=False,
            es_operativo=True,
            cal_info=inspect_operation_date(d),
        )
        for d, q in zip(sample_dates, quantities_mixed)
    ]
    metrics_mixed = _compute_backtest_metrics(pts_mixed)
    # 7 puntos desde índice 0..6 -> se evalúan los índices >= 3 (4 puntos en total)
    assert metrics_mixed.muestras_evaluadas == 4
    assert metrics_mixed.mae_base is not None
    assert metrics_mixed.mape_porcentaje is not None
    assert metrics_mixed.mape_porcentaje > Decimal("0")

    # Caso B: todas las observaciones evaluadas (índices >= 3) tienen valor 0 -> MAPE debe ser None (no 0%)
    quantities_all_zero_test = [120.0, 130.0, 125.0, 0.0, 0.0, 0.0, 0.0]
    pts_zero = [
        _DailyDemandPoint(
            fecha=d,
            cantidad_base=q,
            tipo_dia="sabado" if d.weekday() == 5 else "domingo",
            es_historico=False,
            es_sintetico=False,
            es_operativo=True,
            cal_info=inspect_operation_date(d),
        )
        for d, q in zip(sample_dates, quantities_all_zero_test)
    ]
    metrics_zero = _compute_backtest_metrics(pts_zero)
    assert metrics_zero.muestras_evaluadas == 4
    assert metrics_zero.mae_base is not None
    assert metrics_zero.mape_porcentaje is None
    assert metrics_zero.precision_estimada_porcentaje is None


def test_demand_routes_require_authentication(api_client):
    assert api_client.get("/prediccion/contexto-historico").status_code == 401
    assert (
        api_client.post(
            "/prediccion/estimar",
            json={
                "producto_nombre": "Hayaca",
                "fecha_desde": "2026-06-06",
                "fecha_hasta": "2026-10-31",
                "horizonte": "proxima_semana",
            },
        ).status_code
        == 401
    )
    assert (
        api_client.get(
            "/prediccion/estimacion?producto_nombre=Hayaca&fecha_desde=2026-06-06&fecha_hasta=2026-10-31"
        ).status_code
        == 401
    )


def test_demand_rest_endpoints_post_and_get_integration(
    api_client,
    auth_headers: dict[str, str],
    isolated_session: Session,
):
    hayaca = isolated_session.scalar(
        select(Producto).where(Producto.nombre == "Hayaca")
    )
    assert hayaca is not None
    pres = isolated_session.scalar(
        select(Presentacion).where(Presentacion.producto_id == hayaca.id)
    )
    assert pres is not None

    # Poblar 8 jornadas operativas válidas de octubre de 2026
    sample_days = [
        (date(2026, 10, 10), 150),
        (date(2026, 10, 11), 160),
        (date(2026, 10, 12), 148),  # Festivo Día de la Raza
        (date(2026, 10, 17), 154),
        (date(2026, 10, 18), 162),
        (date(2026, 10, 24), 156),
        (date(2026, 10, 25), 164),
        (date(2026, 10, 31), 158),
    ]
    for d_op, qty in sample_days:
        v = Venta(
            fecha_venta=datetime.combine(d_op, datetime.min.time()).replace(hour=12),
            estado="concretada",
            observaciones="Venta operativa prueba",
        )
        isolated_session.add(v)
        isolated_session.flush()
        isolated_session.add(
            DetalleVenta(
                venta_id=v.id,
                presentacion_id=pres.id,
                cantidad=Decimal(str(qty)),
                precio_unitario=Decimal("10000"),
                factor_conversion_snapshot=Decimal("1"),
            )
        )
        isolated_session.add(
            CierreDiario(
                producto_id=hayaca.id,
                fecha=d_op,
                existencia_calculada_base=Decimal("10"),
                sobrante_real_base=Decimal("10"),
                observaciones="Cierre operativo prueba",
            )
        )
    isolated_session.commit()

    # 1. Contexto histórico vía GET /prediccion/contexto-historico
    ctx_resp = api_client.get(
        "/prediccion/contexto-historico",
        headers=auth_headers,
    )
    assert ctx_resp.status_code == 200, ctx_resp.text
    ctx_json = ctx_resp.json()
    assert ctx_json["fecha_minima_global"] == "2026-10-10"
    assert ctx_json["fecha_maxima_global"] == "2026-10-31"
    assert ctx_json["minimo_dias_operativos_requeridos"] == 3

    # 2. Estimación vía POST /prediccion/estimar
    post_resp = api_client.post(
        "/prediccion/estimar",
        headers=auth_headers,
        json={
            "producto_nombre": "Hayacas",
            "fecha_desde": "2026-10-10",
            "fecha_hasta": "2026-10-31",
            "horizonte": "Próxima semana",
        },
    )
    assert post_resp.status_code == 200, post_resp.text
    post_data = post_resp.json()
    assert post_data["producto_nombre"] == "Hayaca"
    assert post_data["horizonte"] == "proxima_semana"
    assert post_data["total_dias_operativos_proyectados"] == 3
    assert post_data["sobrantes_totales_disponibles"] == 10
    assert (
        post_data["produccion_total_sugerida"]
        == post_data["demanda_total_estimada"] - post_data["sobrantes_totales_disponibles"]
    )
    assert len(post_data["recomendaciones"]) >= 4

    # 3. Estimación vía GET /prediccion/estimacion con query params equivalentes
    get_resp = api_client.get(
        "/prediccion/estimacion"
        "?producto_nombre=Hayacas&fecha_desde=2026-10-10&fecha_hasta=2026-10-31&horizonte=proxima_semana",
        headers=auth_headers,
    )
    assert get_resp.status_code == 200, get_resp.text
    get_data = get_resp.json()
    assert get_data["demanda_total_estimada"] == post_data["demanda_total_estimada"]
    assert get_data["produccion_total_sugerida"] == post_data["produccion_total_sugerida"]

    # 4. Errores controlados en endpoints REST (422 rango invertido, 404 producto inexistente)
    bad_range = api_client.get(
        "/prediccion/estimacion"
        "?producto_nombre=Hayaca&fecha_desde=2026-10-31&fecha_hasta=2026-10-10",
        headers=auth_headers,
    )
    assert bad_range.status_code == 422

    not_found = api_client.post(
        "/prediccion/estimar",
        headers=auth_headers,
        json={
            "producto_nombre": "Empanada",
            "fecha_desde": "2026-10-10",
            "fecha_hasta": "2026-10-31",
            "horizonte": "proxima_semana",
        },
    )
    assert not_found.status_code == 404


def test_frontend_demand_integration_and_mysql_historical_integrity():
    """Verifica la integración del frontend de Predicción de Demanda y la integridad intacta de MySQL."""
    api_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "demand"
        / "services"
        / "demandApi.js"
    ).read_text(encoding="utf-8")
    page_code = (
        PROJECT_ROOT
        / "src"
        / "features"
        / "demand"
        / "pages"
        / "DemandPage.jsx"
    ).read_text(encoding="utf-8")

    # 1. Servicio demandApi.js usa apiRequest y consume los endpoints reales
    assert "apiRequest" in api_code
    assert "/prediccion/contexto-historico" in api_code
    assert "/prediccion/estimar" in api_code
    assert "buildDemandReportCsv" in api_code
    assert "downloadDemandReportCsv" in api_code
    assert "insufficient_data" in api_code

    # 2. DemandPage.jsx está conectada con demandApi.js, sin valores simulados ni cálculos duplicados
    assert "getDemandHistoricalContext" in page_code
    assert "requestDemandForecast" in page_code
    assert "downloadDemandReportCsv" in page_code
    assert "180 unidades" not in page_code
    assert "Valor estático de muestra" not in page_code
    assert "proxima_semana" in page_code
    assert "proximo_mes" in page_code
    assert "proximo_trimestre" in page_code
    assert "incluirSinteticos" in page_code
    assert "No disponible" in page_code

    # 3. Verificar que los 482 registros históricos en ventas, producciones y cierres_diarios siguen intactos
    engine = get_engine()
    with engine.connect() as conn:
        ventas_hist = conn.execute(
            text(
                "SELECT COUNT(*) FROM ventas WHERE observaciones LIKE '%IMPORTACION_EXCEL|%'"
            )
        ).scalar_one()
        prod_hist = conn.execute(
            text(
                "SELECT COUNT(*) FROM producciones WHERE observaciones LIKE '%IMPORTACION_EXCEL|%'"
            )
        ).scalar_one()
        cierres_hist = conn.execute(
            text(
                "SELECT COUNT(*) FROM cierres_diarios WHERE observaciones LIKE '%IMPORTACION_EXCEL|%'"
            )
        ).scalar_one()

    assert ventas_hist == 482
    assert prod_hist == 482
    assert cierres_hist == 482
