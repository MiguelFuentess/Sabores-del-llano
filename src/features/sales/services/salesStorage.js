import { apiRequest } from '../../auth/services/authService.js';
import { validateSale } from '../utils/validateSale.js';

const LEGACY_SALES_STORAGE_KEY = 'sabores-del-llano-sales-v1';
const LEGACY_NEXT_RECEIPT_KEY = 'sabores-del-llano-sales-next-receipt-v1';
const CHANGE_EVENT = 'sabores-del-llano:sales-changed';

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

function purgeLegacyLocalSales() {
  window.localStorage.removeItem(LEGACY_SALES_STORAGE_KEY);
  window.localStorage.removeItem(LEGACY_NEXT_RECEIPT_KEY);
}

function stripHistoricalTraceTag(text) {
  if (!text) return '';
  return String(text)
    .replace(/\[IMPORTACION_EXCEL\|[^\]]+\]/g, '')
    .trim();
}

function extractTimePart(isoDateTime) {
  if (!isoDateTime) return '';
  const match = String(isoDateTime).match(/T(\d{2}:\d{2})/);
  if (!match) return '';
  return match[1] === '00:00' ? '' : match[1];
}

function buildIsoDateTime(dateStr, timeStr = '') {
  const cleanDate = String(dateStr || '').slice(0, 10);
  const cleanTime = timeStr && /^\d{2}:\d{2}$/.test(timeStr) ? timeStr : '00:00';
  return `${cleanDate}T${cleanTime}:00`;
}

function computeWeekdayShort(dateStr) {
  if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return '';
  return new Intl.DateTimeFormat('es-CO', {
    weekday: 'short',
    timeZone: 'UTC',
  })
    .format(new Date(`${dateStr}T12:00:00Z`))
    .replace('.', '')
    .toLocaleLowerCase('es');
}

export function mapApiSaleToUiSale(venta) {
  const primaryDetail =
    Array.isArray(venta.detalles) && venta.detalles.length > 0
      ? venta.detalles[0]
      : null;
  const prodKey = String(primaryDetail?.producto_nombre ?? '').toLowerCase();
  const mappedProduct = PRODUCT_FROM_API[prodKey] ?? 'lechona';
  const mappedQuantity = primaryDetail
    ? Math.round(Number(primaryDetail.cantidad))
    : Math.round(Number(venta.cantidad_total_base || 0));
  const mappedUnitPrice = primaryDetail
    ? Math.round(Number(primaryDetail.precio_unitario))
    : 0;
  const dateStr = String(venta.fecha_venta || '').slice(0, 10);

  return {
    id: venta.id,
    receiptNumber: venta.id,
    pedidoId: venta.pedido_id ?? null,
    date: dateStr,
    time: extractTimePart(venta.fecha_venta),
    weekday: computeWeekdayShort(dateStr),
    product: mappedProduct,
    quantity: mappedQuantity,
    unitPrice: mappedUnitPrice,
    total: Math.round(Number(venta.total ?? mappedQuantity * mappedUnitPrice)),
    estado: venta.estado ?? 'concretada',
    observations: stripHistoricalTraceTag(venta.observaciones),
    esHistorico: Boolean(venta.es_historico),
    esSintetico: Boolean(venta.es_sintetico),
    origenRegistro: venta.origen_registro ?? 'operativo',
    detalles: venta.detalles ?? [],
    createdAt: venta.creado_en,
  };
}

function assertSaleIsValid(sale) {
  const errors = validateSale({
    ...sale,
    time: sale.time || '12:00',
  });
  if (Object.keys(errors).length) {
    throw new Error(
      'Revisa la fecha, el producto, la cantidad y el precio antes de guardar.'
    );
  }
}

function buildDetallesPayload(data) {
  if (Array.isArray(data.detalles) && data.detalles.length > 0) {
    return data.detalles.map((item) => ({
      presentacion_id: item.presentacion_id ?? undefined,
      producto_id: item.producto_id ?? undefined,
      producto_nombre:
        item.producto_nombre ??
        PRODUCT_TO_API[String(item.product || '').toLowerCase()] ??
        item.product,
      cantidad: Number(item.cantidad ?? item.quantity),
      precio_unitario:
        item.precio_unitario !== undefined || item.unitPrice !== undefined
          ? Number(item.precio_unitario ?? item.unitPrice)
          : undefined,
    }));
  }

  const prodName =
    PRODUCT_TO_API[String(data.product || '').toLowerCase()] ??
    String(data.product || '').trim();

  return [
    {
      producto_nombre: prodName,
      cantidad: Number(data.quantity),
      precio_unitario:
        data.unitPrice !== undefined && data.unitPrice !== ''
          ? Number(data.unitPrice)
          : undefined,
    },
  ];
}

export async function getSales({
  q = '',
  estado = 'concretada',
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
  purgeLegacyLocalSales();

  const params = new URLSearchParams();
  if (q && String(q).trim()) params.set('q', String(q).trim());
  if (estado) params.set('estado', String(estado));
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

  const data = await apiRequest(`/ventas?${params.toString()}`, {
    method: 'GET',
    signal,
  });
  return Array.isArray(data) ? data.map(mapApiSaleToUiSale) : [];
}

export async function getSaleById(id, { signal } = {}) {
  const data = await apiRequest(`/ventas/${encodeURIComponent(id)}`, {
    method: 'GET',
    signal,
  });
  return mapApiSaleToUiSale(data);
}

export async function getSaleDetails(id, { signal } = {}) {
  return apiRequest(`/ventas/${encodeURIComponent(id)}/detalles`, {
    method: 'GET',
    signal,
  });
}

export async function createSale(data) {
  assertSaleIsValid(data);
  const payload = {
    pedido_id: data.pedidoId ?? undefined,
    fecha_venta: buildIsoDateTime(data.date, data.time),
    estado: data.estado ?? 'concretada',
    observaciones: data.observations ? String(data.observations).trim() : null,
    detalles: buildDetallesPayload(data),
  };

  const created = await apiRequest('/ventas', {
    method: 'POST',
    body: payload,
  });
  window.dispatchEvent(new Event(CHANGE_EVENT));
  if (payload.pedido_id) {
    window.dispatchEvent(new Event('sabores-del-llano:orders-changed'));
  }
  return mapApiSaleToUiSale(created);
}

export async function updateSale(id, changes) {
  assertSaleIsValid(changes);
  const payload = {
    fecha_venta: changes.date
      ? buildIsoDateTime(changes.date, changes.time)
      : undefined,
    estado: changes.estado ?? undefined,
    observaciones:
      changes.observations !== undefined
        ? changes.observations
          ? String(changes.observations).trim()
          : null
        : undefined,
    detalles:
      changes.product || changes.detalles
        ? buildDetallesPayload(changes)
        : undefined,
  };

  const updated = await apiRequest(`/ventas/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: payload,
  });
  window.dispatchEvent(new Event(CHANGE_EVENT));
  return mapApiSaleToUiSale(updated);
}

export async function deleteSale(id) {
  await apiRequest(`/ventas/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  window.dispatchEvent(new Event(CHANGE_EVENT));
  return id;
}

export function subscribeSales(onChange) {
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}
