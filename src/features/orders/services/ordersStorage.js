import { apiRequest } from '../../auth/services/authService.js';

const LEGACY_ORDERS_STORAGE_KEY = 'sabores-del-llano-orders-v1';

const STATUS_FROM_API = {
  pendiente: 'Pendiente',
  confirmado: 'Confirmado',
  en_preparacion: 'En preparación',
  entregado: 'Entregado',
  cancelado: 'Cancelado',
};

const STATUS_TO_API = {
  Pendiente: 'pendiente',
  Confirmado: 'confirmado',
  'En preparación': 'en_preparacion',
  Entregado: 'entregado',
  Cancelado: 'cancelado',
};

const PRODUCT_FROM_API = {
  hayaca: 'hayacas-individual',
  lechona: 'lechona-personal',
};

const PRODUCT_TO_API = {
  'hayacas-individual': 'Hayaca',
  hayacas: 'Hayaca',
  hayaca: 'Hayaca',
  'lechona-personal': 'Lechona',
  lechona: 'Lechona',
};

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

export function mapApiOrderToUiOrder(pedido) {
  const primaryDetail = Array.isArray(pedido.detalles) && pedido.detalles.length > 0
    ? pedido.detalles[0]
    : null;
  const prodKey = String(primaryDetail?.producto_nombre ?? '').toLowerCase();
  const mappedProduct = PRODUCT_FROM_API[prodKey] ?? 'hayacas-individual';
  const mappedQuantity = primaryDetail
    ? Math.round(Number(primaryDetail.cantidad))
    : Math.round(Number(pedido.cantidad_total_base || 0));

  return {
    id: pedido.id,
    orderNumber: String(pedido.id).padStart(3, '0'),
    customer: pedido.cliente_nombre || pedido.nombre_contacto || 'Cliente',
    customerId: pedido.cliente_id,
    product: mappedProduct,
    quantity: mappedQuantity,
    registeredDate: String(pedido.fecha_pedido || '').slice(0, 10),
    deliveryDate: String(pedido.fecha_entrega_prevista || '').slice(0, 10),
    deliveryTime: extractTimePart(pedido.fecha_entrega_prevista),
    deliveryMode: pedido.modalidad_entrega || 'retiro',
    address: pedido.direccion_entrega ?? '',
    phone: pedido.telefono_contacto ?? '',
    observations: stripHistoricalTraceTag(pedido.observaciones),
    status: STATUS_FROM_API[pedido.estado] ?? 'Pendiente',
    esHistorico: Boolean(pedido.es_historico),
    esSintetico: Boolean(pedido.es_sintetico),
    origenRegistro: pedido.origen_registro ?? 'operativo',
    total: Number(pedido.total ?? 0),
    detalles: pedido.detalles ?? [],
  };
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
      observaciones: item.observaciones ? String(item.observaciones).trim() : null,
    }));
  }

  const prodName =
    PRODUCT_TO_API[String(data.product || '').toLowerCase()] ??
    String(data.product || '').trim();

  return [
    {
      producto_nombre: prodName,
      cantidad: Number(data.quantity),
    },
  ];
}

export async function getOrders({
  q = '',
  estado = '',
  incluirHistoricos = true,
  incluirSinteticos = true,
  soloOperativos = false,
  limit = 2000,
  offset = 0,
  signal,
} = {}) {
  window.localStorage.removeItem(LEGACY_ORDERS_STORAGE_KEY);

  const params = new URLSearchParams();
  if (q && String(q).trim()) params.set('q', String(q).trim());
  if (estado) {
    params.set('estado', STATUS_TO_API[estado] ?? estado);
  }
  params.set('incluir_historicos', String(Boolean(incluirHistoricos)));
  params.set('incluir_sinteticos', String(Boolean(incluirSinteticos)));
  if (soloOperativos) params.set('solo_operativos', 'true');
  params.set('limit', String(limit));
  params.set('offset', String(offset));

  const data = await apiRequest(`/pedidos?${params.toString()}`, {
    method: 'GET',
    signal,
  });
  return Array.isArray(data) ? data.map(mapApiOrderToUiOrder) : [];
}

export async function getOrderById(id, { signal } = {}) {
  const data = await apiRequest(`/pedidos/${encodeURIComponent(id)}`, {
    method: 'GET',
    signal,
  });
  return mapApiOrderToUiOrder(data);
}

export async function getOrderDetails(id, { signal } = {}) {
  return apiRequest(`/pedidos/${encodeURIComponent(id)}/detalles`, {
    method: 'GET',
    signal,
  });
}

export async function createOrder(data) {
  const payload = {
    cliente_nombre: String(data.customer ?? '').trim(),
    cliente_id: data.customerId ?? undefined,
    fecha_pedido: data.registeredDate
      ? buildIsoDateTime(data.registeredDate, '00:00')
      : undefined,
    fecha_entrega_prevista: buildIsoDateTime(data.deliveryDate, data.deliveryTime),
    estado: STATUS_TO_API[data.status] ?? data.status ?? 'pendiente',
    modalidad_entrega: data.deliveryMode === 'domicilio' ? 'domicilio' : 'retiro',
    telefono_contacto: data.phone ? String(data.phone).trim() : null,
    direccion_entrega:
      data.deliveryMode === 'domicilio' && data.address
        ? String(data.address).trim()
        : null,
    observaciones: data.observations ? String(data.observations).trim() : null,
    detalles: buildDetallesPayload(data),
  };

  const created = await apiRequest('/pedidos', {
    method: 'POST',
    body: payload,
  });
  window.dispatchEvent(new Event('sabores-del-llano:orders-changed'));
  return mapApiOrderToUiOrder(created);
}

export async function updateOrder(id, changes) {
  const payload = {
    fecha_entrega_prevista: changes.deliveryDate
      ? buildIsoDateTime(changes.deliveryDate, changes.deliveryTime)
      : undefined,
    estado: changes.status
      ? STATUS_TO_API[changes.status] ?? changes.status
      : undefined,
    modalidad_entrega:
      changes.deliveryMode === 'domicilio'
        ? 'domicilio'
        : changes.deliveryMode === 'retiro'
          ? 'retiro'
          : undefined,
    telefono_contacto:
      changes.phone !== undefined
        ? changes.phone
          ? String(changes.phone).trim()
          : null
        : undefined,
    direccion_entrega:
      changes.deliveryMode === 'domicilio'
        ? String(changes.address ?? '').trim()
        : changes.deliveryMode === 'retiro'
          ? null
          : undefined,
    observaciones:
      changes.observations !== undefined
        ? changes.observations
          ? String(changes.observations).trim()
          : null
        : undefined,
    detalles:
      changes.product || changes.detalles ? buildDetallesPayload(changes) : undefined,
  };

  const updated = await apiRequest(`/pedidos/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: payload,
  });
  window.dispatchEvent(new Event('sabores-del-llano:orders-changed'));
  return mapApiOrderToUiOrder(updated);
}

export async function deleteOrder(id) {
  await apiRequest(`/pedidos/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  window.dispatchEvent(new Event('sabores-del-llano:orders-changed'));
  return id;
}
