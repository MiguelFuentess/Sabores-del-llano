import { apiRequest } from '../../auth/services/authService.js';

export async function getCustomers({
  q = '',
  soloActivos = false,
  incluirSinteticos = true,
  soloOperativos = false,
  limit = 500,
  offset = 0,
  signal,
} = {}) {
  const params = new URLSearchParams();
  if (q && String(q).trim()) params.set('q', String(q).trim());
  if (soloActivos) params.set('solo_activos', 'true');
  params.set('incluir_sinteticos', String(Boolean(incluirSinteticos)));
  if (soloOperativos) params.set('solo_operativos', 'true');
  params.set('limit', String(limit));
  params.set('offset', String(offset));

  return apiRequest(`/clientes?${params.toString()}`, { method: 'GET', signal });
}

export async function getCustomerById(clienteId, { signal } = {}) {
  return apiRequest(`/clientes/${encodeURIComponent(clienteId)}`, {
    method: 'GET',
    signal,
  });
}

export async function createCustomer(data) {
  return apiRequest('/clientes', {
    method: 'POST',
    body: {
      nombre: String(data.nombre ?? '').trim(),
      telefono: data.telefono ? String(data.telefono).trim() : null,
      correo: data.correo ? String(data.correo).trim() : null,
      notas: data.notas ? String(data.notas).trim() : null,
      activo: data.activo ?? true,
      permitir_homonimo: Boolean(data.permitirHomonimo),
    },
  });
}

export async function updateCustomer(clienteId, changes) {
  const body = {};
  if (changes.nombre !== undefined) body.nombre = String(changes.nombre).trim();
  if (changes.telefono !== undefined) {
    body.telefono = changes.telefono ? String(changes.telefono).trim() : null;
  }
  if (changes.correo !== undefined) {
    body.correo = changes.correo ? String(changes.correo).trim() : null;
  }
  if (changes.notas !== undefined) {
    body.notas = changes.notas ? String(changes.notas).trim() : null;
  }
  if (changes.activo !== undefined) body.activo = Boolean(changes.activo);

  return apiRequest(`/clientes/${encodeURIComponent(clienteId)}`, {
    method: 'PATCH',
    body,
  });
}
