import { useCallback, useEffect, useState } from 'react';
import { createSale, deleteSale, getSales, subscribeSales, updateSale } from '../services/salesStorage.js';

function loadSales() {
  try { return { sales: getSales(), error: '' }; }
  catch { return { sales: [], error: 'No fue posible leer las ventas guardadas en este navegador.' }; }
}

export default function useSales() {
  const [state, setState] = useState(loadSales);
  const reload = useCallback(() => setState(loadSales()), []);
  useEffect(() => subscribeSales(reload), [reload]);

  const create = useCallback((data) => {
    const result = createSale(data);
    setState({ sales: result.sales, error: '' });
    return result.sale;
  }, []);
  const update = useCallback((id, data) => {
    const result = updateSale(id, data);
    setState({ sales: result.sales, error: '' });
    return result.sale;
  }, []);
  const remove = useCallback((id) => {
    const sales = deleteSale(id);
    setState({ sales, error: '' });
  }, []);

  return { sales: state.sales, error: state.error, create, update, remove, reload };
}

