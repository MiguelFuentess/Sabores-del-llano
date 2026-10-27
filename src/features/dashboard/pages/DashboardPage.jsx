import { Link, useOutletContext } from 'react-router-dom';
import StatCard from '../../../components/ui/StatCard.jsx';
import useOrders from '../../orders/hooks/useOrders.js';
import { formatDeliveryDate, orderDescription } from '../../orders/utils/orderPresentation.js';
import { dashboardSales, summarizeSales } from '../data/dashboardData.js';

const currency = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });
const chartDays = ['Jue', 'Vie', 'Sáb', 'Dom'];
const chartMax = 3000000;
const chartBase = 224;
const chartHeight = 184;
const gridValues = [3000000, 2000000, 1000000, 500000, 0];

function compactCurrency(value) {
  if (value >= 1000000) return `$${(value / 1000000).toFixed(2).replace(/0$/, '').replace(/\.0$/, '')}M`;
  if (value >= 1000) return `$${Math.round(value / 1000)}k`;
  return '$0';
}

function SalesChart({ summary }) {
  const xForDay = (index) => 146 + index * 190;
  const yForValue = (value) => chartBase - (value / chartMax) * chartHeight;

  return <section className="dashboard-card dashboard-chart" aria-labelledby="sales-chart-title">
    <div className="dashboard-card__header dashboard-chart__header">
      <div className="dashboard-card__title"><svg className="dashboard-icon dashboard-icon--filled" viewBox="0 0 24 24" aria-hidden="true"><rect height="11" rx="1" width="4" x="3" y="10"/><rect height="17" rx="1" width="4" x="10" y="4"/><rect height="8" rx="1" width="4" x="17" y="13"/></svg><h3 id="sales-chart-title">Ventas por Días</h3></div>
      <div className="dashboard-chart__legend" aria-label="Productos">
        <span><i className="legend-dot legend-dot--lechona"/>Lechona Tolimense</span>
        <span><i className="legend-dot legend-dot--hayacas"/>Hayacas Campesinas</span>
      </div>
    </div>
    <div className="dashboard-chart__canvas">
      <svg viewBox="0 0 900 286" role="img" aria-labelledby="chart-title chart-description">
        <title id="chart-title">Ventas de lechona y hayacas de jueves a domingo</title>
        <desc id="chart-description">Gráfico de barras agrupadas. Los valores provienen de los datos de demostración del panel.</desc>
        {gridValues.map((value) => {
          const y = yForValue(value);
          return <g key={value}>
            <text className="chart-axis-label" x="57" y={y + 4} textAnchor="end">{compactCurrency(value)}</text>
            <line className={value === 0 ? 'chart-grid chart-grid--baseline' : 'chart-grid'} x1="76" y1={y} x2="880" y2={y} />
          </g>;
        })}
        {chartDays.map((day, index) => {
          const values = summary.byDay[day] ?? { lechona: 0, hayacas: 0 };
          const center = xForDay(index);
          return <g key={day}>
            {[{ key: 'lechona', x: center - 27, fill: '#9f321d' }, { key: 'hayacas', x: center + 5, fill: '#2d5a3d' }].map(({ key, x, fill }) => {
              const value = values[key];
              const height = value === 0 ? 3 : Math.max((value / chartMax) * chartHeight, 3);
              const y = chartBase - height;
              return <g key={key}>
                <title>{`${day} · ${key === 'lechona' ? 'Lechona Tolimense' : 'Hayacas Campesinas'}: ${currency.format(value)}`}</title>
                <text className="chart-value-label" x={x + 11} y={y - 7} textAnchor="middle" fill={fill}>{compactCurrency(value)}</text>
                <rect x={x} y={y} width="22" height={height} rx="3" fill={fill} />
              </g>;
            })}
            <text className={`chart-day-label${day === 'Sáb' || day === 'Dom' ? ' chart-day-label--peak' : ''}`} x={center - 2} y="266" textAnchor="middle">{day}{day === 'Sáb' || day === 'Dom' ? ' ★' : ''}</text>
          </g>;
        })}
      </svg>
    </div>
  </section>;
}

function formatOrderSchedule(order) {
  const date = formatDeliveryDate(order.deliveryDate);
  if (!order.deliveryTime) return date;
  const [hour, minute] = order.deliveryTime.split(':').map(Number);
  const time = new Intl.DateTimeFormat('es-CO', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'UTC' }).format(new Date(Date.UTC(2026, 0, 1, hour, minute)));
  return `${date} - ${time}`;
}

function RecentOrders({ orders, totalOrders }) {
  return <section className="dashboard-card dashboard-orders" aria-labelledby="recent-orders-title">
    <div className="dashboard-card__header dashboard-orders__header">
      <div className="dashboard-card__title"><svg className="dashboard-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6M9 15h4"/></svg><h3 id="recent-orders-title">Últimos Pedidos</h3></div>
      <span className="dashboard-orders__priority">{orders.length} pedidos prioritarios</span>
    </div>
    <div className="dashboard-orders__table-wrap">
      <table className="dashboard-orders__table">
        <thead><tr><th scope="col">Cliente</th><th scope="col">Pedido solicitado</th><th scope="col">Modalidad</th><th scope="col">Hora de entrega / retiro</th></tr></thead>
        <tbody>{orders.length ? orders.map((order) => <tr key={order.id}>
          <td className="dashboard-orders__customer">{order.customer}</td>
          <td>{orderDescription(order)}</td>
          <td className="dashboard-orders__delivery">{order.deliveryMode === 'domicilio' ? `Domicilio${order.address ? ` • ${order.address}` : ''}` : 'Retiro en Local'}</td>
          <td className="dashboard-orders__schedule">{formatOrderSchedule(order)}</td>
        </tr>) : <tr><td colSpan="4" className="dashboard-orders__empty">No hay pedidos recientes.</td></tr>}</tbody>
      </table>
    </div>
    <footer className="dashboard-orders__footer"><span>Mostrando {orders.length} de {totalOrders} pedidos programados para la fecha</span><Link to="/app/orders">Ver todos los pedidos <span aria-hidden="true">→</span></Link></footer>
  </section>;
}

export default function DashboardPage() {
  const { openMenu } = useOutletContext();
  const { orders } = useOrders();
  const summary = summarizeSales(dashboardSales);
  const recentOrders = [...orders].sort((a, b) => b.registeredDate.localeCompare(a.registeredDate) || b.orderNumber.localeCompare(a.orderNumber)).slice(0, 5);
  return <div className="dashboard-page">
    <button className="dashboard-mobile-menu" type="button" aria-label="Abrir menú" onClick={openMenu}><span/><span/><span/></button>
    <header className="dashboard-welcome">
      <h1>¡Buenos días, Doña Martha!</h1>
      <p>Resumen general de producción, pedidos y entregas del día</p>
    </header>
    <section className="dashboard-stats" aria-label="Indicadores del panel">
      <StatCard label="Ventas registradas" value={currency.format(summary.total)} detail="COP" />
      <StatCard label="Pedidos registrados" value={orders.length} detail="pedidos" />
      <StatCard label="Lechona vendida" value={summary.quantity.lechona ?? 0} detail="porciones" />
      <StatCard label="Hayacas vendidas" value={summary.quantity.hayacas ?? 0} detail="unidades" />
    </section>
    <SalesChart summary={summary} />
    <RecentOrders orders={recentOrders} totalOrders={orders.length} />
  </div>;
}


