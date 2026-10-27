import { getSaleProduct } from '../data/salesOptions.js';

const DAY = 24 * 60 * 60 * 1000;

function dateOnly(date) { return date.toISOString().slice(0, 10); }

export function getSalesPeriodBounds(period, today = new Date()) {
  const end = dateOnly(today);
  if (period === '15days') return { from: dateOnly(new Date(today.getTime() - 14 * DAY)), to: end };
  if (period === 'month') return { from: `${end.slice(0, 7)}-01`, to: end };
  const weekday = (today.getDay() + 6) % 7;
  return { from: dateOnly(new Date(today.getTime() - weekday * DAY)), to: dateOnly(new Date(today.getTime() + (6 - weekday) * DAY)) };
}

export function filterSales(sales, { search = '', period = 'week', product = '', today = new Date() } = {}) {
  const bounds = getSalesPeriodBounds(period, today);
  const term = search.trim().toLocaleLowerCase('es');
  return sales.filter((sale) => {
    const searchable = [
      `#${String(sale.receiptNumber).padStart(3, '0')}`,
      getSaleProduct(sale.product)?.label,
      sale.product,
      sale.date,
      new Intl.DateTimeFormat('es-CO', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${sale.date}T12:00:00Z`)),
    ].filter(Boolean).some((value) => String(value).toLocaleLowerCase('es').includes(term));
    return sale.date >= bounds.from && sale.date <= bounds.to
      && (!product || sale.product === product)
      && (!term || searchable);
  }).sort((a, b) => b.date.localeCompare(a.date) || b.time.localeCompare(a.time) || b.receiptNumber - a.receiptNumber);
}

export function summarizeSales(sales) {
  const summary = sales.reduce((result, sale) => {
    result.total += sale.total;
    result.count += 1;
    result.units[sale.product] = (result.units[sale.product] ?? 0) + sale.quantity;
    const day = sale.weekday ? sale.weekday[0].toLocaleUpperCase('es') + sale.weekday.slice(1) : '';
    if (day) {
      result.byDay[day] ??= { lechona: 0, hayacas: 0 };
      result.byDay[day][sale.product] += sale.total;
    }
    return result;
  }, { total: 0, count: 0, units: { lechona: 0, hayacas: 0 }, byDay: {} });
  return { ...summary, quantity: summary.units };
}

export function formatCOP(value) {
  return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(value);
}

export function formatSaleDate(value) {
  return new Intl.DateTimeFormat('es-CO', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T12:00:00Z`));
}

export function formatSaleTime(value) {
  if (!value) return '';
  const [hour, minute] = value.split(':').map(Number);
  return new Intl.DateTimeFormat('es-CO', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'UTC' }).format(new Date(Date.UTC(2026, 0, 1, hour, minute)));
}

