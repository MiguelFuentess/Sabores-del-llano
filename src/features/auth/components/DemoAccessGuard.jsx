import { Navigate, useLocation } from 'react-router-dom';
import { hasDemoAccess } from '../demoAccess.js';

export default function DemoAccessGuard({ children }) {
  const location = useLocation();
  if (!hasDemoAccess()) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children;
}
