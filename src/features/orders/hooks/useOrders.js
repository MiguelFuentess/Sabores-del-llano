import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createOrder,
  deleteOrder,
  getOrders,
  updateOrder,
} from '../services/ordersStorage.js';

export default function useOrders() {
  const [state, setState] = useState({
    orders: [],
    loading: true,
    error: '',
  });
  const requestIdRef = useRef(0);

  const reload = useCallback(async ({ signal } = {}) => {
    const currentRequestId = ++requestIdRef.current;
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const orders = await getOrders({ signal });
      if (currentRequestId === requestIdRef.current) {
        setState({ orders, loading: false, error: '' });
      }
      return orders;
    } catch (err) {
      if (signal?.aborted) return [];
      if (currentRequestId === requestIdRef.current) {
        setState((prev) => ({
          ...prev,
          loading: false,
          error: err.message || 'No fue posible cargar los pedidos desde el servidor.',
        }));
      }
      return [];
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    reload({ signal: controller.signal });
    return () => controller.abort();
  }, [reload]);

  const create = useCallback(async (data) => {
    const createdOrder = await createOrder(data);
    setState((prev) => ({
      orders: [createdOrder, ...prev.orders.filter((item) => item.id !== createdOrder.id)],
      loading: false,
      error: '',
    }));
    return createdOrder;
  }, []);

  const update = useCallback(async (id, data) => {
    const updatedOrder = await updateOrder(id, data);
    setState((prev) => ({
      orders: prev.orders.map((item) => (item.id === id ? updatedOrder : item)),
      loading: false,
      error: '',
    }));
    return updatedOrder;
  }, []);

  const remove = useCallback(async (id) => {
    await deleteOrder(id);
    setState((prev) => ({
      orders: prev.orders.filter((item) => item.id !== id),
      loading: false,
      error: '',
    }));
  }, []);

  return {
    orders: state.orders,
    loading: state.loading,
    error: state.error,
    create,
    update,
    remove,
    reload,
  };
}
