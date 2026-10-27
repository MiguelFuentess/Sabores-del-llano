import { Navigate, createBrowserRouter } from 'react-router-dom';
import AdminLayout from '../components/layout/AdminLayout.jsx';
import PlaceholderPage from '../components/ui/PlaceholderPage.jsx';
import LoginPage from '../features/auth/pages/LoginPage.jsx';
import DemoAccessGuard from '../features/auth/components/DemoAccessGuard.jsx';
import DashboardPage from '../features/dashboard/pages/DashboardPage.jsx';
import OrdersPage from '../features/orders/pages/OrdersPage.jsx';
import ProductionPage from '../features/production/pages/ProductionPage.jsx';
import SalesPage from '../features/sales/pages/SalesPage.jsx';
import DemandPage from '../features/demand/pages/DemandPage.jsx';
import PublicHomePage from '../features/public/pages/PublicHomePage.jsx';

const adminPages = [
];

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/public" replace /> },
  { path: '/app', element: <DemoAccessGuard><AdminLayout /></DemoAccessGuard>, children: [
    { index: true, element: <Navigate to="dashboard" replace /> },
    { path: 'dashboard', element: <DashboardPage /> },
    { path: 'orders', element: <OrdersPage /> },
    { path: 'production', element: <ProductionPage /> },
    { path: 'sales', element: <SalesPage /> },
    { path: 'demand', element: <DemandPage /> },
    ...adminPages.map(({ path, ...page }) => ({ path, element: <PlaceholderPage {...page} /> })),
  ] },
  { path: '/login', element: <LoginPage /> },
  { path: '/public', element: <PublicHomePage /> },
  { path: '*', element: <Navigate to="/public" replace /> },
]);

