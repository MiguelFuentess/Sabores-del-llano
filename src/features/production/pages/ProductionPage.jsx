import { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import Button from '../../../components/ui/Button.jsx';
import PageHeader from '../../../components/ui/PageHeader.jsx';
import StatCard from '../../../components/ui/StatCard.jsx';
import ProductionFormModal from '../components/ProductionFormModal.jsx';
import { PRODUCTION_PRODUCTS } from '../data/productionOptions.js';
import useProductionRecords from '../hooks/useProductionRecords.js';
import useSales from '../../sales/hooks/useSales.js';
import { filterSales } from '../../sales/utils/filterSales.js';
import { filterProductionRecords, getProductionPeriodBounds } from '../utils/productionAnalytics.js';
const shortDate = new Intl.DateTimeFormat('es-CO', { day: '2-digit', month: 'short', timeZone: 'UTC' });
const fullDate = new Intl.DateTimeFormat('es-CO', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });

function dateAtNoon(value) { return new Date(`${value}T12:00:00Z`); }
function formatDate(value, formatter = fullDate) { return formatter.format(dateAtNoon(value)); }

function periodLabel(period) {
  const bounds = getProductionPeriodBounds(period);
  if (period === 'week') return `Esta semana (${formatDate(bounds.from, shortDate)} - ${formatDate(bounds.to, shortDate)})`;
  if (period === '15days') return 'Últimos 15 días';
  return 'Este mes';
}

function PlusIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>; }

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
  const max = Math.max(...days.flatMap(([, values]) => [values.produced, values.sold]), 0);

  return <section className="production-card production-chart" aria-labelledby="production-chart-title">
    <div className="production-chart__header">
      <div><span className="production-eyebrow">BALANCE POR HORNADA</span><h2 id="production-chart-title">Unidades Producidas vs. Vendidas</h2></div>
      <div className="production-chart__legend"><span><i className="production-legend-dot" />Producido</span><span className="production-chart__sales-note">Vendido</span></div>
    </div>
    {days.length ? <div className="production-chart__plot" role="img" aria-label="Unidades producidas y ventas registradas por fecha; las ventas pueden corresponder a producto de jornadas anteriores">
      {days.map(([date, values]) => <div className="production-chart__day" key={date} title={`${formatDate(date)}: ${values.produced} producidas, ${values.sold} vendidas`}>
        <div className="production-chart__bar-area"><span className="production-chart__value">{values.produced} / {values.sold}</span><div className="production-chart__bars"><div className="production-chart__bar" style={{ height: `${values.produced ? Math.max(4, (values.produced / max) * 145) : 2}px` }} /><div className="production-chart__bar production-chart__bar--sales" style={{ height: `${values.sold ? Math.max(4, (values.sold / max) * 145) : 2}px` }} /></div></div>
        <span className="production-chart__date">{formatDate(date, shortDate)}</span>
      </div>)}
    </div> : <div className="production-chart__empty">Los registros de producción y ventas del período aparecerán aquí.</div>}
    <p className="production-data-note">Las ventas se muestran por su fecha de registro y no se asignan a una hornada específica; pueden incluir producto conservado de jornadas anteriores.</p>
  </section>;
}

function ProductionHistory({ records, sales }) {
  const productionByDateProduct = records.reduce((groups, record) => {
    const key = `${record.date}:${record.product}`;
    groups[key] ??= { id: key, date: record.date, product: record.product, quantity: 0, leftovers: 0 };
    groups[key].quantity += record.quantity;
    groups[key].leftovers += record.leftovers;
    return groups;
  }, {});
  const groupedProduction = Object.values(productionByDateProduct).sort((a, b) => b.date.localeCompare(a.date));
  const salesByDateProduct = sales.reduce((totals, sale) => {
    const key = `${sale.date}:${sale.product}`;
    totals[key] = (totals[key] ?? 0) + sale.quantity;
    return totals;
  }, {});
  return <section className="production-history production-card" aria-labelledby="production-history-title">
    <div className="production-history__ribbon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 11H5m14 0a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2m14 0V9a2 2 0 0 0-2-2M5 11V9a2 2 0 0 1 2-2m0 0V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2M7 7h10" /></svg><h2 id="production-history-title">HISTORIAL DE PRODUCCIÓN Y BALANCE DE VENTAS</h2></div>
    <div className="production-table-wrap"><table className="production-table">
      <thead><tr><th scope="col">Fecha y producto</th><th scope="col">Cant. producida</th><th scope="col">Ventas en fecha</th><th scope="col">Sobrantes / merma</th><th scope="col">Referencia</th></tr></thead>
      <tbody>{groupedProduction.length ? groupedProduction.map((record) => {
        const productLabel = PRODUCTION_PRODUCTS.find(({ value }) => value === record.product)?.label ?? 'Producto';
        const dateSales = salesByDateProduct[`${record.date}:${record.product}`] ?? 0;
        return <tr key={record.id}><td><strong>{productLabel}</strong><small>{formatDate(record.date)}</small></td><td>{record.quantity} uds</td><td title="Ventas registradas en esa fecha; pueden incluir existencias anteriores">{dateSales} uds<small className="production-unavailable">Fecha de venta, no lote</small></td><td>{record.leftovers} uds</td><td className="production-unavailable">No asignadas a una hornada</td></tr>;
      }) : <tr><td className="production-table__empty" colSpan="5">No hay registros de producción para los filtros seleccionados.</td></tr>}</tbody>
    </table></div>
  </section>;
}

