import { useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import Button from '../../../components/ui/Button.jsx';
import PageHeader from '../../../components/ui/PageHeader.jsx';
import {
  downloadDemandReportCsv,
  getDemandHistoricalContext,
  normalizeDemandProductName,
  requestDemandForecast,
} from '../services/demandApi.js';

const numberFormatter = new Intl.NumberFormat('es-CO');
const dateFormatter = new Intl.DateTimeFormat('es-CO', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  timeZone: 'America/Bogota',
});

function formatIsoDate(dateStr) {
  if (!dateStr || typeof dateStr !== 'string') return 'No disponible';
  const clean = dateStr.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(clean)) return dateStr;
  return dateFormatter.format(new Date(`${clean}T12:00:00-05:00`));
}

function formatUnitPlural(unidadBase, count = 2) {
  const base = String(unidadBase || 'Unidad').trim().toLowerCase();
  if (base === 'plato') return Number(count) === 1 ? 'plato' : 'platos';
  return Number(count) === 1 ? 'unidad' : 'unidades';
}

function formatMetricValue(value, suffix = '') {
  if (value === null || value === undefined || value === '') {
    return 'No disponible';
  }
  const num = Number(value);
  if (Number.isNaN(num)) return 'No disponible';
  return `${numberFormatter.format(num)}${suffix}`;
}

function SparklesIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 14.3 9.7 21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3L12 3ZM19 2v4m-2-2h4M5 17v4m-2-2h4" /></svg>;
}

function BulbIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.7 17h4.6M12 3v1m6.4 1.6-.7.7M21 12h-1M4 12H3m3.3-5.7-.7-.7m2.8 9.9a5 5 0 1 1 7.1 0l-.5.5a3.4 3.4 0 0 0-1 2.4v.5a2 2 0 1 1-4 0v-.5a3.4 3.4 0 0 0-1-2.4l-.5-.5Z" /></svg>;
}

function DownloadIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0 4.5-4.5M12 15l-4.5-4.5M4 16.5v2.25A2.25 2.25 0 0 0 6.25 21h11.5A2.25 2.25 0 0 0 20 18.75V16.5" /></svg>;
}

const DEFAULT_PRODUCTS = [
  { producto_id: null, producto_nombre: 'Hayaca', label: 'Hayacas', unidad_base: 'Unidad' },
  { producto_id: null, producto_nombre: 'Lechona', label: 'Lechona', unidad_base: 'Plato' },
];

