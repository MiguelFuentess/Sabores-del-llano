import { getSaleProduct } from '../data/salesOptions.js';
import { calculateSaleTotal } from './saleCalculations.js';

function isRealDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value ?? '')) return false;
  const date = new Date(`${value}T12:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function validateSale(sale) {
  const errors = {};
  if (!isRealDate(sale.date)) errors.date = 'Ingresa una fecha válida.';
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(sale.time ?? '')) errors.time = 'Ingresa una hora válida.';
  if (!getSaleProduct(sale.product)) errors.product = 'Selecciona hayacas o lechona.';
  if (!/^\d+$/.test(String(sale.quantity ?? '').trim()) || Number(sale.quantity) < 1 || !Number.isSafeInteger(Number(sale.quantity))) {
    errors.quantity = 'Ingresa una cantidad entera mayor que cero.';
  }
  if (!/^\d+$/.test(String(sale.unitPrice ?? '').trim()) || Number(sale.unitPrice) < 1 || !Number.isSafeInteger(Number(sale.unitPrice))) {
    errors.unitPrice = 'Ingresa un precio válido en pesos colombianos.';
  }
  if (!errors.quantity && !errors.unitPrice && !Number.isSafeInteger(calculateSaleTotal(sale.quantity, sale.unitPrice))) {
    errors.unitPrice = 'El total de la venta supera el valor permitido.';
  }
  return errors;
}

