import { getProduct, getProductCategory } from '../data/orderOptions.js';

export function filterOrders(orders, filters) {
  const term = (filters.search ?? '').trim().toLocaleLowerCase('es');
  return orders.filter((order) => {
    const searchable = [order.customer, order.orderNumber, `#${order.orderNumber}`, getProduct(order.product)?.label, order.address]
      .filter(Boolean).some((value) => String(value).toLocaleLowerCase('es').includes(term));
    return (!term || searchable)
      && (!filters.status || order.status === filters.status)
      && (!filters.product || getProductCategory(order.product) === filters.product)
      && (!filters.date || order.deliveryDate === filters.date);
  }).sort((a, b) => (b.deliveryDate ?? '').localeCompare(a.deliveryDate ?? '') || String(a.orderNumber).localeCompare(String(b.orderNumber), 'es', { numeric: true }));
}
