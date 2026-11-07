import { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import Button from '../../../components/ui/Button.jsx';
import PageHeader from '../../../components/ui/PageHeader.jsx';
import StatCard from '../../../components/ui/StatCard.jsx';
import DeleteProductionDialog from '../components/DeleteProductionDialog.jsx';
import ProductionFormModal from '../components/ProductionFormModal.jsx';
import { PRODUCTION_PRODUCTS } from '../data/productionOptions.js';
import useProductionRecords from '../hooks/useProductionRecords.js';
import { downloadProductionReport } from '../services/productionStorage.js';
import useSales from '../../sales/hooks/useSales.js';
import { filterSales } from '../../sales/utils/filterSales.js';
import {
  filterProductionRecords,
  getProductionPeriodBounds,
} from '../utils/productionAnalytics.js';

const shortDate = new Intl.DateTimeFormat('es-CO', {
  day: '2-digit',
  month: 'short',
  timeZone: 'UTC',
});
const fullDate = new Intl.DateTimeFormat('es-CO', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});
const countFormat = new Intl.NumberFormat('es-CO');

function dateAtNoon(value) {
  return new Date(`${value}T12:00:00Z`);
}
function formatDate(value, formatter = fullDate) {
  return formatter.format(dateAtNoon(value));
}

function periodLabel(period) {
  if (!period || period === 'all') return 'Todo el historial';
  const bounds = getProductionPeriodBounds(period);
  if (period === 'week') {
    return `Esta semana (${formatDate(bounds.from, shortDate)} - ${formatDate(
      bounds.to,
      shortDate
    )})`;
  }
  if (period === '15days') return 'Últimos 15 días';
  return 'Este mes';
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3v12m0 0 4.5-4.5M12 15l-4.5-4.5M4 16.5v2.25A2.25 2.25 0 0 0 6.25 21h11.5A2.25 2.25 0 0 0 20 18.75V16.5" />
    </svg>
  );
}
function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m15 5 4 4M4 20l4-.8L19.5 7.7a2.1 2.1 0 0 0-3-3L5 16.2 4 20Z" />
    </svg>
  );
}
function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16M10 11v6m4-6v6M5 7l1 14h12l1-14M9 7V4h6v3" />
    </svg>
  );
}

