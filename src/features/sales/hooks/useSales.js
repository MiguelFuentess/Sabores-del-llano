import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createSale,
  deleteSale,
  getSales,
  subscribeSales,
  updateSale,
} from '../services/salesStorage.js';

export default function useSales() {
  const [state, setState] = useState({
    sales: [],
    loading: true,
    error: '',
  });
  const requestIdRef = useRef(0);

  const reload = useCallback(async ({ signal } = {}) => {
    const currentRequestId = ++requestIdRef.current;
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const sales = await getSales({ signal });
      if (currentRequestId === requestIdRef.current) {
        setState({ sales, loading: false, error: '' });
      }
      return sales;
    } catch (err) {
      if (signal?.aborted) return [];
      if (currentRequestId === requestIdRef.current) {
        setState((prev) => ({
          ...prev,
          loading: false,
          error:
            err.message ||
            'No fue posible cargar las ventas desde el servidor.',
        }));
      }
      return [];
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    reload({ signal: controller.signal });
    const unsubscribe = subscribeSales(() => {
      reload();
    });
    return () => {
      controller.abort();
      unsubscribe();
    };
  }, [reload]);

  const create = useCallback(async (data) => {
    const createdSale = await createSale(data);
    setState((prev) => ({
      sales: [
        createdSale,
        ...prev.sales.filter((item) => item.id !== createdSale.id),
      ],
      loading: false,
      error: '',
    }));
    return createdSale;
  }, []);

  const update = useCallback(async (id, data) => {
    const updatedSale = await updateSale(id, data);
    setState((prev) => ({
      sales: prev.sales.map((item) => (item.id === id ? updatedSale : item)),
      loading: false,
      error: '',
    }));
    return updatedSale;
  }, []);

  const remove = useCallback(async (id) => {
    await deleteSale(id);
    setState((prev) => ({
      sales: prev.sales.filter((item) => item.id !== id),
      loading: false,
      error: '',
    }));
  }, []);

  return {
    sales: state.sales,
    loading: state.loading,
    error: state.error,
    create,
    update,
    remove,
    reload,
  };
}
