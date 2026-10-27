import { useCallback, useState } from 'react';
import { createOrder, deleteOrder, getOrders, updateOrder } from '../services/ordersStorage.js';

function loadState() {
  try { return { orders: getOrders(), error: '' }; }
  catch { return { orders: [], error: 'No fue posible leer los pedidos guardados en este navegador.' }; }
}

export default function useOrders() {
  const [state, setState] = useState(loadState);

  const create = useCallback((data) => {
    const result = createOrder(data);
    setState({ orders: result.orders, error: '' });
    return result.order;
  }, []);

  const update = useCallback((id, data) => {
    const result = updateOrder(id, data);
    setState({ orders: result.orders, error: '' });
    return result.order;
  }, []);

  const remove = useCallback((id) => {
    const orders = deleteOrder(id);
    setState({ orders, error: '' });
  }, []);

  const reload = useCallback(() => setState(loadState()), []);

  return { orders: state.orders, error: state.error, create, update, remove, reload };
}
