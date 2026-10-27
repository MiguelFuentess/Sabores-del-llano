import { validateSale } from '../utils/validateSale.js';
import { calculateSaleTotal } from '../utils/saleCalculations.js';

const STORAGE_KEY = 'sabores-del-llano-sales-v1';
const NEXT_RECEIPT_KEY = 'sabores-del-llano-sales-next-receipt-v1';
const CHANGE_EVENT = 'sabores-del-llano:sales-changed';

function persist(sales) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sales));
  window.dispatchEvent(new Event(CHANGE_EVENT));
  return sales;
}

export function getSales() {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === null) return persist([]);
  const sales = JSON.parse(stored);
  if (!Array.isArray(sales)) throw new Error('Las ventas guardadas no tienen un formato válido.');
  return sales;
}

function assertSaleIsValid(sale) {
  const errors = validateSale(sale);
  if (Object.keys(errors).length) throw new Error('Revisa la fecha, el producto, la cantidad y el precio antes de guardar.');
}

function makeSale(data, identity = {}) {
  return {
    ...data,
    ...identity,
    quantity: Number(data.quantity),
    unitPrice: Number(data.unitPrice),
    total: calculateSaleTotal(data.quantity, data.unitPrice),
    weekday: new Intl.DateTimeFormat('es-CO', { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${data.date}T12:00:00Z`)).replace('.', '').toLocaleLowerCase('es'),
  };
}

export function createSale(data) {
  assertSaleIsValid(data);
  const sales = getSales();
  const savedNextNumber = Number(window.localStorage.getItem(NEXT_RECEIPT_KEY));
  const largestNumber = sales.reduce((max, sale) => Math.max(max, Number(sale.receiptNumber) || 0), 0);
  const receiptNumber = Number.isSafeInteger(savedNextNumber) && savedNextNumber > largestNumber ? savedNextNumber : largestNumber + 1;
  window.localStorage.setItem(NEXT_RECEIPT_KEY, String(receiptNumber + 1));
  const sale = makeSale(data, {
    id: globalThis.crypto?.randomUUID?.() ?? `sale-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    receiptNumber,
    createdAt: new Date().toISOString(),
    source: 'user',
  });
  return { sale, sales: persist([...sales, sale]) };
}

export function updateSale(id, changes) {
  assertSaleIsValid(changes);
  const sales = getSales();
  const current = sales.find((sale) => sale.id === id);
  if (!current) throw new Error('No se encontró la venta que intentas modificar.');
  const sale = makeSale(changes, { id: current.id, receiptNumber: current.receiptNumber, createdAt: current.createdAt, source: current.source });
  return { sale, sales: persist(sales.map((item) => item.id === id ? sale : item)) };
}

export function deleteSale(id) {
  const sales = getSales();
  const nextSales = sales.filter((sale) => sale.id !== id);
  if (nextSales.length === sales.length) throw new Error('No se encontró la venta que intentas eliminar.');
  return persist(nextSales);
}

export function subscribeSales(onChange) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

