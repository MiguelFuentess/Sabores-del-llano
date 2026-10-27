import { ORDER_PRODUCTS, ORDER_STATUSES } from '../data/orderOptions.js';

function isRealDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

export function validateOrderData(data, { isNew = false, addingClient = false } = {}) {
  const errors = {};
  if (isNew && !(data.customer || '').trim()) errors.customer = addingClient ? 'Escribe el nombre del nuevo cliente.' : 'Selecciona un cliente.';
  if (!ORDER_PRODUCTS.some((product) => product.value === data.product)) errors.product = 'Selecciona un producto.';
  if (!Number.isInteger(Number(data.quantity)) || Number(data.quantity) <= 0) errors.quantity = 'Ingresa una cantidad entera mayor que cero.';
  if (!isRealDate(data.registeredDate)) errors.registeredDate = 'La fecha de registro no es válida.';
  if (!isRealDate(data.deliveryDate)) errors.deliveryDate = 'Selecciona una fecha de entrega válida.';
  else if (isRealDate(data.registeredDate) && data.deliveryDate < data.registeredDate) errors.deliveryDate = 'La fecha de entrega no puede ser anterior a la fecha de registro.';
  if (data.deliveryTime && !/^([01]\d|2[0-3]):[0-5]\d$/.test(data.deliveryTime)) errors.deliveryTime = 'Ingresa una hora válida.';
  if (!['retiro', 'domicilio'].includes(data.deliveryMode)) errors.deliveryMode = 'Selecciona una modalidad de entrega.';
  if (data.deliveryMode === 'domicilio' && !(data.address || '').trim()) errors.address = 'Ingresa la dirección para el domicilio.';
  if (!ORDER_STATUSES.includes(data.status)) errors.status = 'Selecciona un estado válido.';
  return errors;
}
