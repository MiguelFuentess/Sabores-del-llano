import Button from '../../../components/ui/Button.jsx';

function SearchIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>;
}

export default function OrdersFilters({ search, onSearch, status, onStatus, product, onProduct, date, onDate, onClear }) {
  const hasFilters = Boolean(search || status || product || date);
  return <section className="orders-filter-card" aria-label="Buscar y filtrar pedidos">
    <div className="orders-search">
      <SearchIcon />
      <input type="search" value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Buscar por cliente o número de pedido..." aria-label="Buscar por cliente o número de pedido" />
    </div>
    <div className="orders-filter-divider" />
    <div className="orders-filter-row">
      <label className="orders-filter-select"><span className="sr-only">Filtrar por estado</span><select value={status} onChange={(event) => onStatus(event.target.value)}><option value="">Todos los estados</option><option>Pendiente</option><option>Confirmado</option><option>En preparación</option><option>Entregado</option></select></label>
      <label className="orders-filter-select"><span className="sr-only">Filtrar por producto</span><select value={product} onChange={(event) => onProduct(event.target.value)}><option value="">Todos los productos</option><option value="hayacas">Hayacas</option><option value="lechona">Lechona</option></select></label>
      <label className={`orders-filter-date${date ? ' has-value' : ''}`}><span>Fecha</span><input type="date" value={date} onChange={(event) => onDate(event.target.value)} aria-label="Filtrar por fecha de entrega" /></label>
      {hasFilters && <button className="orders-filter-clear" type="button" onClick={onClear}>Limpiar filtros</button>}
    </div>
  </section>;
}
