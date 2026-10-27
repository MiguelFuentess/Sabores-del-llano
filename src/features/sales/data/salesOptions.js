export const SALE_PRODUCTS = [
  { value: 'lechona', label: 'Lechona Tolimense (Porción)', shortLabel: 'Lechona', unit: 'porciones' },
  { value: 'hayacas', label: 'Hayacas Tradicionales', shortLabel: 'Hayacas', unit: 'uds' },
];

export const SALES_PAGE_SIZE = 6;

export function getSaleProduct(productId) {
  return SALE_PRODUCTS.find((product) => product.value === productId);
}

