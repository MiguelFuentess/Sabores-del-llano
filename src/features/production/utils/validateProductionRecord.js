import { PRODUCTION_PRODUCTS } from '../data/productionOptions.js';

function isRealDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function validateProductionRecord(form) {
  const errors = {};
  if (!isRealDate(form.date)) errors.date = 'Ingresa una fecha válida.';
  if (!PRODUCTION_PRODUCTS.some(({ value }) => value === form.product)) errors.product = 'Selecciona hayacas o lechona.';
  if (!/^\d+$/.test(String(form.quantity).trim()) || Number(form.quantity) < 1) errors.quantity = 'Ingresa una cantidad entera mayor que cero.';
  if (form.leftovers !== '' && (!/^\d+$/.test(String(form.leftovers).trim()) || Number(form.leftovers) < 0)) {
    errors.leftovers = 'Ingresa cero o una cantidad entera positiva.';
  }
  return errors;
}

