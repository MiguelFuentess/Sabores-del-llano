import { NavLink, useNavigate } from 'react-router-dom';
import { clearDemoAccess } from '../../features/auth/demoAccess.js';

const links = [
  { to: '/app/dashboard', label: 'Panel de Control', icon: 'dashboard' },
  { to: '/app/orders', label: 'Pedidos', icon: 'orders' },
  { to: '/app/production', label: 'Producción y análisis', icon: 'production' },
  { to: '/app/sales', label: 'Ventas', icon: 'sales' },
  { to: '/app/demand', label: 'Predicción de demanda', icon: 'demand' },
];

function NavIcon({ name }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', viewBox: '0 0 24 24', 'aria-hidden': true };
  const icons = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></>,
    orders: <><path d="M16 2H6a2 2 0 0 0-2 2v16l2.5-1.5L9 20l2.5-1.5L14 20l2.5-1.5L19 20V4a2 2 0 0 0-2-2Z"/><path d="M8 7h7M8 11h7M8 15h5"/></>,
    production: <><path d="M4 11h16a1 1 0 0 1 1 1v1a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5v-1a1 1 0 0 1 1-1Z"/><path d="m6 18-2 3m14-3 2 3M7 8c1-1.5 1-3 0-4m5 4c1-1.5 1-3 0-4m5 4c1-1.5 1-3 0-4"/></>,
    sales: <><path d="M5 7h14a1 1 0 0 1 1 1v1H4V8a1 1 0 0 1 1-1Z"/><rect x="7" y="4" width="10" height="3" rx="1"/><path d="m4 9-1 9a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1l-1-9"/><path d="M2 21h20"/><circle cx="8" cy="13" r=".7"/><circle cx="12" cy="13" r=".7"/><circle cx="16" cy="13" r=".7"/></>,
    demand: <><path d="M16 11c1.5 0 3-1.2 3-3a3 3 0 0 0-4-2.8A3.5 3.5 0 0 0 8 7c0 .5.1 1 .3 1.5A3 3 0 0 0 6 11c0 1.2.7 2.2 1.7 2.7C7.3 14.5 7 15.7 7 17a3 3 0 0 0 3 3h5"/><circle cx="12" cy="11" r="2"/><path d="M12 8.5v1m0 3v1m-2.5-2.5H11m2 0h1"/></>,
  };
  return <svg className="nav-link__icon" {...common}>{icons[name]}</svg>;
}

export default function Sidebar({ open, onNavigate }) {
  const navigate = useNavigate();

  function handleLogout(event) {
    event.preventDefault();
    clearDemoAccess();
    onNavigate();
    navigate('/login', { replace: true });
  }

  return <>
    {open && <button className="sidebar-scrim" aria-label="Cerrar menú" onClick={onNavigate} />}
    <aside className={`sidebar ${open ? 'sidebar--open' : ''}`}>
      <div>
        <NavLink className="brand" to="/app/dashboard" onClick={onNavigate}>
          <span className="brand__mark" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none"><path d="M14 18c2-4 7-6 11-4-2 3-5 5-11 4Zm9-4c4 0 7 3 8 7-3-1-6-3-8-7Z" fill="#397334"/><path d="M11 25h26c0 0-1.5 12-13 12S11 25 11 25Z" fill="#9d4c2b" stroke="#692b15" strokeWidth="1.2"/><ellipse cx="24" cy="25" rx="13" ry="3" fill="#b85d38" stroke="#692b15" strokeWidth="1"/><ellipse cx="24" cy="25" rx="9" ry="1.8" fill="#d2834b"/><path d="M18 36.5h12V38H18z" fill="#7a3219"/></svg></span>
          <span><strong>Sabores del llano</strong><small>TRADICIÓN CULINARIA</small></span>
        </NavLink>
        <nav className="sidebar__nav" aria-label="Menú principal">
          {links.map(({ to, label, icon }) => <NavLink key={to} to={to} onClick={onNavigate} className={({ isActive }) => `nav-link${isActive ? ' nav-link--active' : ''}`}>
            <NavIcon name={icon}/><span>{label}</span>
          </NavLink>)}
        </nav>
      </div>
      <div className="sidebar__footer"><a className="nav-link nav-link--logout" href="/login" onClick={handleLogout}><svg className="nav-link__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5m5 5H9"/></svg><span>Cerrar Sesión</span></a></div>
    </aside>
  </>;
}
