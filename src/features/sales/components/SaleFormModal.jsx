import { useEffect, useState } from 'react';
import Button from '../../../components/ui/Button.jsx';
import { SALE_PRODUCTS } from '../data/salesOptions.js';
import { calculateSaleTotal } from '../utils/saleCalculations.js';
import { formatCOP } from '../utils/filterSales.js';
import { validateSale } from '../utils/validateSale.js';

function localDateTime() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function CloseIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>; }

export default function SaleFormModal({ sale, onClose, onSave }) {
  const isEdit = Boolean(sale);
  const [form, setForm] = useState(() => ({
    dateTime: sale ? `${sale.date}T${sale.time}` : localDateTime(),
    product: sale?.product ?? 'lechona',
    quantity: sale ? String(sale.quantity) : '',
    unitPrice: sale ? String(sale.unitPrice) : '',
  }));
  const [errors, setErrors] = useState({});
  const [date = '', time = ''] = form.dateTime.split('T');
  const total = calculateSaleTotal(form.quantity, form.unitPrice);

  useEffect(() => {
    function onKeyDown(event) { if (event.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  function change(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name === 'dateTime' ? 'date' : name]: '' }));
  }

  function submit(event) {
    event.preventDefault();
    const nextErrors = validateSale({ date, time, product: form.product, quantity: form.quantity, unitPrice: form.unitPrice });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    onSave({ date, time, product: form.product, quantity: Number(form.quantity), unitPrice: Number(form.unitPrice) });
  }

  return <div className="orders-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="orders-modal sales-form-modal" role="dialog" aria-modal="true" aria-labelledby="sale-modal-title">
      <header className="orders-modal__header sales-form-modal__header">
        <div><h2 id="sale-modal-title">{isEdit ? 'Modificar venta' : 'Registrar venta'}</h2><p>{isEdit ? `Venta #${String(sale.receiptNumber).padStart(3, '0')}` : 'Ingresa los datos de la operación de venta realizada.'}</p></div>
        <button className="orders-modal__close" type="button" aria-label="Cerrar modal" onClick={onClose}><CloseIcon /></button>
      </header>
      <form className="sales-form" onSubmit={submit} noValidate>
        <div className="sales-field">
          <label htmlFor="sale-date">Fecha <span>*</span></label>
          <input id="sale-date" className="sales-control" type="datetime-local" value={form.dateTime} onChange={(event) => change('dateTime', event.target.value)} aria-invalid={Boolean(errors.date)} aria-describedby={errors.date ? 'sale-date-error' : undefined} />
          {errors.date && <p id="sale-date-error" className="sales-field__error" role="alert">{errors.date}</p>}
          {errors.time && <p className="sales-field__error" role="alert">{errors.time}</p>}
        </div>
        <div className="sales-field">
          <span className="sales-field__label" id="sale-product-label">Producto <span>*</span></span>
          <div className="sales-product-toggle" role="group" aria-labelledby="sale-product-label">
            {SALE_PRODUCTS.map(({ value, shortLabel }) => <button key={value} type="button" className={form.product === value ? 'is-active' : ''} aria-pressed={form.product === value} onClick={() => change('product', value)}>{value === 'hayacas' ? 'Hayaca' : 'Lechona'}</button>)}
          </div>
          {errors.product && <p className="sales-field__error" role="alert">{errors.product}</p>}
        </div>
        <div className="sales-form__columns">
          <div className="sales-field">
            <label htmlFor="sale-quantity">Cantidad vendida <span>*</span></label>
            <input id="sale-quantity" className="sales-control" type="number" min="1" step="1" inputMode="numeric" placeholder="Ej. 4" value={form.quantity} onChange={(event) => change('quantity', event.target.value)} aria-invalid={Boolean(errors.quantity)} aria-describedby={errors.quantity ? 'sale-quantity-error' : undefined} />
            {errors.quantity && <p id="sale-quantity-error" className="sales-field__error" role="alert">{errors.quantity}</p>}
          </div>
          <div className="sales-field">
            <label htmlFor="sale-unit-price">Precio unitario <span>*</span></label>
            <input id="sale-unit-price" className="sales-control" type="number" min="1" step="1" inputMode="numeric" placeholder="$ 0" value={form.unitPrice} onChange={(event) => change('unitPrice', event.target.value)} aria-invalid={Boolean(errors.unitPrice)} aria-describedby={errors.unitPrice ? 'sale-unit-price-error' : undefined} />
            {errors.unitPrice && <p id="sale-unit-price-error" className="sales-field__error" role="alert">{errors.unitPrice}</p>}
          </div>
        </div>
        <div className="sales-total"><span>Total a cobrar:</span><strong>{formatCOP(total)}</strong></div>
        <footer className="sales-form__actions">
          <Button variant="quiet" onClick={onClose}>Cancelar</Button>
          <Button type="submit">{isEdit ? 'Guardar cambios' : 'Guardar venta'}</Button>
        </footer>
      </form>
    </section>
  </div>;
}