function ProductionChart({ records, sales }) {
  const byDate = records.reduce((groups, record) => {
    groups[record.date] ??= { produced: 0, sold: 0 };
    groups[record.date].produced += record.quantity;
    return groups;
  }, {});
  sales.forEach((sale) => {
    byDate[sale.date] ??= { produced: 0, sold: 0 };
    byDate[sale.date].sold += sale.quantity;
  });
  const days = Object.entries(byDate).sort(([a], [b]) => a.localeCompare(b));
  const max = Math.max(
    ...days.flatMap(([, values]) => [values.produced, values.sold]),
    0
  );

  return (
    <section
      className="production-card production-chart"
      aria-labelledby="production-chart-title"
    >
      <div className="production-chart__header">
        <div>
          <span className="production-eyebrow">BALANCE POR HORNADA</span>
          <h2 id="production-chart-title">Unidades Producidas vs. Vendidas</h2>
        </div>
        <div className="production-chart__legend">
          <span>
            <i className="production-legend-dot" />
            Producido
          </span>
          <span className="production-chart__sales-note">Vendido</span>
        </div>
      </div>
      {days.length ? (
        <div
          className="production-chart__plot"
          role="img"
          aria-label="Unidades producidas y ventas registradas por fecha; las ventas pueden corresponder a producto de jornadas anteriores"
        >
          {days.map(([date, values]) => (
            <div
              className="production-chart__day"
              key={date}
              title={`${formatDate(date)}: ${values.produced} producidas, ${
                values.sold
              } vendidas`}
            >
              <div className="production-chart__bar-area">
                <span className="production-chart__value">
                  {values.produced} / {values.sold}
                </span>
                <div className="production-chart__bars">
                  <div
                    className="production-chart__bar"
                    style={{
                      height: `${
                        values.produced
                          ? Math.max(4, (values.produced / max) * 145)
                          : 2
                      }px`,
                    }}
                  />
                  <div
                    className="production-chart__bar production-chart__bar--sales"
                    style={{
                      height: `${
                        values.sold
                          ? Math.max(4, (values.sold / max) * 145)
                          : 2
                      }px`,
                    }}
                  />
                </div>
              </div>
              <span className="production-chart__date">
                {formatDate(date, shortDate)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="production-chart__empty">
          Los registros de producción y ventas del período aparecerán aquí.
        </div>
      )}
      <p className="production-data-note">
        Las ventas se muestran por su fecha de registro y no se asignan a una
        hornada específica; pueden incluir producto conservado de jornadas
        anteriores.
      </p>
    </section>
  );
}

function ProductionHistory({ records, sales, onEdit, onDelete }) {
  const sortedRecords = useMemo(
    () =>
      [...records].sort(
        (a, b) => b.date.localeCompare(a.date) || Number(b.id) - Number(a.id)
      ),
    [records]
  );
  const salesByDateProduct = useMemo(
    () =>
      sales.reduce((totals, sale) => {
        const key = `${sale.date}:${sale.product}`;
        totals[key] = (totals[key] ?? 0) + sale.quantity;
        return totals;
      }, {}),
    [sales]
  );

  return (
    <section
      className="production-history production-card"
      aria-labelledby="production-history-title"
    >
      <div className="production-history__ribbon">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M19 11H5m14 0a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2m14 0V9a2 2 0 0 0-2-2M5 11V9a2 2 0 0 1 2-2m0 0V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2M7 7h10" />
        </svg>
        <h2 id="production-history-title">
          HISTORIAL DE PRODUCCIÓN Y BALANCE DE VENTAS
        </h2>
      </div>
      <div className="production-table-wrap">
        <table className="production-table">
          <thead>
            <tr>
              <th scope="col">Fecha y producto</th>
              <th scope="col">Cant. producida</th>
              <th scope="col">Cant. vendida</th>
              <th scope="col">Sobrantes / merma</th>
              <th scope="col">Rendimiento / estado</th>
              <th scope="col" className="production-table__actions-heading">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedRecords.length ? (
              sortedRecords.map((record) => {
                const productLabel =
                  PRODUCTION_PRODUCTS.find(
                    ({ value }) => value === record.product
                  )?.label ??
                  (record.product === 'hayacas' ? 'Hayacas' : 'Lechona');
                const dateSales =
                  salesByDateProduct[`${record.date}:${record.product}`] ??
                  record.soldQuantity ??
                  0;
                const efficiencyPct = record.quantity
                  ? `${((dateSales / record.quantity) * 100).toFixed(1)}% vendido`
                  : 'Sin lote asignado';
                const unitAbbr =
                  record.baseUnit === 'Plato' ? 'platos' : 'uds';

                return (
                  <tr key={record.id}>
                    <td>
                      <strong>{productLabel}</strong>
                      <small>{formatDate(record.date)}</small>
                    </td>
                    <td>
                      {countFormat.format(record.quantity)} {unitAbbr}
                    </td>
                    <td title="Ventas registradas en esa fecha; pueden incluir existencias anteriores">
                      {countFormat.format(dateSales)} {unitAbbr}
                      <small className="production-unavailable">
                        Fecha de venta, no lote
                      </small>
                    </td>
                    <td>
                      {countFormat.format(record.leftovers)} {unitAbbr}
                    </td>
                    <td className="production-unavailable">{efficiencyPct}</td>
                    <td className="production-table__actions">
                      <div className="sales-table__actions">
                        <button
                          type="button"
                          title={`Editar producción de ${productLabel}`}
                          aria-label={`Editar producción de ${productLabel} del ${formatDate(
                            record.date
                          )}`}
                          onClick={() => onEdit(record)}
                        >
                          <EditIcon />
                        </button>
                        <button
                          type="button"
                          title={`Eliminar producción de ${productLabel}`}
                          aria-label={`Eliminar producción de ${productLabel} del ${formatDate(
                            record.date
                          )}`}
                          onClick={() => onDelete(record)}
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td className="production-table__empty" colSpan="6">
                  No hay registros de producción para los filtros seleccionados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const PRODUCTION_PAGE_SIZE = 15;

function ProductionPagination({
  page,
  pageCount,
  resultCount,
  totalCount,
  onPage,
}) {
  const start = resultCount ? (page - 1) * PRODUCTION_PAGE_SIZE + 1 : 0;
  const end = Math.min(page * PRODUCTION_PAGE_SIZE, resultCount);
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
    <footer className="production-pagination sales-pagination">
      <p>
        Mostrando <strong>{start}–{end}</strong> de{' '}
        <strong>{resultCount}</strong> registros de producción{' '}
        <span>
          ({totalCount} en total · Página {page} de {pageCount})
        </span>
      </p>
      {pageCount > 1 && (
        <nav aria-label="Paginación de producción">
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

export default function ProductionPage() {
  const outletContext = useOutletContext();
  const openMenu = outletContext?.openMenu;
  const { records, error, create, update, remove } = useProductionRecords();
  const { sales } = useSales();
  const [period, setPeriod] = useState('15days');
  const [product, setProduct] = useState('');
  const [page, setPage] = useState(1);
  const [isCreating, setIsCreating] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  const [deletingRecord, setDeletingRecord] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDownloadingReport, setIsDownloadingReport] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  const filtered = useMemo(
    () => filterProductionRecords(records, { period, product }),
    [records, period, product]
  );
  const filteredSales = useMemo(
    () => filterSales(sales, { period, product }),
    [sales, period, product]
  );

  const sortedFiltered = useMemo(
    () =>
      [...filtered].sort(
        (a, b) => b.date.localeCompare(a.date) || Number(b.id) - Number(a.id)
      ),
    [filtered]
  );

  const pageCount = Math.max(1, Math.ceil(sortedFiltered.length / PRODUCTION_PAGE_SIZE));
  const safePage = Math.min(Math.max(1, page), pageCount);

  useEffect(() => {
    setPage(1);
  }, [period, product]);

  useEffect(() => {
    if (page > pageCount) {
      setPage(pageCount);
    }
  }, [page, pageCount]);

  const displayedRecords = useMemo(() => {
    if (period !== 'all') return sortedFiltered;
    const start = (safePage - 1) * PRODUCTION_PAGE_SIZE;
    return sortedFiltered.slice(start, start + PRODUCTION_PAGE_SIZE);
  }, [period, sortedFiltered, safePage]);
  const totals = useMemo(() => {
    const byDateProductLeftovers = {};
    const acc = filtered.reduce(
      (sum, record) => {
        sum.produced += record.quantity;
        sum.producedByProduct[record.product] =
          (sum.producedByProduct[record.product] ?? 0) + record.quantity;
        byDateProductLeftovers[`${record.date}:${record.product}`] = {
          product: record.product,
          leftovers: record.leftovers,
        };
        return sum;
      },
      {
        produced: 0,
        producedByProduct: { lechona: 0, hayacas: 0 },
        leftovers: { lechona: 0, hayacas: 0 },
      }
    );
    Object.values(byDateProductLeftovers).forEach(
      ({ product: prodKey, leftovers }) => {
        acc.leftovers[prodKey] = (acc.leftovers[prodKey] ?? 0) + leftovers;
      }
    );
    return acc;
  }, [filtered]);
  const sold = filteredSales.reduce((total, sale) => total + sale.quantity, 0);
  const salesEfficiency = totals.produced
    ? `${((sold / totals.produced) * 100).toFixed(1)}%`
    : '—';

  function announce(message, kind = 'success') {
    setToast({ message, kind });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3500);
  }

  function handleEdit(record) {
    setEditingRecord(record);
  }

  function handleDelete(record) {
    setDeletingRecord(record);
  }

  async function saveProduction(data) {
    try {
      if (editingRecord) {
        await update(editingRecord.id, data);
        setEditingRecord(null);
        announce('La producción se actualizó correctamente.');
      } else {
        await create(data);
        setIsCreating(false);
        announce('La producción se registró correctamente.');
      }
    } catch (saveError) {
      announce(
        saveError.message || 'No fue posible guardar el registro.',
        'error'
      );
      throw saveError;
    }
  }

  async function confirmDelete() {
    if (!deletingRecord || isDeleting) return;
    setIsDeleting(true);
    try {
      await remove(deletingRecord.id);
      announce('El registro de producción se eliminó correctamente.');
      setDeletingRecord(null);
    } catch (deleteError) {
      announce(
        deleteError.message || 'No fue posible eliminar el registro.',
        'error'
      );
    } finally {
      setIsDeleting(false);
    }
  }

  async function handleDownloadReport() {
    if (isDownloadingReport) return;
    if (sortedFiltered.length === 0) {
      announce(
        'No hay registros de producción para los filtros seleccionados. Ajusta el período o el producto antes de descargar.',
        'error'
      );
      return;
    }

    setIsDownloadingReport(true);
    try {
      const fileName = await downloadProductionReport({ period, product });
      announce(`Reporte descargado: ${fileName}`);
    } catch (downloadError) {
      announce(
        downloadError?.message ||
          'No fue posible descargar el reporte de producción.',
        'error'
      );
    } finally {
      setIsDownloadingReport(false);
    }
  }

  return (
    <div className="production-page">
      <button
        className="orders-mobile-menu"
        type="button"
        aria-label="Abrir menú"
        onClick={openMenu}
      >
        <span />
        <span />
        <span />
      </button>
      <PageHeader
        title="Producción y Análisis"
        description="Balance de unidades producidas vs. vendidas y análisis de rendimiento para toma de decisiones artesanales."
        actions={
          <>
            <Button
              variant="quiet"
              className="production-report-button"
              disabled={isDownloadingReport}
              title={
                sortedFiltered.length === 0
                  ? 'No hay registros en los filtros actuales para exportar'
                  : 'Descargar reporte en Excel (.xlsx) según los filtros aplicados'
              }
              onClick={handleDownloadReport}
            >
              <DownloadIcon />
              {isDownloadingReport ? 'Descargando...' : 'Descargar reporte'}
            </Button>
            <Button onClick={() => setIsCreating(true)}>
              <PlusIcon />
              Registrar producción
            </Button>
          </>
        }
      />

      <section
        className="production-metrics"
        aria-label="Indicadores de producción"
      >
        <StatCard
          label="Total producido (período)"
          value={`${countFormat.format(totals.produced)} uds`}
          detail={
            <>
              <span className="production-product-total production-product-total--hayacas">
                {countFormat.format(totals.producedByProduct.hayacas)} Hayacas
              </span>
              <span className="production-product-total production-product-total--lechona">
                {countFormat.format(totals.producedByProduct.lechona)} Lechona
              </span>
            </>
          }
        />
        <StatCard
          label="Total vendido"
          value={`${countFormat.format(sold)} uds`}
          detail="Según el registro compartido de Ventas"
        />
        <StatCard
          label="Unidades sobrantes"
          value={`${countFormat.format(
            totals.leftovers.lechona
          )} · ${countFormat.format(totals.leftovers.hayacas)}`}
          detail="Lechona · Hayacas"
        />
        <StatCard
          label="Eficiencia de producción"
          value={salesEfficiency}
          detail={
            totals.produced
              ? 'Ventas del período / producción del período'
              : 'Sin producción registrada en el período'
          }
        />
      </section>

      <div className="production-filters" aria-label="Filtros de producción">
        <div className="production-periods">
          <span>PERÍODO:</span>
          {[
            ['all', 'Todo el historial'],
            ['week', periodLabel('week')],
            ['15days', 'Últimos 15 días'],
            ['month', periodLabel('month')],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={period === key ? 'is-active' : ''}
              aria-pressed={period === key}
              onClick={() => setPeriod(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="production-product-filter">
          <span className="sr-only">Filtrar productos</span>
          <select
            value={product}
            onChange={(event) => setProduct(event.target.value)}
          >
            <option value="">Filtrar: Todos los productos</option>
            {PRODUCTION_PRODUCTS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <p className="orders-storage-error" role="alert">
          {error}
        </p>
      )}
      <ProductionChart records={filtered} sales={filteredSales} />
      <ProductionHistory
        records={displayedRecords}
        sales={filteredSales}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />
      {period === 'all' && (
        <ProductionPagination
          page={safePage}
          pageCount={pageCount}
          resultCount={sortedFiltered.length}
          totalCount={records.length}
          onPage={setPage}
        />
      )}
      {isCreating && (
        <ProductionFormModal
          onClose={() => setIsCreating(false)}
          onSave={saveProduction}
        />
      )}
      {editingRecord && (
        <ProductionFormModal
          record={editingRecord}
          onClose={() => setEditingRecord(null)}
          onSave={saveProduction}
        />
      )}
      {deletingRecord && (
        <DeleteProductionDialog
          record={deletingRecord}
          onCancel={() => setDeletingRecord(null)}
          onConfirm={confirmDelete}
          isDeleting={isDeleting}
        />
      )}
      {toast && (
        <div
          className={`orders-toast${
            toast.kind === 'error' ? ' orders-toast--error' : ''
          }`}
          role="status"
          aria-live="polite"
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
