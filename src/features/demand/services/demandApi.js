import { apiRequest } from '../../auth/services/authService.js';

const PRODUCT_TO_API = {
  hayaca: 'Hayaca',
  hayacas: 'Hayaca',
  'hayacas-individual': 'Hayaca',
  lechona: 'Lechona',
  'lechona-personal': 'Lechona',
};

const HORIZON_TO_API = {
  proxima_semana: 'proxima_semana',
  'próxima semana': 'proxima_semana',
  'proxima semana': 'proxima_semana',
  proximo_mes: 'proximo_mes',
  'próximo mes': 'proximo_mes',
  'proximo mes': 'proximo_mes',
  proximo_trimestre: 'proximo_trimestre',
  'próximo trimestre': 'proximo_trimestre',
  'proximo trimestre': 'proximo_trimestre',
};

export function normalizeDemandProductName(value) {
  const raw = String(value || '').trim();
  return PRODUCT_TO_API[raw.toLowerCase()] ?? raw;
}

export function normalizeDemandHorizon(value) {
  const raw = String(value || '').trim().toLowerCase();
  return HORIZON_TO_API[raw] ?? raw;
}

function classifyDemandApiError(error) {
  const status = Number(error?.status || 0);
  const message = String(
    error?.message || 'No fue posible procesar la solicitud de predicción de demanda.'
  );

  const enriched = new Error(message);
  enriched.status = status;

  if (status === 401 || status === 403) {
    enriched.kind = 'auth';
  } else if (status === 404) {
    enriched.kind = 'not_found';
  } else if (status === 422 || status === 400) {
    if (
      message.toLowerCase().includes('jornadas operativas') ||
      message.toLowerCase().includes('insuficiente')
    ) {
      enriched.kind = 'insufficient_data';
    } else {
      enriched.kind = 'validation';
    }
  } else {
    enriched.kind = 'network';
  }

  return enriched;
}

export async function getDemandHistoricalContext({ signal } = {}) {
  try {
    return await apiRequest('/prediccion/contexto-historico', {
      method: 'GET',
      signal,
    });
  } catch (error) {
    throw classifyDemandApiError(error);
  }
}

export async function requestDemandForecast(
  {
    productoId,
    productoNombre,
    fechaDesde,
    fechaHasta,
    horizonte = 'proxima_semana',
    incluirSinteticos = true,
    fechaReferencia,
    sobranteDisponibleInicial,
  },
  { signal } = {}
) {
  const payload = {
    fecha_desde: String(fechaDesde || '').slice(0, 10),
    fecha_hasta: String(fechaHasta || '').slice(0, 10),
    horizonte: normalizeDemandHorizon(horizonte),
    incluir_sinteticos: Boolean(incluirSinteticos),
  };

  if (productoId !== undefined && productoId !== null && productoId !== '') {
    payload.producto_id = Number(productoId);
  }
  if (productoNombre) {
    payload.producto_nombre = normalizeDemandProductName(productoNombre);
  }
  if (fechaReferencia) {
    payload.fecha_referencia = String(fechaReferencia).slice(0, 10);
  }
  if (
    sobranteDisponibleInicial !== undefined &&
    sobranteDisponibleInicial !== null &&
    sobranteDisponibleInicial !== ''
  ) {
    payload.sobrante_disponible_inicial = Number(sobranteDisponibleInicial);
  }

  try {
    return await apiRequest('/prediccion/estimar', {
      method: 'POST',
      body: payload,
      signal,
    });
  } catch (error) {
    throw classifyDemandApiError(error);
  }
}

