import { getProduct, getProductCategory } from '../data/orderOptions.js';

export function formatDeliveryDate(value) {
  if (!value) return '—';
  const [year, month, day] = value.split('-').map(Number);
  return new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function orderDescription(order) {
  const category = getProductCategory(order.product);
  if (category === 'hayacas') return `${order.quantity} ${order.quantity === 1 ? 'hayaca' : 'hayacas'}`;
  const product = getProduct(order.product)?.label ?? 'Lechona';
  if (order.product === 'lechona-personal') return `${order.quantity} ${order.quantity === 1 ? 'porción lechona' : 'porciones lechona'}`;
  return `${order.quantity} × ${product}`;
}
