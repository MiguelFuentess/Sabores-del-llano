export const ORDER_STATUSES = ['Pendiente', 'Confirmado', 'En preparación', 'Entregado'];

export const ORDER_PRODUCTS = [
  { value: 'lechona-personal', label: 'Lechona Tolimense (Porción personal)', category: 'lechona' },
  { value: 'lechona-cojin-30', label: 'Cojín de Lechona (30 porciones)', category: 'lechona' },
  { value: 'lechona-cojin-50', label: 'Cojín de Lechona (50 porciones)', category: 'lechona' },
  { value: 'hayacas-dozen', label: 'Hayacas Tradicionales x Docena', category: 'hayacas' },
  { value: 'hayacas-individual', label: 'Hayacas Individuales', category: 'hayacas' },
];

export const INITIAL_DEMO_ORDERS = [
  { id: 'demo-order-001', orderNumber: '001', customer: 'Carlos Mendoza', product: 'hayacas-individual', quantity: 12, registeredDate: '2026-10-20', deliveryDate: '2026-10-21', deliveryTime: '12:15', deliveryMode: 'retiro', address: '', observations: '', status: 'Pendiente' },
  { id: 'demo-order-002', orderNumber: '002', customer: 'Familia Guzmán', product: 'lechona-personal', quantity: 20, registeredDate: '2026-10-20', deliveryDate: '2026-10-21', deliveryTime: '12:30', deliveryMode: 'retiro', address: '', observations: '', status: 'Confirmado' },
  { id: 'demo-order-003', orderNumber: '003', customer: 'Andrés Vargas', product: 'hayacas-individual', quantity: 10, registeredDate: '2026-10-19', deliveryDate: '2026-10-20', deliveryTime: '', deliveryMode: 'domicilio', address: 'Las Palmas', observations: '', status: 'Entregado' },
  { id: 'demo-order-004', orderNumber: '004', customer: 'Dra. Claudia Ortiz', product: 'lechona-cojin-30', quantity: 1, registeredDate: '2026-10-19', deliveryDate: '2026-10-20', deliveryTime: '', deliveryMode: 'retiro', address: '', observations: 'Incluye 6 hayacas.', status: 'En preparación' },
  { id: 'demo-order-005', orderNumber: '005', customer: 'Restaurante El Tolimita', product: 'hayacas-individual', quantity: 25, registeredDate: '2026-10-18', deliveryDate: '2026-10-19', deliveryTime: '', deliveryMode: 'domicilio', address: 'Centro', observations: '', status: 'Entregado' },
  { id: 'demo-order-006', orderNumber: '006', customer: 'Carmen Agudelo', product: 'hayacas-individual', quantity: 7, registeredDate: '2026-10-18', deliveryDate: '2026-10-19', deliveryTime: '', deliveryMode: 'retiro', address: '', observations: '', status: 'Entregado' },
];

export function getProduct(productId) {
  return ORDER_PRODUCTS.find((product) => product.value === productId);
}

export function getProductCategory(productId) {
  return getProduct(productId)?.category ?? '';
}