export default function ProductionPage() {
  const { openMenu } = useOutletContext();
  const { records, error, create } = useProductionRecords();
  const { sales } = useSales();
  const [period, setPeriod] = useState('week');
  const [product, setProduct] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  const filtered = useMemo(() => filterProductionRecords(records, { period, product }), [records, period, product]);
  const filteredSales = useMemo(() => filterSales(sales, { period, product }), [sales, period, product]);
  const totals = useMemo(() => filtered.reduce((sum, record) => {
    sum.produced += record.quantity;
    sum.producedByProduct[record.product] = (sum.producedByProduct[record.product] ?? 0) + record.quantity;
    sum.leftovers[record.product] = (sum.leftovers[record.product] ?? 0) + record.leftovers;
    return sum;
  }, { produced: 0, producedByProduct: { lechona: 0, hayacas: 0 }, leftovers: { lechona: 0, hayacas: 0 } }), [filtered]);
  const sold = filteredSales.reduce((total, sale) => total + sale.quantity, 0);
  const salesEfficiency = totals.produced ? `${((sold / totals.produced) * 100).toFixed(1)}%` : '—';

  function announce(message, kind = 'success') {
    setToast({ message, kind });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3500);
  }

  function saveProduction(data) {
    try {
      create(data);
      setIsCreating(false);
      announce('La producción se registró correctamente.');
    } catch (saveError) {
      announce(saveError.message || 'No fue posible guardar el registro.', 'error');
    }
  }

  return <div className="production-page">
    <button className="orders-mobile-menu" type="button" aria-label="Abrir menú" onClick={openMenu}><span /><span /><span /></button>
    <PageHeader title="Producción y Análisis" description="Balance de unidades producidas vs. vendidas y análisis de rendimiento para toma de decisiones artesanales." actions={<Button onClick={() => setIsCreating(true)}><PlusIcon />Registrar producción</Button>} />

    <section className="production-metrics" aria-label="Indicadores de producción">
      <StatCard label="Total producido (período)" value={`${totals.produced} uds`} detail={<><span className="production-product-total production-product-total--hayacas">{totals.producedByProduct.hayacas} Hayacas</span><span className="production-product-total production-product-total--lechona">{totals.producedByProduct.lechona} Lechona</span></>} />
      <StatCard label="Total vendido" value={`${sold} uds`} detail="Según el registro compartido de Ventas" />
      <StatCard label="Unidades sobrantes" value={`${totals.leftovers.lechona} · ${totals.leftovers.hayacas}`} detail="Lechona · Hayacas" />
      <StatCard label="Eficiencia de producción" value={salesEfficiency} detail={totals.produced ? 'Ventas del período / producción del período' : 'Sin producción registrada en el período'} />
    </section>

    <div className="production-filters" aria-label="Filtros de producción">
      <div className="production-periods"><span>PERÍODO:</span>{[['week', periodLabel('week')], ['15days', 'Últimos 15 días'], ['month', periodLabel('month')]].map(([key, label]) => <button key={key} type="button" className={period === key ? 'is-active' : ''} aria-pressed={period === key} onClick={() => setPeriod(key)}>{label}</button>)}</div>
      <label className="production-product-filter"><span className="sr-only">Filtrar productos</span><select value={product} onChange={(event) => setProduct(event.target.value)}><option value="">Filtrar: Todos los productos</option>{PRODUCTION_PRODUCTS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}</select></label>
    </div>

    {error && <p className="orders-storage-error" role="alert">{error}</p>}
    <ProductionChart records={filtered} sales={filteredSales} />
    <ProductionHistory records={filtered} sales={filteredSales} />
    {isCreating && <ProductionFormModal onClose={() => setIsCreating(false)} onSave={saveProduction} />}
    {toast && <div className={`orders-toast${toast.kind === 'error' ? ' orders-toast--error' : ''}`} role="status" aria-live="polite">{toast.message}</div>}
  </div>;
}

