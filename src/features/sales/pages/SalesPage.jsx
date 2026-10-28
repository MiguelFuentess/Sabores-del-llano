import { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import Button from '../../../components/ui/Button.jsx';
import PageHeader from '../../../components/ui/PageHeader.jsx';
import StatCard from '../../../components/ui/StatCard.jsx';
import DeleteSaleDialog from '../components/DeleteSaleDialog.jsx';
import SaleFormModal from '../components/SaleFormModal.jsx';
import SalesFilters from '../components/SalesFilters.jsx';
import { getSaleProduct, SALES_PAGE_SIZE } from '../data/salesOptions.js';
import useSales from '../hooks/useSales.js';
import { filterSales, formatCOP, formatSaleDate, formatSaleTime, summarizeSales } from '../utils/filterSales.js';

const countFormat = new Intl.NumberFormat('es-CO');

function PlusIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v16M4 12h16" /></svg>; }
function DownloadIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0 4.5-4.5M12 15l-4.5-4.5M4 16.5v2.25A2.25 2.25 0 0 0 6.25 21h11.5A2.25 2.25 0 0 0 20 18.75V16.5" /></svg>; }
function EditIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5 4 4M4 20l4-.8L19.5 7.7a2.1 2.1 0 0 0-3-3L5 16.2 4 20Z" /></svg>; }
function TrashIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6m4-6v6M5 7l1 14h12l1-14M9 7V4h6v3" /></svg>; }

function SaleTable({ sales, hasAnySales, onCreate, onEdit, onDelete }) {
  return <section className="sales-table-card" aria-label="Tabla de ventas">
    <header className="sales-table-card__header"><h2>LISTADO DE VENTAS REALIZADAS</h2></header>
    <div className="sales-table-wrap"><table className="sales-table">
      <thead><tr><th scope="col">Fecha</th><th scope="col">Producto</th><th scope="col">Cantidad vendida</th><th scope="col">Precio unitario</th><th scope="col">Total</th><th scope="col" className="sales-table__actions-heading">Acciones</th></tr></thead>
      <tbody>{sales.length ? sales.map((sale) => {
        const product = getSaleProduct(sale.product);
        return <tr key={sale.id}>
          <td className="sales-table__date"><strong>{formatSaleDate(sale.date)}</strong><span> · {formatSaleTime(sale.time)}</span><small>Venta #{String(sale.receiptNumber).padStart(3, '0')}</small></td>
          <td className="sales-table__product">{product?.label ?? 'Producto'}</td>
          <td className="sales-table__quantity">{countFormat.format(sale.quantity)} {product?.unit ?? 'uds'}</td>
          <td>{formatCOP(sale.unitPrice)}</td>
          <td className="sales-table__total">{formatCOP(sale.total)}</td>
          <td className="sales-table__actions"><button type="button" title={`Editar venta ${sale.receiptNumber}`} aria-label={`Editar venta ${sale.receiptNumber}`} onClick={() => onEdit(sale)}><EditIcon /></button><button type="button" title={`Eliminar venta ${sale.receiptNumber}`} aria-label={`Eliminar venta ${sale.receiptNumber}`} onClick={() => onDelete(sale)}><TrashIcon /></button></td>
        </tr>;
      }) : <tr><td className="sales-empty" colSpan="6"><strong>{hasAnySales ? 'No hay ventas que coincidan con la búsqueda o los filtros.' : 'Aún no hay ventas registradas.'}</strong>{!hasAnySales && <><span>Registra la primera operación efectivamente realizada.</span><Button onClick={onCreate}><PlusIcon />Registrar venta</Button></>}</td></tr>}</tbody>
    </table></div>
  </section>;
}

function SalesPagination({ page, pageCount, resultCount, totalCount, onPage }) {
  const start = resultCount ? (page - 1) * SALES_PAGE_SIZE + 1 : 0;
  const end = Math.min(page * SALES_PAGE_SIZE, resultCount);
  return <footer className="sales-pagination"><p>Mostrando <strong>{start}–{end}</strong> de <strong>{resultCount}</strong> ventas filtradas <span>({totalCount} en total)</span></p>
    {pageCount > 1 && <nav aria-label="Paginación de ventas"><button type="button" aria-label="Página anterior" disabled={page === 1} onClick={() => onPage(page - 1)}>‹</button>{Array.from({ length: pageCount }, (_, index) => index + 1).map((number) => <button key={number} type="button" className={number === page ? 'is-active' : ''} aria-current={number === page ? 'page' : undefined} onClick={() => onPage(number)}>{number}</button>)}<button type="button" aria-label="Página siguiente" disabled={page === pageCount} onClick={() => onPage(page + 1)}>›</button></nav>}
  </footer>;
}

function currentDate() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export default function SalesPage() {
  const { openMenu } = useOutletContext();
  const { sales, error: storageError, create, update, remove } = useSales();
  const [search, setSearch] = useState('');
  const [period, setPeriod] = useState('week');
  const [product, setProduct] = useState('');
  const [page, setPage] = useState(1);
  const [isCreating, setIsCreating] = useState(false);
  const [editingSale, setEditingSale] = useState(null);
  const [deletingSale, setDeletingSale] = useState(null);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  useEffect(() => () => window.clearTimeout(toastTimer.current), []);
  useEffect(() => setPage(1), [search, period, product]);

  const visibleSales = useMemo(() => filterSales(sales, { search, period, product }), [sales, search, period, product]);
  const summary = useMemo(() => summarizeSales(visibleSales), [visibleSales]);
  const todayTotal = useMemo(() => visibleSales.filter((sale) => sale.date === currentDate()).reduce((total, sale) => total + sale.total, 0), [visibleSales]);
  const pageCount = Math.max(1, Math.ceil(visibleSales.length / SALES_PAGE_SIZE));
  const pageSales = visibleSales.slice((page - 1) * SALES_PAGE_SIZE, page * SALES_PAGE_SIZE);
  useEffect(() => { if (page > pageCount) setPage(pageCount); }, [page, pageCount]);

  function announce(message, kind = 'success') {
    setToast({ message, kind });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3500);
  }

  function saveSale(data) {
    try {
      if (editingSale) {
        update(editingSale.id, data);
        setEditingSale(null);
        announce('La venta se actualizó correctamente.');
      } else {
        create(data);
        setIsCreating(false);
        setPage(1);
        announce('La venta se registró correctamente.');
      }
    } catch (saveError) {
      announce(saveError.message || 'No fue posible guardar la venta.', 'error');
    }
  }

  function confirmDelete() {
    try {
      remove(deletingSale.id);
      announce(`Se eliminó la venta #${String(deletingSale.receiptNumber).padStart(3, '0')}.`);
      setDeletingSale(null);
    } catch (deleteError) {
      announce(deleteError.message || 'No fue posible eliminar la venta.', 'error');
    }
  }

  return <div className="sales-page">
    <button className="orders-mobile-menu" type="button" aria-label="Abrir menú" onClick={openMenu}><span /><span /><span /></button>
    <PageHeader title="Ventas" description="Consulta el historial de ventas y registra las operaciones efectivamente realizadas." actions={<><Button variant="quiet" className="sales-report-button" aria-disabled="true" title="Exportación disponible en una etapa posterior"><DownloadIcon />Descargar reporte</Button><Button onClick={() => setIsCreating(true)}><PlusIcon />Registrar venta</Button></>} />

    <section className="sales-metrics" aria-label="Métricas principales">
      <StatCard label="Total ventas (período)" value={formatCOP(summary.total)} detail={`${countFormat.format(summary.count)} transacciones registradas`} />
      <article className="stat-card sales-units-card"><span className="stat-card__label">Unidades vendidas</span><div className="sales-units-summary"><span><strong>{countFormat.format(summary.units.hayacas)} uds</strong><small>Hayacas</small></span><span><strong>{countFormat.format(summary.units.lechona)} porciones</strong><small>Lechona</small></span></div></article>
      <StatCard label="Venta del día" value={formatCOP(todayTotal)} detail="Operaciones registradas hoy" />
    </section>

    <SalesFilters search={search} onSearch={setSearch} period={period} onPeriod={setPeriod} product={product} onProduct={setProduct} />
    {storageError && <p className="orders-storage-error" role="alert">{storageError}</p>}
    <SaleTable sales={pageSales} hasAnySales={sales.length > 0} onCreate={() => setIsCreating(true)} onEdit={setEditingSale} onDelete={setDeletingSale} />
    <SalesPagination page={page} pageCount={pageCount} resultCount={visibleSales.length} totalCount={sales.length} onPage={setPage} />

    {isCreating && <SaleFormModal onClose={() => setIsCreating(false)} onSave={saveSale} />}
    {editingSale && <SaleFormModal sale={editingSale} onClose={() => setEditingSale(null)} onSave={saveSale} />}
    {deletingSale && <DeleteSaleDialog sale={deletingSale} onCancel={() => setDeletingSale(null)} onConfirm={confirmDelete} />}
    {toast && <div className={`orders-toast${toast.kind === 'error' ? ' orders-toast--error' : ''}`} role="status" aria-live="polite">{toast.message}</div>}
  </div>;
}

