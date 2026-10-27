import { SALE_PRODUCTS } from '../data/salesOptions.js';

function SearchIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>; }

export default function SalesFilters({ search, onSearch, period, onPeriod, product, onProduct }) {
  return <section className="sales-filters" aria-label="Buscador y filtros de ventas">
    <div className="sales-search"><SearchIcon /><input type="search" value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Buscar por producto, recibo o fecha..." aria-label="Buscar por producto, recibo o fecha" /></div>
    <label className="sales-filter"><span>Período:</span><select value={period} onChange={(event) => onPeriod(event.target.value)} aria-label="Filtrar por período"><option value="week">Esta semana</option><option value="15days">Últimos 15 días</option><option value="month">Este mes</option></select></label>
    <label className="sales-filter"><span>Producto:</span><select value={product} onChange={(event) => onProduct(event.target.value)} aria-label="Filtrar por producto"><option value="">Todos los productos</option>{SALE_PRODUCTS.map(({ value, shortLabel }) => <option key={value} value={value}>{shortLabel}</option>)}</select></label>
  </section>;
}

