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

export const ORDERS_PAGE_SIZE = 15;

function PlusIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v16M4 12h16"/></svg>;
}

export function OrdersPagination({ page, pageCount, resultCount, totalCount, onPage }) {
  const start = resultCount ? (page - 1) * ORDERS_PAGE_SIZE + 1 : 0;
  const end = Math.min(page * ORDERS_PAGE_SIZE, resultCount);
  const maxVisiblePages = 7;
  let startPage = Math.max(1, page - Math.floor(maxVisiblePages / 2));
  let endPage = Math.min(pageCount, startPage + maxVisiblePages - 1);
  if (endPage - startPage + 1 < maxVisiblePages) {
    startPage = Math.max(1, endPage - maxVisiblePages + 1);
  }
  const visiblePageNumbers = Array.from(
    { length: endPage - startPage + 1 },
    (_, index) => startPage + index
  );

  return (
    <footer className="orders-pagination sales-pagination" style={{ maxWidth: '980px' }}>
      <p>
        Mostrando <strong>{start}–{end}</strong> de <strong>{resultCount}</strong> pedidos filtrados{' '}
        <span>({totalCount} en total · Página {page} de {pageCount})</span>
      </p>
      {pageCount > 1 && (
        <nav aria-label="Paginación de pedidos">
          <button
            type="button"
            aria-label="Página anterior"
            disabled={page === 1}
            onClick={() => onPage(page - 1)}
          >
            ‹
          </button>
          {visiblePageNumbers.map((number) => (
            <button
              key={number}
              type="button"
              className={number === page ? 'is-active' : ''}
              aria-current={number === page ? 'page' : undefined}
              onClick={() => onPage(number)}
            >
              {number}
            </button>
          ))}
          <button
            type="button"
            aria-label="Página siguiente"
            disabled={page === pageCount}
            onClick={() => onPage(page + 1)}
          >
            ›
          </button>
        </nav>
      )}
    </footer>
  );
}

export default function OrdersPage() {
  const { openMenu } = useOutletContext();
  const { orders, error: storageError, create, update, remove } = useOrders();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [product, setProduct] = useState('');
  const [date, setDate] = useState('');
  const [page, setPage] = useState(1);
  const [editingOrder, setEditingOrder] = useState(null);
  const [deletingOrder, setDeletingOrder] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);
  useEffect(() => setPage(1), [search, status, product, date]);

  const visibleOrders = useMemo(
    () => filterOrders(orders, { search, status, product, date }),
    [orders, search, status, product, date]
  );
  const pageCount = Math.max(1, Math.ceil(visibleOrders.length / ORDERS_PAGE_SIZE));
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  const pageOrders = useMemo(() => {
    const start = (page - 1) * ORDERS_PAGE_SIZE;
    return visibleOrders.slice(start, start + ORDERS_PAGE_SIZE);
  }, [visibleOrders, page]);

  const pendingCount = orders.filter((order) => order.status === 'Pendiente').length;
  const deliveredCount = orders.filter((order) => order.status === 'Entregado').length;
  const hasFilters = Boolean(search.trim() || status || product || date);

  function announce(message, kind = 'success') {
    setToast({ message, kind });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3500);
  }

  async function handleSave(data) {
    try {
      if (editingOrder) {
        await update(editingOrder.id, data);
        setEditingOrder(null);
        announce('El pedido se actualizó correctamente.');
      } else {
        await create(data);
        setIsCreating(false);
        setPage(1);
        announce('El pedido se registró correctamente.');
      }
    } catch (saveError) {
      announce(saveError.message || 'No fue posible guardar el pedido.', 'error');
    }
  }

  async function handleDelete() {
    try {
      await remove(deletingOrder.id);
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
    setPage(1);
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
    <OrdersList
      orders={pageOrders}
      hasFilters={hasFilters}
      onEdit={setEditingOrder}
      onDelete={setDeletingOrder}
      onCreate={() => setIsCreating(true)}
      pagination={
        <OrdersPagination
          page={page}
          pageCount={pageCount}
          resultCount={visibleOrders.length}
          totalCount={orders.length}
          onPage={setPage}
        />
      }
    />

    {isCreating && <OrderFormModal onClose={() => setIsCreating(false)} onSave={handleSave} />}
    {editingOrder && <OrderFormModal order={editingOrder} onClose={() => setEditingOrder(null)} onSave={handleSave} />}
    {deletingOrder && <DeleteOrderDialog order={deletingOrder} onCancel={() => setDeletingOrder(null)} onConfirm={handleDelete} />}
    {toast && <div className={`orders-toast orders-toast--${toast.kind}`} role="status" aria-live="polite">{toast.message}</div>}
  </div>;
}
