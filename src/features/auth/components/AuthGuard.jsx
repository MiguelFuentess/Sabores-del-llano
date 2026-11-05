import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import {
  fetchCurrentUser,
  hasAuthenticatedSession,
  subscribeAuthChanges,
} from '../services/authService.js';

export default function AuthGuard({ children }) {
  const location = useLocation();
  const [authenticated, setAuthenticated] = useState(() => hasAuthenticatedSession());

  useEffect(() => {
    const unsubscribe = subscribeAuthChanges(() => {
      setAuthenticated(hasAuthenticatedSession());
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!authenticated) return undefined;
    const controller = new AbortController();
    fetchCurrentUser({ signal: controller.signal }).catch(() => {
      setAuthenticated(hasAuthenticatedSession());
    });
    return () => controller.abort();
  }, [authenticated]);

  if (!authenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children;
}
