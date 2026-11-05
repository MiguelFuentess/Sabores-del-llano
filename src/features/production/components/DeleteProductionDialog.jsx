import { useEffect } from 'react';
import Button from '../../../components/ui/Button.jsx';
import { PRODUCTION_PRODUCTS } from '../data/productionOptions.js';

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16M10 11v6m4-6v6M5 7l1 14h12l1-14M9 7V4h6v3" />
    </svg>
  );
}

export default function DeleteProductionDialog({
  record,
  onCancel,
  onConfirm,
  isDeleting = false,
}) {
  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === 'Escape' && !isDeleting) onCancel();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onCancel, isDeleting]);

  if (!record) return null;

  const productLabel =
    PRODUCTION_PRODUCTS.find(({ value }) => value === record.product)?.label ??
    (record.product === 'hayacas' ? 'Hayacas' : 'Lechona');
  const unitLabel =
    record.baseUnit || (record.product === 'hayacas' ? 'unidades' : 'platos');

  return (
    <div
      className="orders-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isDeleting) onCancel();
      }}
    >
      <section
        className="orders-confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-prod-title"
        aria-describedby="delete-prod-description"
      >
        <h2 id="delete-prod-title">¿Eliminar registro de producción?</h2>
        <p id="delete-prod-description">
          Se eliminará permanentemente la producción de{' '}
          <strong>{productLabel}</strong> del{' '}
          <strong>{record.date}</strong> ({record.quantity} {unitLabel}). Esta
          acción actualizará los movimientos de inventario y el balance de la
          jornada.
        </p>
        <div className="orders-confirm-dialog__actions">
          <Button variant="quiet" onClick={onCancel} disabled={isDeleting}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={isDeleting}>
            <TrashIcon />
            {isDeleting ? 'Eliminando...' : 'Eliminar producción'}
          </Button>
        </div>
      </section>
    </div>
  );
}
