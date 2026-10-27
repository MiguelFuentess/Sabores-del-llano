import Button from '../../../components/ui/Button.jsx';
import { getSaleProduct } from '../data/salesOptions.js';
import { formatCOP } from '../utils/filterSales.js';

function TrashIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m19 7-.87 12.14A2 2 0 0 1 16.14 21H7.86a2 2 0 0 1-2-1.86L5 7m5 4v6m4-6v6m1-10V4a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v3M4 7h16" /></svg>; }

export default function DeleteSaleDialog({ sale, onCancel, onConfirm }) {
  const product = getSaleProduct(sale.product);
  return <div className="orders-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}>
    <section className="orders-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-sale-title" aria-describedby="delete-sale-description">
      <h2 id="delete-sale-title">¿Estás seguro de eliminar esta venta?</h2>
      <p id="delete-sale-description">Se eliminará permanentemente la venta <strong>#{String(sale.receiptNumber).padStart(3, '0')}</strong> de {sale.quantity} {product?.unit ?? 'unidades'} de {product?.label ?? 'producto'} por {formatCOP(sale.total)}. Esta acción no se puede deshacer.</p>
      <div className="orders-confirm-dialog__actions"><Button variant="quiet" onClick={onCancel}>Cancelar</Button><Button variant="danger" onClick={onConfirm}><TrashIcon />Eliminar venta</Button></div>
    </section>
  </div>;
}

