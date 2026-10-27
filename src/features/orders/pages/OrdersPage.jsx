import { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import Button from '../../../components/ui/Button.jsx';
import PageHeader from '../../../components/ui/PageHeader.jsx';
import StatCard from '../../../components/ui/StatCard.jsx';
import useOrders from '../hooks/useOrders.js';
import { filterOrders } from '../utils/filterOrders.js';
import DeleteOrderDialog from '../components/DeleteOrderDialog.jsx';
import OrderFormModal from '../components/OrderFormModal.jsx';
import OrdersFilters from '../components/OrdersFilters.jsx';
import OrdersList from '../components/OrdersList.jsx';

function PlusIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v16M4 12h16"/></svg>;
}

export default function OrdersPage() {
  const { openMenu } = useOutletContext();
  const { orders, error: storageError, create, update, remove } = useOrders();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [product, setProduct] = useState('');
  const [date, setDate] = useState('');
  const [editingOrder, setEditingOrder] = useState(null);
  const [deletingOrder, setDeletingOrder] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  const visibleOrders = useMemo(() => filterOrders(orders, { search, status, product, date }), [orders, search, status, product, date]);

  const customers = useMemo(() => [...new Set(orders.map((order) => order.customer).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es')), [orders]);
  const pendingCount = orders.filter((order) => order.status === 'Pendiente').length;
  const deliveredCount = orders.filter((order) => order.status === 'Entregado').length;
  const hasFilters = Boolean(search.trim() || status || product || date);

  function announce(message, kind = 'success') {
    setToast({ message, kind });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3500);
  }

  function handleSave(data) {
    try {
      if (editingOrder) {
        update(editingOrder.id, data);
        setEditingOrder(null);
        announce('El pedido se actualizó correctamente.');
      } else {
        create(data);
        setIsCreating(false);
        announce('El pedido se registró correctamente.');
      }
    } catch (saveError) {
      announce(saveError.message || 'No fue posible guardar el pedido.', 'error');
    }
  }

  function handleDelete() {
    try {
      remove(deletingOrder.id);
      announce(`Se eliminó el pedido #${deletingOrder.orderNumber}.`);
      setDeletingOrder(null);
    } catch (deleteError) {
      announce(deleteError.message || 'No fue posible eliminar el pedido.', 'error');
    }
  }

  function clearFilters() {
    setSearch('');
    setStatus('');
    setProduct('');
    setDate('');
  }

  return <div className="orders-page">
    <button className="orders-mobile-menu" type="button" aria-label="Abrir menú" onClick={openMenu}><span/><span/><span/></button>
    <PageHeader title="Pedidos" description="Administra los pedidos y la información" actions={<Button onClick={() => setIsCreating(true)}><PlusIcon />Nuevo pedido</Button>} />

    <section className="orders-metrics" aria-label="Resumen de pedidos">
      <StatCard label="Total pedidos" value={orders.length} />
      <StatCard label="Pendientes" value={pendingCount} />
      <StatCard label="Entregados" value={deliveredCount} />
    </section>

    <OrdersFilters search={search} onSearch={setSearch} status={status} onStatus={setStatus} product={product} onProduct={setProduct} date={date} onDate={setDate} onClear={clearFilters} />

    {storageError && <p className="orders-storage-error" role="alert">{storageError}</p>}
    <OrdersList orders={visibleOrders} hasFilters={hasFilters} onEdit={setEditingOrder} onDelete={setDeletingOrder} onCreate={() => setIsCreating(true)} />

    {isCreating && <OrderFormModal customers={customers} onClose={() => setIsCreating(false)} onSave={handleSave} />}
    {editingOrder && <OrderFormModal order={editingOrder} customers={customers} onClose={() => setEditingOrder(null)} onSave={handleSave} />}
    {deletingOrder && <DeleteOrderDialog order={deletingOrder} onCancel={() => setDeletingOrder(null)} onConfirm={handleDelete} />}
    {toast && <div className={`orders-toast orders-toast--${toast.kind}`} role="status" aria-live="polite">{toast.message}</div>}
  </div>;
}


