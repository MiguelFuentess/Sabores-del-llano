import { useEffect, useState } from 'react';
import Button from '../../../components/ui/Button.jsx';
import { PRODUCTION_PRODUCTS } from '../data/productionOptions.js';
import { validateProductionRecord } from '../utils/validateProductionRecord.js';

function today() {
  const date = new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

export default function ProductionFormModal({ onClose, onSave, record }) {
  const isEditing = Boolean(record);
  const [form, setForm] = useState(() => ({
    date: record?.date || today(),
    product: record?.product || 'lechona',
    quantity: record?.quantity !== undefined ? String(record.quantity) : '',
    leftovers: record?.leftovers !== undefined ? String(record.leftovers) : '',
  }));
  const [errors, setErrors] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  const [serverError, setServerError] = useState('');

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === 'Escape' && !isSaving) onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, isSaving]);

  function change(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: '' }));
    setServerError('');
  }

  async function submit(event) {
    event.preventDefault();
    const nextErrors = validateProductionRecord(form);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    setIsSaving(true);
    setServerError('');
    try {
      await onSave({
        date: form.date,
        product: form.product,
        quantity: Number(form.quantity),
        leftovers: Number(form.leftovers || 0),
      });
    } catch (saveError) {
      setServerError(
        saveError.message || 'No fue posible guardar la producción.'
      );
    } finally {
      setIsSaving(false);
    }
  }

  const unitLabel = form.product === 'hayacas' ? 'Unidad' : 'Plato';
  const unitPlural = form.product === 'hayacas' ? 'unidades' : 'platos';

  return (
    <div
      className="orders-modal-backdrop production-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSaving) onClose();
      }}
    >
      <section
        className="orders-modal production-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="production-modal-title"
      >
        <header className="orders-modal__header production-modal__header">
          <div>
            <h2 id="production-modal-title">
              {isEditing ? 'Editar producción' : 'Registrar producción'}
            </h2>
            <p>
              {isEditing
                ? 'Modifica los datos de la jornada de producción seleccionada.'
                : 'Ingresa los datos de la jornada de producción.'}
            </p>
          </div>
          <button
            className="orders-modal__close"
            type="button"
            onClick={onClose}
            aria-label="Cerrar modal"
            disabled={isSaving}
          >
            <CloseIcon />
          </button>
        </header>

        <form className="production-form" onSubmit={submit} noValidate>
          {serverError && (
            <div
              className="orders-storage-error"
              role="alert"
              style={{ marginBottom: '4px' }}
            >
              {serverError}
            </div>
          )}

          <div className="production-field">
            <label htmlFor="production-date">
              Fecha <span>*</span>
            </label>
            <input
              id="production-date"
              className="production-control"
              type="date"
              value={form.date}
              onChange={(event) => change('date', event.target.value)}
              aria-invalid={Boolean(errors.date)}
              aria-describedby={errors.date ? 'production-date-error' : undefined}
              disabled={isSaving}
            />
            {errors.date && (
              <p
                id="production-date-error"
                className="production-field__error"
                role="alert"
              >
                {errors.date}
              </p>
            )}
          </div>

          <div className="production-field">
            <span
              className="production-field__label"
              id="production-product-label"
            >
              Producto <span>*</span>
            </span>
            {isEditing ? (
              <div className="production-product-fixed">
                <strong>
                  {form.product === 'hayacas'
                    ? 'Hayaca (Unidad)'
                    : 'Lechona (Plato)'}
                </strong>
                <small
                  className="production-field__hint"
                  style={{ display: 'block', marginTop: '4px' }}
                >
                  El producto está asociado al lote y no puede modificarse en la edición.
                </small>
              </div>
            ) : (
              <div
                className="production-product-toggle"
                role="group"
                aria-labelledby="production-product-label"
              >
                {PRODUCTION_PRODUCTS.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    className={form.product === value ? 'is-active' : ''}
                    aria-pressed={form.product === value}
                    onClick={() => change('product', value)}
                    disabled={isSaving}
                  >
                    {value === 'lechona' ? 'Lechona' : 'Hayaca'}
                  </button>
                ))}
              </div>
            )}
            {errors.product && (
              <p className="production-field__error" role="alert">
                {errors.product}
              </p>
            )}
          </div>

          <div className="production-form__quantities">
            <div className="production-field">
              <label htmlFor="production-quantity">
                Cantidad producida ({unitLabel}) <span>*</span>
              </label>
              <input
                id="production-quantity"
                className="production-control"
                type="number"
                min="1"
                step="1"
                inputMode="numeric"
                placeholder={
                  form.product === 'hayacas' ? 'Ej. 80 uds' : 'Ej. 40 platos'
                }
                value={form.quantity}
                onChange={(event) => change('quantity', event.target.value)}
                aria-invalid={Boolean(errors.quantity)}
                aria-describedby={
                  errors.quantity ? 'production-quantity-error' : undefined
                }
                disabled={isSaving}
              />
              {errors.quantity && (
                <p
                  id="production-quantity-error"
                  className="production-field__error"
                  role="alert"
                >
                  {errors.quantity}
                </p>
              )}
            </div>

            <div className="production-field">
              <label htmlFor="production-leftovers">
                Sobrantes registrados ({unitLabel})
              </label>
              <input
                id="production-leftovers"
                className="production-control"
                type="number"
                min="0"
                step="1"
                inputMode="numeric"
                placeholder="0"
                value={form.leftovers}
                onChange={(event) => change('leftovers', event.target.value)}
                aria-invalid={Boolean(errors.leftovers)}
                aria-describedby={
                  errors.leftovers
                    ? 'production-leftovers-error'
                    : 'production-leftovers-hint'
                }
                disabled={isSaving}
              />
              {errors.leftovers ? (
                <p
                  id="production-leftovers-error"
                  className="production-field__error"
                  role="alert"
                >
                  {errors.leftovers}
                </p>
              ) : (
                <p
                  id="production-leftovers-hint"
                  className="production-field__hint"
                >
                  Registrado en {unitPlural}; no se calcula automáticamente con las ventas.
                </p>
              )}
            </div>
          </div>

          <footer className="production-form__actions">
            <Button variant="quiet" onClick={onClose} disabled={isSaving}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving
                ? 'Guardando...'
                : isEditing
                ? 'Guardar cambios'
                : 'Guardar registro'}
            </Button>
          </footer>
        </form>
      </section>
    </div>
  );
}
