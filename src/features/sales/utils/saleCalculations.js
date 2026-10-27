export function calculateSaleTotal(quantity, unitPrice) {
  const total = Number(quantity) * Number(unitPrice);
  return Number.isFinite(total) ? total : 0;
}

