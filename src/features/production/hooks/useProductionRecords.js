import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createProductionRecord,
  deleteProductionRecord,
  getProductionRecords,
  subscribeProductionRecords,
  updateProductionRecord,
} from '../services/productionStorage.js';

export default function useProductionRecords() {
  const [state, setState] = useState({
    records: [],
    loading: true,
    error: '',
  });
  const requestIdRef = useRef(0);

  const reload = useCallback(async ({ signal } = {}) => {
    const currentRequestId = ++requestIdRef.current;
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const records = await getProductionRecords({ signal });
      if (currentRequestId === requestIdRef.current) {
        setState({ records, loading: false, error: '' });
      }
      return records;
    } catch (err) {
      if (signal?.aborted) return [];
      if (currentRequestId === requestIdRef.current) {
        setState((prev) => ({
          ...prev,
          loading: false,
          error:
            err.message ||
            'No fue posible cargar los registros de producción desde el servidor.',
        }));
      }
      return [];
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    reload({ signal: controller.signal });
    const unsubscribe = subscribeProductionRecords(() => {
      reload();
    });
    return () => {
      controller.abort();
      unsubscribe();
    };
  }, [reload]);

  const create = useCallback(async (data) => {
    const createdRecord = await createProductionRecord(data);
    setState((prev) => ({
      records: [
        createdRecord,
        ...prev.records.filter((item) => item.id !== createdRecord.id),
      ],
      loading: false,
      error: '',
    }));
    return createdRecord;
  }, []);

  const update = useCallback(async (id, data) => {
    const updatedRecord = await updateProductionRecord(id, data);
    setState((prev) => ({
      records: prev.records.map((item) =>
        item.id === id ? updatedRecord : item
      ),
      loading: false,
      error: '',
    }));
    return updatedRecord;
  }, []);

  const remove = useCallback(async (id) => {
    await deleteProductionRecord(id);
    setState((prev) => ({
      records: prev.records.filter((item) => item.id !== id),
      loading: false,
      error: '',
    }));
  }, []);

  return {
    records: state.records,
    loading: state.loading,
    error: state.error,
    create,
    update,
    remove,
    reload,
  };
}
