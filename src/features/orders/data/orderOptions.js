export const ORDER_STATUSES = ['Pendiente', 'Confirmado', 'En preparación', 'Entregado', 'Cancelado'];

export const ORDER_PRODUCTS = [
  { value: 'lechona-personal', label: 'Lechona (Plato individual)', category: 'lechona', productName: 'Lechona', unit: 'Plato' },
  { value: 'hayacas-individual', label: 'Hayaca (Unidad individual)', category: 'hayacas', productName: 'Hayaca', unit: 'Unidad' },
];

export function getProduct(productId) {
  return ORDER_PRODUCTS.find(
    (product) =>
      product.value === productId ||
      product.productName?.toLowerCase() === String(productId ?? '').toLowerCase()
  );
}

export function getProductCategory(productId) {
  return getProduct(productId)?.category ?? '';
}
