import { useCallback, useState } from 'react';
import { createProductionRecord, getProductionRecords } from '../services/productionStorage.js';

function load() {
  try { return { records: getProductionRecords(), error: '' }; }
  catch { return { records: [], error: 'No fue posible leer los registros de producción guardados en este navegador.' }; }
}

export default function useProductionRecords() {
  const [state, setState] = useState(load);
  const create = useCallback((data) => {
    const result = createProductionRecord(data);
    setState({ records: result.records, error: '' });
    return result.record;
  }, []);
  return { records: state.records, error: state.error, create };
}

