const DAY = 24 * 60 * 60 * 1000;

function dateOnly(date) { return date.toISOString().slice(0, 10); }

export function getProductionPeriodBounds(period, today = new Date()) {
  const todayKey = dateOnly(today);
  if (period === 'month') return { from: `${todayKey.slice(0, 7)}-01`, to: todayKey };
  if (period === '15days') return { from: dateOnly(new Date(today.getTime() - 14 * DAY)), to: todayKey };
  const weekday = (today.getDay() + 6) % 7;
  return { from: dateOnly(new Date(today.getTime() - weekday * DAY)), to: dateOnly(new Date(today.getTime() + (6 - weekday) * DAY)) };
}

export function filterProductionRecords(records, { period, product = '', today = new Date() }) {
  const bounds = getProductionPeriodBounds(period, today);
  return records
    .filter((record) => record.date >= bounds.from && record.date <= bounds.to && (!product || record.product === product))
    .sort((a, b) => b.date.localeCompare(a.date));
}