function escapeCsvCell(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  if (/[",\n\r;]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function buildDemandReportCsv(forecast) {
  if (!forecast || typeof forecast !== 'object') {
    throw new Error('No hay una estimación válida disponible para descargar.');
  }

  const resumen = forecast.resumen_historico ?? {};
  const metricas = forecast.metricas_precision ?? {};
  const planificacion = Array.isArray(forecast.planificacion_diaria)
    ? forecast.planificacion_diaria
    : [];
  const recomendaciones = Array.isArray(forecast.recomendaciones)
    ? forecast.recomendaciones
    : [];

  const maeDisplay =
    metricas.mae_base !== null && metricas.mae_base !== undefined
      ? `${metricas.mae_base} ${forecast.unidad_base || ''}`.trim()
      : 'No disponible';
  const mapeDisplay =
    metricas.mape_porcentaje !== null && metricas.mape_porcentaje !== undefined
      ? `${metricas.mape_porcentaje}%`
      : 'No disponible';

  const lines = [
    ['REPORTE DE PREDICCIÓN DE DEMANDA - SABORES DEL LLANO'],
    ['Fecha de generación', forecast.generado_en || ''],
    ['Producto', `${forecast.producto_nombre || ''} (ID: ${forecast.producto_id ?? ''})`],
    ['Unidad base', forecast.unidad_base || ''],
    [
      'Período histórico seleccionado',
      `${resumen.fecha_desde || ''} a ${resumen.fecha_hasta || ''}`,
    ],
    [
      'Rango observado con ventas',
      `${resumen.fecha_minima_observada || ''} a ${resumen.fecha_maxima_observada || ''}`,
    ],
    [
      'Horizonte de estimación',
      `${forecast.horizonte_etiqueta || forecast.horizonte || ''} (${forecast.fecha_inicio_horizonte || ''} a ${forecast.fecha_fin_horizonte || ''})`,
    ],
    [
      'Inclusión de datos sintéticos',
      forecast.incluir_sinteticos ? 'Sí (incluidos)' : 'No (solo reales y operativos)',
    ],
    ['Días operativos proyectados', forecast.total_dias_operativos_proyectados ?? 0],
    ['Demanda total estimada', forecast.demanda_total_estimada ?? 0],
    ['Sobrantes disponibles aplicados', forecast.sobrantes_totales_disponibles ?? 0],
    ['Producción total sugerida', forecast.produccion_total_sugerida ?? 0],
    [],
    ['ORIGEN Y TRAZABILIDAD DE DATOS HISTÓRICOS'],
    ['Jornadas operativas con ventas', resumen.dias_operativos_con_ventas ?? 0],
    ['Jornadas operativas sin ventas', resumen.dias_operativos_sin_ventas ?? 0],
    ['Registros históricos reales', resumen.registros_reales ?? 0],
    ['Registros operativos (app)', resumen.registros_operativos ?? 0],
    ['Registros históricos sintéticos', resumen.registros_sinteticos ?? 0],
    ['Proporción de datos reales/operativos (%)', resumen.proporcion_datos_reales ?? 0],
    [
      'Fechas no operativas excluidas',
      Array.isArray(resumen.fechas_no_operativas_excluidas) &&
      resumen.fechas_no_operativas_excluidas.length > 0
        ? resumen.fechas_no_operativas_excluidas.join(', ')
        : 'Ninguna',
    ],
    [
      'Promedio histórico de sobrantes',
      resumen.promedio_sobrante_historico_base ?? 0,
    ],
    [
      'Último sobrante registrado en cierre',
      `${resumen.ultimo_sobrante_registrado_base ?? 0} (${resumen.fecha_ultimo_cierre || 'Sin cierre'})`,
    ],
    [],
    ['MÉTRICAS DE PRECISIÓN Y CONFIABILIDAD'],
    ['Método estadístico', metricas.metodo || ''],
    ['Origen de evaluación', metricas.origen_evaluacion || ''],
    ['Muestras evaluadas (backtesting)', metricas.muestras_evaluadas ?? 0],
    ['Error absoluto medio (MAE)', maeDisplay],
    ['Error porcentual absoluto medio (MAPE)', mapeDisplay],
    ['Nivel de confianza', metricas.nivel_confianza || ''],
    ['Nota metodológica', metricas.nota_metodologica || ''],
    [],
    ['PLANIFICACIÓN POR FECHA OPERATIVA FUTURA'],
    [
      'Fecha',
      'Día / Festivo',
      'Tipo de jornada',
      'Producto',
      'Unidad',
      'Demanda estimada',
      'Sobrantes disponibles',
      'Producción sugerida',
      'Rango mínimo esperado',
      'Rango máximo esperado',
      'Explicación del día',
    ],
    ...planificacion.map((item) => [
      item.fecha,
      item.etiqueta_dia,
      item.tipo_dia,
      item.producto_nombre,
      item.unidad_base,
      item.demanda_estimada,
      item.sobrantes_disponibles,
      item.produccion_sugerida,
      item.rango_minimo_esperado,
      item.rango_maximo_esperado,
      item.explicacion_dia,
    ]),
    [],
    ['RECOMENDACIONES EXPLICABLES Y ADVERTENCIAS'],
    ['Categoría', 'Título', 'Detalle'],
    ...recomendaciones.map((rec) => [rec.tipo, rec.titulo, rec.detalle]),
  ];

  return `\uFEFF${lines
    .map((row) => row.map(escapeCsvCell).join(','))
    .join('\r\n')}`;
}

export function downloadDemandReportCsv(forecast) {
  const csvContent = buildDemandReportCsv(forecast);
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const prodSlug = String(forecast.producto_nombre || 'producto')
    .toLowerCase()
    .replace(/\s+/g, '_');
  const horSlug = String(forecast.horizonte || 'horizonte').toLowerCase();
  const fileName = `prediccion_demanda_${prodSlug}_${horSlug}_${forecast.fecha_inicio_horizonte || 'reporte'}.csv`;

  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', fileName);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
  return fileName;
}