export default function DemandPage() {
  const outletContext = useOutletContext() || {};
  const openMenu = outletContext.openMenu || (() => {});

  const [contextoHistorico, setContextoHistorico] = useState(null);
  const [isLoadingContext, setIsLoadingContext] = useState(true);
  const [contextError, setContextError] = useState('');

  const [productoSeleccionado, setProductoSeleccionado] = useState('Hayaca');
  const [periodoHistorico, setPeriodoHistorico] = useState({
    fechaDesde: '',
    fechaHasta: '',
  });
  const [horizonte, setHorizonte] = useState('proxima_semana');

  const [forecast, setForecast] = useState(null);
  const [isEstimating, setIsEstimating] = useState(false);
  const [forecastError, setForecastError] = useState('');
  const [reportNotice, setReportNotice] = useState('');

  useEffect(() => {
    let isCancelled = false;
    const controller = new AbortController();
    setIsLoadingContext(true);
    setContextError('');

    getDemandHistoricalContext({ signal: controller.signal })
      .then((ctx) => {
        if (isCancelled || controller.signal.aborted) return;
        setContextoHistorico(ctx);
        setContextError('');
        const firstProd =
          Array.isArray(ctx?.productos) && ctx.productos.length > 0
            ? ctx.productos[0]
            : null;
        const minDate =
          firstProd?.fecha_minima_ventas ||
          ctx?.fecha_minima_global ||
          ctx?.fecha_inicio_datos_reales ||
          '';
        const maxDate =
          firstProd?.fecha_maxima_ventas ||
          ctx?.fecha_maxima_global ||
          ctx?.fecha_maxima_datos_reales ||
          '';

        setPeriodoHistorico((current) => ({
          fechaDesde: current.fechaDesde || minDate,
          fechaHasta: current.fechaHasta || maxDate,
        }));
      })
      .catch((err) => {
        if (isCancelled || controller.signal.aborted || err?.name === 'AbortError') {
          return;
        }
        const message = String(err?.message || '');
        const specificMessage =
          err?.kind === 'auth'
            ? 'Tu sesión ha expirado. Por favor inicia sesión nuevamente.'
            : message && !message.toLowerCase().includes('conectar con el servidor')
              ? message
              : 'No fue posible sincronizar automáticamente el calendario histórico. Puedes indicar las fechas de análisis y generar la estimación.';
        setContextError(specificMessage);
      })
      .finally(() => {
        if (!isCancelled && !controller.signal.aborted) {
          setIsLoadingContext(false);
        }
      });

    return () => {
      isCancelled = true;
      controller.abort();
    };
  }, []);

  const productOptions = useMemo(() => {
    if (
      Array.isArray(contextoHistorico?.productos) &&
      contextoHistorico.productos.length > 0
    ) {
      return contextoHistorico.productos.map((item) => ({
        ...item,
        label: item.producto_nombre === 'Hayaca' ? 'Hayacas' : item.producto_nombre,
      }));
    }
    return DEFAULT_PRODUCTS;
  }, [contextoHistorico]);

  const activeProductContext = useMemo(() => {
    const canonical = normalizeDemandProductName(productoSeleccionado);
    return (
      productOptions.find((item) => item.producto_nombre === canonical) ||
      productOptions[0]
    );
  }, [productOptions, productoSeleccionado]);

  const dateBounds = useMemo(() => {
    const minGlobal = contextoHistorico?.fecha_minima_global;
    const maxGlobal = contextoHistorico?.fecha_maxima_global;

    const minProd = activeProductContext?.fecha_minima_ventas;
    const maxProd = activeProductContext?.fecha_maxima_ventas;

    return {
      min: minProd || minGlobal || '',
      max: maxProd || maxGlobal || '',
    };
  }, [activeProductContext, contextoHistorico]);

  function handleProductoChange(event) {
    const nextProducto = normalizeDemandProductName(event.target.value);
    setProductoSeleccionado(nextProducto);
    setForecastError('');
    setReportNotice('');

    const nextProdCtx = productOptions.find(
      (item) => item.producto_nombre === nextProducto
    );
    if (nextProdCtx) {
      const nextMin = nextProdCtx.fecha_minima_ventas;
      const nextMax = nextProdCtx.fecha_maxima_ventas;
      const prevMin = activeProductContext?.fecha_minima_ventas;
      const prevMax = activeProductContext?.fecha_maxima_ventas;

      setPeriodoHistorico((current) => ({
        fechaDesde:
          !current.fechaDesde ||
          current.fechaDesde === prevMin ||
          (nextMin && current.fechaDesde < nextMin)
            ? nextMin || current.fechaDesde
            : current.fechaDesde,
        fechaHasta:
          !current.fechaHasta ||
          current.fechaHasta === prevMax ||
          (nextMax && current.fechaHasta > nextMax)
            ? nextMax || current.fechaHasta
            : current.fechaHasta,
      }));
    }
  }

  const fechasIncompletas = Boolean(
    !periodoHistorico.fechaDesde || !periodoHistorico.fechaHasta
  );
  const rangoHistoricoInvalido = Boolean(
    periodoHistorico.fechaDesde &&
      periodoHistorico.fechaHasta &&
      periodoHistorico.fechaDesde > periodoHistorico.fechaHasta
  );

  async function handleGenerateForecast() {
    if (rangoHistoricoInvalido || fechasIncompletas || isEstimating) {
      return;
    }

    setIsEstimating(true);
    setForecastError('');
    setReportNotice('');
    // Limpiar resultado previo para no mostrar datos anteriores como si fueran de la nueva consulta
    setForecast(null);

    try {
      const response = await requestDemandForecast({
        productoId: activeProductContext?.producto_id ?? undefined,
        productoNombre:
          activeProductContext?.producto_nombre || productoSeleccionado,
        fechaDesde: periodoHistorico.fechaDesde,
        fechaHasta: periodoHistorico.fechaHasta,
        horizonte,
        incluirSinteticos: true,
      });
      setForecast(response);
      setContextError('');
    } catch (err) {
      setForecastError(
        err?.message ||
          'No fue posible generar la estimación de demanda con los parámetros seleccionados.'
      );
    } finally {
      setIsEstimating(false);
    }
  }

  function handleDownloadReport() {
    if (!forecast || isEstimating) return;
    try {
      const fileName = downloadDemandReportCsv(forecast);
      setReportNotice(`Reporte exportado: ${fileName}`);
    } catch (err) {
      setForecastError(
        err?.message || 'No fue posible exportar el reporte de predicción.'
      );
    }
  }

  const resumen = forecast?.resumen_historico;
  const metricas = forecast?.metricas_precision;
  const planificacion = Array.isArray(forecast?.planificacion_diaria)
    ? forecast.planificacion_diaria
    : [];
  const recomendaciones = Array.isArray(forecast?.recomendaciones)
    ? forecast.recomendaciones
    : [];

  const hasSampleWarning = Boolean(
    forecast &&
      (metricas?.origen_evaluacion === 'muestra_insuficiente' ||
        (resumen?.dias_operativos_con_ventas ?? 0) <
          (contextoHistorico?.dias_operativos_recomendados ?? 8))
  );

  const badgeLabel = useMemo(() => {
    if (isEstimating) return 'Calculando estimación...';
    if (!forecast) return 'Pendiente de estimación';
    const confianza = String(metricas?.nivel_confianza || 'media').toUpperCase();
    return `Confianza ${confianza} · ${resumen?.dias_operativos_con_ventas ?? 0} jornadas analizadas`;
  }, [forecast, isEstimating, metricas, resumen]);

  return <div className="demand-page">
    <style>{`
      .demand-fields > .demand-field:first-child > select,
      .demand-fields > .demand-field:last-child > select { margin-top: 19px; }
      .demand-plan-table td:nth-child(1),
      .demand-plan-table td:nth-child(2) { text-align: left; color: #1e1c1a; }
      .demand-plan-table td:nth-child(n+3) { text-align: right; color: #1e1c1a; font-variant-numeric: tabular-nums; }
      .demand-plan-table td.demand-plan-empty { text-align: center; color: #827b72; }
      @media (max-width: 900px) {
        .demand-fields > .demand-field:first-child > select,
        .demand-fields > .demand-field:last-child > select { margin-top: 0; }
      }
    `}</style>
    <button className="orders-mobile-menu demand-mobile-menu" type="button" aria-label="Abrir menú" onClick={openMenu}><span /><span /><span /></button>
    <PageHeader title="Predicción de demanda" description="Estima la demanda futura para apoyar la planificación de la producción." />

    <section className="demand-card demand-config" aria-labelledby="demand-config-title">
      <div className="demand-card__intro">
        <h2 id="demand-config-title">Configurar estimación</h2>
        <p>Selecciona los datos y el período que deseas estimar.</p>
      </div>
      <hr />
      <div className="demand-fields">
        <label className="demand-field">
          <span>1. Producto</span>
          <select
            aria-label="Producto"
            value={activeProductContext?.producto_nombre || productoSeleccionado}
            onChange={handleProductoChange}
            disabled={isEstimating}
          >
            {productOptions.map((item) => (
              <option key={item.producto_nombre} value={item.producto_nombre}>
                {item.label}
              </option>
            ))}
          </select>
          {activeProductContext && activeProductContext.dias_operativos_totales !== undefined && (
            <small>
              Unidad base: {activeProductContext.unidad_base} · {activeProductContext.dias_operativos_totales ?? 0} jornadas operativas en el historial disponible.
            </small>
          )}
        </label>
        <div className="demand-field">
          <span>2. Período histórico</span>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
            <label style={{ display: 'flex', minWidth: 0, flexDirection: 'column', gap: 6, fontSize: 11, fontWeight: 500 }}>
              <span>Desde</span>
              <input
                className="demand-date-control"
                type="date"
                aria-label="Fecha desde"
                aria-invalid={rangoHistoricoInvalido}
                min={dateBounds.min || undefined}
                max={dateBounds.max || undefined}
                value={periodoHistorico.fechaDesde}
                disabled={isEstimating}
                onChange={(event) => {
                  setForecastError('');
                  setPeriodoHistorico((current) => ({
                    ...current,
                    fechaDesde: event.target.value,
                  }));
                }}
                style={{ width: '100%', minWidth: 0, minHeight: 43, padding: '9px 10px', border: `1px solid ${rangoHistoricoInvalido ? '#b94420' : '#ebdcd0'}`, borderRadius: 11, outline: 0, color: '#1e1c1a', background: '#fdf7f2', font: "500 12px 'Plus Jakarta Sans', sans-serif" }}
              />
            </label>
            <label style={{ display: 'flex', minWidth: 0, flexDirection: 'column', gap: 6, fontSize: 11, fontWeight: 500 }}>
              <span>Hasta</span>
              <input
                className="demand-date-control"
                type="date"
                aria-label="Fecha hasta"
                aria-invalid={rangoHistoricoInvalido}
                min={dateBounds.min || undefined}
                max={dateBounds.max || undefined}
                value={periodoHistorico.fechaHasta}
                disabled={isEstimating}
                onChange={(event) => {
                  setForecastError('');
                  setPeriodoHistorico((current) => ({
                    ...current,
                    fechaHasta: event.target.value,
                  }));
                }}
                style={{ width: '100%', minWidth: 0, minHeight: 43, padding: '9px 10px', border: `1px solid ${rangoHistoricoInvalido ? '#b94420' : '#ebdcd0'}`, borderRadius: 11, outline: 0, color: '#1e1c1a', background: '#fdf7f2', font: "500 12px 'Plus Jakarta Sans', sans-serif" }}
              />
            </label>
          </div>
          {rangoHistoricoInvalido ? (
            <small role="alert" style={{ color: '#a83224' }}>
              La fecha desde no puede ser posterior a la fecha hasta.
            </small>
          ) : fechasIncompletas ? (
            <small role="alert" style={{ color: '#a83224' }}>
              Selecciona la fecha inicial y la fecha final del período histórico.
            </small>
          ) : (
            <small>
              Define qué registros históricos se tendrán en cuenta (mínimo {contextoHistorico?.minimo_dias_operativos_requeridos ?? 3} jornadas operativas; recomendado {contextoHistorico?.dias_operativos_recomendados ?? 8}+).
            </small>
          )}
        </div>
        <label className="demand-field">
          <span>3. Horizonte de estimación</span>
          <select
            aria-label="Horizonte de estimación"
            value={horizonte}
            onChange={(event) => {
              setHorizonte(event.target.value);
              setForecastError('');
              setReportNotice('');
            }}
            disabled={isEstimating}
          >
            <option value="proxima_semana">Próxima semana</option>
            <option value="proximo_mes">Próximo mes</option>
            <option value="proximo_trimestre">Próximo trimestre</option>
          </select>
          <small>Proyecta exclusivamente sábados, domingos y festivos nacionales de Colombia.</small>
        </label>
      </div>

      {isLoadingContext && (
        <small style={{ color: '#6a6661', fontSize: 11 }}>
          Consultando contexto histórico...
        </small>
      )}

      {contextError && (
        <small role="alert" style={{ color: '#a83224', fontSize: 12 }}>
          {contextError}
        </small>
      )}
      {forecastError && (
        <small role="alert" style={{ color: '#a83224', fontSize: 12, fontWeight: 600 }}>
          {forecastError}
        </small>
      )}

      <div className="demand-config__action">
        <Button
          onClick={handleGenerateForecast}
          disabled={rangoHistoricoInvalido || fechasIncompletas || isEstimating}
        >
          <SparklesIcon />
          {isEstimating ? 'Generando estimación...' : 'Generar estimación'}
        </Button>
      </div>
    </section>

    <section className="demand-card demand-result" aria-labelledby="demand-result-title">
      <div className="demand-result__heading">
        <h2 id="demand-result-title">Resultado de la estimación</h2>
        <div className="demand-result__actions">
          <Button
            variant="quiet"
            className="demand-report-button"
            disabled={!forecast || isEstimating}
            aria-disabled={!forecast || isEstimating ? 'true' : 'false'}
            onClick={handleDownloadReport}
            title={
              forecast
                ? 'Descargar reporte CSV de la estimación actual'
                : 'Genera primero una estimación válida para habilitar la descarga'
            }
          >
            <DownloadIcon />
            Descargar reporte
          </Button>
          <span className="demand-demo-badge">
            <i />
            {badgeLabel}
          </span>
        </div>
      </div>
      {reportNotice && (
        <small role="status" style={{ color: '#2d6a4f', fontSize: 11 }}>
          {reportNotice}
        </small>
      )}
      <hr />

      {isEstimating ? (
        <div className="demand-result__value" role="status" aria-live="polite">
          <p>Procesando serie histórica en el servidor...</p>
          <strong>Calculando...</strong>
          <span>Consultando registros de ventas, cierres diarios y calendario festivo colombiano.</span>
        </div>
      ) : forecast ? (
        <>
          <div className="demand-result__value">
            <p className="demand-result__period">
              {forecast.producto_nombre === 'Hayaca' ? 'Hayacas' : forecast.producto_nombre} · {forecast.horizonte_etiqueta} · Período proyectado: {formatIsoDate(forecast.fecha_inicio_horizonte)} al {formatIsoDate(forecast.fecha_fin_horizonte)}
            </p>
            <div className="demand-result__main">
              <strong className="demand-result__main-value">
                {numberFormatter.format(forecast.demanda_total_estimada)}{' '}
                {formatUnitPlural(forecast.unidad_base, forecast.demanda_total_estimada)}
              </strong>
            </div>
            <div className="demand-result__summary">
              <div className="demand-result__summary-item">
                <span className="demand-result__desc">Producción total sugerida:</span>
                <strong className="demand-result__val">
                  {numberFormatter.format(forecast.produccion_total_sugerida)}{' '}
                  {formatUnitPlural(forecast.unidad_base, forecast.produccion_total_sugerida)}
                </strong>
              </div>
              <span className="demand-result__separator" aria-hidden="true">·</span>
              <div className="demand-result__summary-item">
                <span className="demand-result__desc">Sobrantes disponibles aplicados:</span>
                <strong className="demand-result__val">
                  {numberFormatter.format(forecast.sobrantes_totales_disponibles)}{' '}
                  {formatUnitPlural(forecast.unidad_base, forecast.sobrantes_totales_disponibles)}
                </strong>
              </div>
              <span className="demand-result__separator" aria-hidden="true">·</span>
              <div className="demand-result__summary-item">
                <strong className="demand-result__val">
                  {forecast.total_dias_operativos_proyectados}
                </strong>
                <span className="demand-result__desc">
                  {forecast.total_dias_operativos_proyectados === 1
                    ? 'jornada operativa proyectada.'
                    : 'jornadas operativas proyectadas.'}
                </span>
              </div>
            </div>
          </div>

          <div
            aria-label="Métricas de precisión y origen de datos"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 10,
              padding: '12px 14px',
              borderRadius: 11,
              border: '1px solid #ece6de',
              background: '#faf8f5',
              fontSize: 11,
              color: '#463f38',
            }}
          >
            <div>
              <strong style={{ display: 'block', color: '#1e1c1a' }}>Error absoluto medio (MAE)</strong>
              <span>
                {metricas?.mae_base !== null && metricas?.mae_base !== undefined
                  ? `${formatMetricValue(metricas.mae_base)} ${formatUnitPlural(forecast.unidad_base)}`
                  : 'No disponible'}
              </span>
            </div>
            <div>
              <strong style={{ display: 'block', color: '#1e1c1a' }}>Error porcentual (MAPE)</strong>
              <span>
                {metricas?.mape_porcentaje !== null && metricas?.mape_porcentaje !== undefined
                  ? `${formatMetricValue(metricas.mape_porcentaje)} %`
                  : 'No disponible'}
              </span>
            </div>
            <div>
              <strong style={{ display: 'block', color: '#1e1c1a' }}>Jornadas analizadas</strong>
              <span>
                {resumen?.dias_operativos_con_ventas ?? 0} jornadas del historial analizadas
              </span>
            </div>
            <div>
              <strong style={{ display: 'block', color: '#1e1c1a' }}>Nivel de confianza</strong>
              <span>
                {String(metricas?.nivel_confianza || ' No disponible').toUpperCase()} ({metricas?.muestras_evaluadas ?? 0} muestras de validación)
              </span>
            </div>
          </div>

          {hasSampleWarning && (
            <div
              role="alert"
              style={{
                padding: '11px 14px',
                borderRadius: 11,
                border: '1px solid #e6c6a8',
                background: '#fff8f1',
                color: '#8a3b12',
                fontSize: 11,
                lineHeight: 1.5,
              }}
            >
              <strong>Advertencia sobre la muestra histórica: </strong>
              {metricas?.nota_metodologica}
            </div>
          )}
        </>
      ) : (
        <div className="demand-result__value">
          <p>
            {(activeProductContext?.producto_nombre === 'Hayaca' ? 'Hayacas' : activeProductContext?.producto_nombre) || 'Producto'} · {horizonte === 'proxima_semana' ? 'Próxima semana' : horizonte === 'proximo_mes' ? 'Próximo mes' : 'Próximo trimestre'}
          </p>
          <strong>Sin estimación activa</strong>
          <span>
            Configura el producto, el rango histórico y el horizonte, y pulsa «Generar estimación» para consultar el cálculo real del servidor.
          </span>
        </div>
      )}

      <div className="demand-plan-wrap">
        <table className="demand-plan-table">
          <thead>
            <tr>
              <th scope="col">Día</th>
              <th scope="col">Producto</th>
              <th scope="col">Demanda estimada</th>
              <th scope="col">Sobrantes disponibles</th>
              <th scope="col">Producción sugerida</th>
            </tr>
          </thead>
          <tbody>
            {planificacion.length > 0 ? (
              planificacion.map((item) => (
                <tr key={item.fecha}>
                  <td>
                    <strong style={{ display: 'block', color: '#1e1c1a' }}>
                      {formatIsoDate(item.fecha)}
                    </strong>
                    <small style={{ color: '#6a6660', fontSize: 10 }}>
                      {item.etiqueta_dia}
                    </small>
                  </td>
                  <td>
                    <span>{item.producto_nombre === 'Hayaca' ? 'Hayacas' : item.producto_nombre}</span>
                    <small style={{ display: 'block', color: '#6a6660', fontSize: 10 }}>
                      Rango esperado: {numberFormatter.format(item.rango_minimo_esperado)}–{numberFormatter.format(item.rango_maximo_esperado)} {formatUnitPlural(item.unidad_base)}
                    </small>
                  </td>
                  <td>
                    <strong>{numberFormatter.format(item.demanda_estimada)}</strong>{' '}
                    {formatUnitPlural(item.unidad_base, item.demanda_estimada)}
                  </td>
                  <td>
                    {item.sobrantes_disponibles !== null && item.sobrantes_disponibles !== undefined
                      ? `${numberFormatter.format(item.sobrantes_disponibles)} ${formatUnitPlural(item.unidad_base, item.sobrantes_disponibles)}`
                      : 'No disponible'}
                  </td>
                  <td>
                    <strong>{numberFormatter.format(item.produccion_sugerida)}</strong>{' '}
                    {formatUnitPlural(item.unidad_base, item.produccion_sugerida)}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="5" className="demand-plan-empty">
                  {isEstimating
                    ? 'Generando planificación por fecha operativa...'
                    : 'Selecciona los parámetros y pulsa «Generar estimación» para visualizar la planificación por fecha operativa futura.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="demand-recommendation">
        <BulbIcon />
        <div>
          <h3>Recomendaciones explicables sobre las cantidades propuestas</h3>
          {recomendaciones.length > 0 ? (
            <ul style={{ margin: '6px 0 0', paddingLeft: 18, color: '#463f38', fontSize: 11, lineHeight: 1.55 }}>
              {recomendaciones.map((rec, index) => (
                <li key={`${rec.tipo}-${index}`} style={{ marginBottom: 4 }}>
                  <strong>{rec.titulo}:</strong> {rec.detalle}
                </li>
              ))}
            </ul>
          ) : (
            <p>
              Este espacio mostrará los motivos estadísticos y operativos de las cantidades propuestas (efecto de sábados, domingos y festivos colombianos, descuento de sobrantes disponibles y trazabilidad de datos) al generar una estimación.
            </p>
          )}
        </div>
      </div>
    </section>
  </div>;
}
