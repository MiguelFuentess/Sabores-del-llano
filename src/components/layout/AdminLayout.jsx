import { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar.jsx';

export default function AdminLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const isDashboard = pathname === '/app/dashboard';
  const hideTopbar = isDashboard || pathname === '/app/orders' || pathname === '/app/production' || pathname === '/app/sales' || pathname === '/app/demand';
  return <div className="admin-shell">
    <Sidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />
    <div className="admin-main">
      {!hideTopbar && <header className="topbar">
        <button className="menu-toggle" aria-label="Abrir menú" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><span /><span /><span /></button>
        <span className="topbar__context">Sabores del Llano <span aria-hidden="true">/</span> Administración</span>
        <div className="user-chip"><span className="user-chip__avatar">M</span><span><strong>Doña Martha</strong><small>Administradora</small></span></div>
      </header>}
      <main className="page-content"><Outlet context={{ openMenu: () => setMenuOpen(true) }} /></main>
    </div>
  </div>;
}
