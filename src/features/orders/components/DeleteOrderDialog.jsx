import Button from '../../../components/ui/Button.jsx';
import { getProduct } from '../data/orderOptions.js';

function TrashIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m19 7-.87 12.14A2 2 0 0 1 16.14 21H7.86a2 2 0 0 1-2-1.86L5 7m5 4v6m4-6v6m1-10V4a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v3M4 7h16"/></svg>;
}

export default function DeleteOrderDialog({ order, onCancel, onConfirm }) {
  const product = getProduct(order.product)?.label ?? 'producto';
  return <div className="orders-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}>
    <section className="orders-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-order-title" aria-describedby="delete-order-description">
      <h2 id="delete-order-title">¿Estás seguro de eliminar este pedido?</h2>
      <p id="delete-order-description">Esta acción no se puede deshacer. Se eliminará permanentemente el pedido <strong>#{order.orderNumber} de {order.customer}</strong> ({order.quantity} × {product}) del registro.</p>
      <div className="orders-confirm-dialog__actions">
        <Button variant="quiet" onClick={onCancel}>Cancelar</Button>
        <Button variant="danger" onClick={onConfirm}><TrashIcon />Eliminar pedido</Button>
      </div>
    </section>
  </div>;
}
