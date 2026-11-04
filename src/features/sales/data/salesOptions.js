export const SALE_PRODUCTS = [
  {
    value: 'lechona',
    apiName: 'Lechona',
    label: 'Lechona Tolimense (Porción)',
    shortLabel: 'Lechona',
    unit: 'porciones',
    defaultPrice: 12000,
  },
  {
    value: 'hayacas',
    apiName: 'Hayaca',
    label: 'Hayacas Tradicionales',
    shortLabel: 'Hayacas',
    unit: 'uds',
    defaultPrice: 10000,
  },
];

export const SALES_PAGE_SIZE = 6;

export function getSaleProduct(productId) {
  return SALE_PRODUCTS.find((product) => product.value === productId);
}

export function getDefaultUnitPrice(productId) {
  return getSaleProduct(productId)?.defaultPrice ?? 10000;
}
