import { useEffect, useState } from 'react';
import Button from '../../../components/ui/Button.jsx';
import { PRODUCTION_PRODUCTS } from '../data/productionOptions.js';
import { validateProductionRecord } from '../utils/validateProductionRecord.js';

function today() {
  const date = new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function CloseIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>;
}

export default function ProductionFormModal({ onClose, onSave }) {
  const [form, setForm] = useState({ date: today(), product: 'lechona', quantity: '', leftovers: '' });
  const [errors, setErrors] = useState({});

  useEffect(() => {
    function onKeyDown(event) { if (event.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  function change(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: '' }));
  }

  function submit(event) {
    event.preventDefault();
    const nextErrors = validateProductionRecord(form);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    onSave({ date: form.date, product: form.product, quantity: Number(form.quantity), leftovers: Number(form.leftovers || 0) });
  }

  return <div className="orders-modal-backdrop production-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="orders-modal production-modal" role="dialog" aria-modal="true" aria-labelledby="production-modal-title">
      <header className="orders-modal__header production-modal__header">
        <div><h2 id="production-modal-title">Registrar producción</h2><p>Ingresa los datos de la jornada de producción.</p></div>
        <button className="orders-modal__close" type="button" onClick={onClose} aria-label="Cerrar modal"><CloseIcon /></button>
      </header>
      <form className="production-form" onSubmit={submit} noValidate>
        <div className="production-field">
          <label htmlFor="production-date">Fecha <span>*</span></label>
          <input id="production-date" className="production-control" type="date" value={form.date} onChange={(event) => change('date', event.target.value)} aria-invalid={Boolean(errors.date)} aria-describedby={errors.date ? 'production-date-error' : undefined} />
          {errors.date && <p id="production-date-error" className="production-field__error" role="alert">{errors.date}</p>}
        </div>
        <div className="production-field">
          <span className="production-field__label" id="production-product-label">Producto <span>*</span></span>
          <div className="production-product-toggle" role="group" aria-labelledby="production-product-label">
            {PRODUCTION_PRODUCTS.map(({ value, label }) => <button key={value} type="button" className={form.product === value ? 'is-active' : ''} aria-pressed={form.product === value} onClick={() => change('product', value)}>{value === 'lechona' ? 'Lechona' : 'Hayaca'}</button>)}
          </div>
          {errors.product && <p className="production-field__error" role="alert">{errors.product}</p>}
        </div>
        <div className="production-form__quantities">
          <div className="production-field">
            <label htmlFor="production-quantity">Cantidad producida <span>*</span></label>
            <input id="production-quantity" className="production-control" type="number" min="1" step="1" inputMode="numeric" placeholder="Ej. 80" value={form.quantity} onChange={(event) => change('quantity', event.target.value)} aria-invalid={Boolean(errors.quantity)} aria-describedby={errors.quantity ? 'production-quantity-error' : undefined} />
            {errors.quantity && <p id="production-quantity-error" className="production-field__error" role="alert">{errors.quantity}</p>}
          </div>
          <div className="production-field">
            <label htmlFor="production-leftovers">Sobrantes registrados</label>
            <input id="production-leftovers" className="production-control" type="number" min="0" step="1" inputMode="numeric" placeholder="0" value={form.leftovers} onChange={(event) => change('leftovers', event.target.value)} aria-invalid={Boolean(errors.leftovers)} aria-describedby={errors.leftovers ? 'production-leftovers-error' : 'production-leftovers-hint'} />
            {errors.leftovers ? <p id="production-leftovers-error" className="production-field__error" role="alert">{errors.leftovers}</p> : <p id="production-leftovers-hint" className="production-field__hint">Dato independiente; no se calcula con las ventas.</p>}
          </div>
        </div>
        <footer className="production-form__actions">
          <Button variant="quiet" onClick={onClose}>Cancelar</Button>
          <Button type="submit">Guardar registro</Button>
        </footer>
      </form>
    </section>
  </div>;
}

