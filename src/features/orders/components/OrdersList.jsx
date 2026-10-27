import Button from '../../../components/ui/Button.jsx';
import StatusBadge from '../../../components/ui/StatusBadge.jsx';
import { getProductCategory } from '../data/orderOptions.js';
import { formatDeliveryDate, orderDescription } from '../utils/orderPresentation.js';

function EditIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15.23 5.23 3.54 3.54M4 20l3.57-.01L19.5 8.04a2.5 2.5 0 0 0-3.54-3.54L4.03 16.43 4 20Z"/></svg>;
}
function TrashIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m19 7-.87 12.14A2 2 0 0 1 16.14 21H7.86a2 2 0 0 1-2-1.86L5 7m5 4v6m4-6v6m1-10V4a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v3M4 7h16"/></svg>;
}

export default function OrdersList({ orders, hasFilters, onEdit, onDelete, onCreate }) {
  return <section className="orders-list-card" aria-labelledby="orders-list-title">
    <div className="orders-list-card__heading"><h2 id="orders-list-title">Listado de pedidos</h2></div>
    {orders.length ? <div className="orders-list">
      {orders.map((order) => <article className="order-row" key={order.id}>
        <div className="order-row__details">
          <h3>{order.customer}</h3>
          <p>#{order.orderNumber} · {orderDescription(order)}</p>
          <time dateTime={order.deliveryDate}>{formatDeliveryDate(order.deliveryDate)}</time>
        </div>
        <div className="order-row__actions">
          <StatusBadge>{order.status}</StatusBadge>
          <div className="order-row__buttons">
            <Button variant="icon" aria-label={`Editar pedido ${order.orderNumber}`} title="Editar pedido" onClick={() => onEdit(order)}><EditIcon /></Button>
            <Button variant="icon" aria-label={`Eliminar pedido ${order.orderNumber}`} title="Eliminar pedido" onClick={() => onDelete(order)}><TrashIcon /></Button>
          </div>
        </div>
      </article>)}
    </div> : <div className="orders-empty-state">
      <p>{hasFilters ? 'No se encontraron pedidos con esos filtros.' : 'Aún no hay pedidos registrados.'}</p>
      {!hasFilters && <Button onClick={onCreate}>Registrar primer pedido</Button>}
    </div>}
  </section>;
}
