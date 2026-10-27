import { INITIAL_DEMO_ORDERS } from '../data/orderOptions.js';

const STORAGE_KEY = 'sabores-del-llano-orders-v1';

function writeOrders(orders) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(orders));
  return orders;
}

export function getOrders() {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === null) return writeOrders(INITIAL_DEMO_ORDERS);
  const orders = JSON.parse(stored);
  if (!Array.isArray(orders)) throw new Error('Los pedidos guardados no tienen un formato válido.');
  return orders;
}

export function createOrder(data) {
  const orders = getOrders();
  const maxOrderNumber = orders.reduce((max, order) => Math.max(max, Number(order.orderNumber) || 0), 0);
  const order = {
    ...data,
    id: globalThis.crypto?.randomUUID?.() ?? `order-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    orderNumber: String(maxOrderNumber + 1).padStart(3, '0'),
  };
  return { order, orders: writeOrders([...orders, order]) };
}

export function updateOrder(id, changes) {
  const orders = getOrders();
  const current = orders.find((order) => order.id === id);
  if (!current) throw new Error('No se encontró el pedido que intentas modificar.');
  const order = { ...current, ...changes, id: current.id, orderNumber: current.orderNumber, customer: current.customer, registeredDate: current.registeredDate };
  return { order, orders: writeOrders(orders.map((item) => item.id === id ? order : item)) };
}

export function deleteOrder(id) {
  const orders = getOrders();
  const nextOrders = orders.filter((order) => order.id !== id);
  if (nextOrders.length === orders.length) throw new Error('No se encontró el pedido que intentas eliminar.');
  return writeOrders(nextOrders);
}
