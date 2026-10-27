import { validateProductionRecord } from '../utils/validateProductionRecord.js';

const STORAGE_KEY = 'sabores-del-llano-production-v1';

function save(records) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
  return records;
}

export function getProductionRecords() {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === null) return save([]);
  const records = JSON.parse(stored);
  if (!Array.isArray(records)) throw new Error('Los registros de producción guardados no tienen un formato válido.');
  return records;
}

export function createProductionRecord(data) {
  const errors = validateProductionRecord({ ...data, quantity: String(data.quantity), leftovers: String(data.leftovers ?? 0) });
  if (Object.keys(errors).length) throw new Error('Revisa la fecha, el producto, la cantidad producida y los sobrantes antes de guardar.');
  const records = getProductionRecords();
  const record = {
    ...data,
    id: globalThis.crypto?.randomUUID?.() ?? `production-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    createdAt: new Date().toISOString(),
    source: 'user',
  };
  return { record, records: save([...records, record]) };
}

