import { apiRequest } from '../../auth/services/authService.js';
import { validateProductionRecord } from '../utils/validateProductionRecord.js';

const LEGACY_PRODUCTION_STORAGE_KEY = 'sabores-del-llano-production-v1';
const CHANGE_EVENT = 'sabores-del-llano:production-changed';

const PRODUCT_FROM_API = {
  hayaca: 'hayacas',
  hayacas: 'hayacas',
  lechona: 'lechona',
};

const PRODUCT_TO_API = {
  hayacas: 'Hayaca',
  hayaca: 'Hayaca',
  'hayacas-individual': 'Hayaca',
  lechona: 'Lechona',
  'lechona-personal': 'Lechona',
};

function purgeLegacyLocalProduction() {
  window.localStorage.removeItem(LEGACY_PRODUCTION_STORAGE_KEY);
}

function stripHistoricalTraceTag(text) {
  if (!text) return '';
  return String(text)
    .replace(/\[IMPORTACION_EXCEL\|[^\]]+\]/g, '')
    .trim();
}

function buildIsoDateTime(dateStr) {
  const cleanDate = String(dateStr || '').slice(0, 10);
  return `${cleanDate}T08:00:00`;
}

export function mapApiProductionToUiRecord(item) {
  const prodKey = String(item.producto_nombre ?? '').toLowerCase();
  const mappedProduct = PRODUCT_FROM_API[prodKey] ?? 'lechona';
  const dateStr = String(item.fecha_jornada || item.fecha_produccion || '').slice(0, 10);
  const quantity = Math.round(Number(item.cantidad_producida_base ?? 0));
  const soldQuantity = Math.round(Number(item.cantidad_vendida_fecha ?? 0));
  const calculatedStock = Math.round(
    Number(item.existencia_calculada_base ?? Math.max(0, quantity - soldQuantity))
  );
  const leftovers = Math.round(Number(item.sobrante_real_base ?? 0));
  const difference = Math.round(
    Number(item.diferencia_base ?? leftovers - calculatedStock)
  );

  return {
    id: item.id,
    productoId: item.producto_id,
    product: mappedProduct,
    productName: item.producto_nombre ?? (mappedProduct === 'hayacas' ? 'Hayaca' : 'Lechona'),
    baseUnit: item.unidad_base ?? (mappedProduct === 'hayacas' ? 'Unidad' : 'Plato'),
    date: dateStr,
    quantity,
    soldQuantity,
    calculatedStock,
    leftovers,
    difference,
    observations: stripHistoricalTraceTag(item.observaciones),
    esHistorico: Boolean(item.es_historico),
    esSintetico: Boolean(item.es_sintetico),
    origenRegistro: item.origen_registro ?? 'operativo',
    source: item.es_historico ? 'historical' : 'user',
    createdAt: item.creado_en,
  };
}

function assertProductionRecordIsValid(data) {
  const errors = validateProductionRecord({
    ...data,
    quantity: String(data.quantity),
    leftovers: String(data.leftovers ?? 0),
  });
  if (Object.keys(errors).length) {
    const firstMessage = Object.values(errors)[0];
    throw new Error(
      firstMessage ||
        'Revisa la fecha, el producto, la cantidad producida y los sobrantes antes de guardar.'
    );
  }
}

export async function getProductionRecords({
  productoNombre = '',
  fechaDesde = '',
  fechaHasta = '',
  incluirHistoricos = true,
  incluirSinteticos = true,
  soloOperativos = false,
  limit = 2000,
  offset = 0,
  signal,
} = {}) {
  purgeLegacyLocalProduction();

  const params = new URLSearchParams();
  if (productoNombre) {
    params.set(
      'producto_nombre',
      PRODUCT_TO_API[String(productoNombre).toLowerCase()] ?? productoNombre
    );
  }
  if (fechaDesde) params.set('fecha_desde', String(fechaDesde).slice(0, 10));
  if (fechaHasta) params.set('fecha_hasta', String(fechaHasta).slice(0, 10));
  params.set('incluir_historicos', String(Boolean(incluirHistoricos)));
  params.set('incluir_sinteticos', String(Boolean(incluirSinteticos)));
  if (soloOperativos) params.set('solo_operativos', 'true');
  params.set('limit', String(limit));
  params.set('offset', String(offset));

  const data = await apiRequest(`/producciones?${params.toString()}`, {
    method: 'GET',
    signal,
  });
  return Array.isArray(data) ? data.map(mapApiProductionToUiRecord) : [];
}

export async function getProductionRecordById(id, { signal } = {}) {
  const data = await apiRequest(`/producciones/${encodeURIComponent(id)}`, {
    method: 'GET',
    signal,
  });
  return mapApiProductionToUiRecord(data);
}

export async function createProductionRecord(data) {
  assertProductionRecordIsValid(data);
  const prodName =
    PRODUCT_TO_API[String(data.product || '').toLowerCase()] ??
    String(data.product || '').trim();

  const payload = {
    producto_id: data.productoId ?? undefined,
    producto_nombre: prodName,
    fecha_produccion: buildIsoDateTime(data.date),
    cantidad_producida_base: Number(data.quantity),
    sobrante_real_base: Number(data.leftovers ?? 0),
    observaciones: data.observations ? String(data.observations).trim() : null,
  };

  const created = await apiRequest('/producciones', {
    method: 'POST',
    body: payload,
  });
  window.dispatchEvent(new Event(CHANGE_EVENT));
  return mapApiProductionToUiRecord(created);
}

export async function updateProductionRecord(id, changes) {
  assertProductionRecordIsValid(changes);
  const payload = {
    fecha_produccion: changes.date ? buildIsoDateTime(changes.date) : undefined,
    cantidad_producida_base:
      changes.quantity !== undefined ? Number(changes.quantity) : undefined,
    sobrante_real_base:
      changes.leftovers !== undefined ? Number(changes.leftovers) : undefined,
    observaciones:
      changes.observations !== undefined
        ? changes.observations
          ? String(changes.observations).trim()
          : null
        : undefined,
  };

  const updated = await apiRequest(`/producciones/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: payload,
  });
  window.dispatchEvent(new Event(CHANGE_EVENT));
  return mapApiProductionToUiRecord(updated);
}

export async function deleteProductionRecord(id) {
  await apiRequest(`/producciones/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  window.dispatchEvent(new Event(CHANGE_EVENT));
  return id;
}

export function subscribeProductionRecords(onChange) {
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}
