export const dashboardSales = [
  { day: 'Jue', product: 'lechona', quantity: 0, amount: 0 },
  { day: 'Jue', product: 'hayacas', quantity: 0, amount: 0 },
  { day: 'Vie', product: 'lechona', quantity: 12, amount: 960000 },
  { day: 'Vie', product: 'hayacas', quantity: 12, amount: 168000 },
  { day: 'Sáb', product: 'lechona', quantity: 14, amount: 1120000 },
  { day: 'Sáb', product: 'hayacas', quantity: 13, amount: 182000 },
  { day: 'Dom', product: 'lechona', quantity: 16, amount: 1280000 },
  { day: 'Dom', product: 'hayacas', quantity: 10, amount: 140000 },
];

export function summarizeSales(sales) {
  return sales.reduce((summary, sale) => {
    summary.total += sale.amount;
    summary.quantity[sale.product] = (summary.quantity[sale.product] ?? 0) + sale.quantity;
    summary.byDay[sale.day] ??= { lechona: 0, hayacas: 0 };
    summary.byDay[sale.day][sale.product] += sale.amount;
    return summary;
  }, { total: 0, quantity: {}, byDay: {} });
}
