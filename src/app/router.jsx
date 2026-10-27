import { Navigate, createBrowserRouter } from 'react-router-dom';
import AdminLayout from '../components/layout/AdminLayout.jsx';
import PlaceholderPage from '../components/ui/PlaceholderPage.jsx';
import LoginPage from '../features/auth/pages/LoginPage.jsx';
import DemoAccessGuard from '../features/auth/components/DemoAccessGuard.jsx';
import DashboardPage from '../features/dashboard/pages/DashboardPage.jsx';
import OrdersPage from '../features/orders/pages/OrdersPage.jsx';

const adminPages = [
  { path: 'production', title: 'Producción y análisis', description: 'Seguimiento de producción y análisis.' },
  { path: 'sales', title: 'Ventas', description: 'Registro y consulta de ventas.' },
  { path: 'demand', title: 'Predicción de demanda', description: 'Estimación de demanda.' },
];

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/public" replace /> },
  { path: '/app', element: <DemoAccessGuard><AdminLayout /></DemoAccessGuard>, children: [
    { index: true, element: <Navigate to="dashboard" replace /> },
    { path: 'dashboard', element: <DashboardPage /> },
    { path: 'orders', element: <OrdersPage /> },
    ...adminPages.map(({ path, ...page }) => ({ path, element: <PlaceholderPage {...page} /> })),
  ] },
  { path: '/login', element: <LoginPage /> },
  { path: '/public', element: <PlaceholderPage title="Sabores del Llano" description="Portada pública pendiente de implementación." /> },
  { path: '*', element: <Navigate to="/public" replace /> },
]);

