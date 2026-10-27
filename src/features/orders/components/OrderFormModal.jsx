import { Children, cloneElement, Fragment, isValidElement, useEffect, useState } from 'react';
import Button from '../../../components/ui/Button.jsx';
import { ORDER_PRODUCTS, ORDER_STATUSES } from '../data/orderOptions.js';
import { validateOrderData } from '../utils/validateOrderData.js';

function localDate(offsetDays = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function freshOrderForm() {
  return { customer: '', product: '', quantity: '', registeredDate: localDate(), deliveryDate: localDate(1), deliveryTime: '', deliveryMode: 'retiro', address: '', observations: '', status: 'Pendiente' };
}

function IconClose() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>;
}

function FieldError({ id, children }) {
  return children ? <p className="order-field-error" id={id} role="alert">{children}</p> : null;
}

function addFieldAccessibility(child, fieldId, labelId, errorId, hasError) {
  if (!isValidElement(child)) return child;
  if (child.type === Fragment) {
    return cloneElement(child, {}, Children.map(child.props.children, (nested) => addFieldAccessibility(nested, fieldId, labelId, errorId, hasError)));
  }
  if (child.type === 'input' || child.type === 'select' || child.type === 'textarea') {
    return cloneElement(child, {
      id: child.props.id ?? fieldId,
      'aria-labelledby': labelId,
      'aria-describedby': hasError ? errorId : undefined,
      'aria-invalid': Boolean(hasError),
    });
  }
  if (child.props.role === 'group') return cloneElement(child, { id: fieldId, 'aria-labelledby': labelId, 'aria-describedby': hasError ? errorId : undefined });
  return child;
}

function LabeledField({ label, required = false, error, children }) {
  const fieldId = `order-field-${label.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')}`;
  const labelId = `${fieldId}-label`;
  const errorId = `${fieldId}-error`;
  return <div className="order-form-field">
    <label id={labelId} htmlFor={fieldId}>{label}{required && <span className="order-required"> *</span>}</label>
    {Children.map(children, (child) => addFieldAccessibility(child, fieldId, labelId, errorId, Boolean(error)))}
    <FieldError id={errorId}>{error}</FieldError>
  </div>;
}

export default function OrderFormModal({ order, customers, onClose, onSave }) {
  const isEdit = Boolean(order);
  const [form, setForm] = useState(() => order ? { ...order, quantity: String(order.quantity) } : freshOrderForm());
  const [addingClient, setAddingClient] = useState(false);
  const [errors, setErrors] = useState({});

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  function updateField(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: '' }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    const nextErrors = validateOrderData(form, { isNew: !isEdit, addingClient });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    onSave({
      ...form,
      customer: form.customer.trim(),
      quantity: Number(form.quantity),
      address: form.deliveryMode === 'domicilio' ? form.address.trim() : '',
      observations: form.observations.trim(),
    });
  }

  return <div className="orders-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={`orders-modal${isEdit ? ' orders-modal--edit' : ''}`} role="dialog" aria-modal="true" aria-labelledby="order-modal-title">
      <header className="orders-modal__header">
        <div><h2 id="order-modal-title">{isEdit ? 'Modificar pedido' : 'Nuevo pedido'}</h2><p>{isEdit ? `Pedido #${order.orderNumber} · ${order.customer}` : 'Ingresa los datos para registrar un nuevo pedido.'}</p></div>
        <button className="orders-modal__close" type="button" onClick={onClose} aria-label="Cerrar"><IconClose /></button>
      </header>
      <form className="order-form" onSubmit={handleSubmit} noValidate>
        {!isEdit && <LabeledField label="Cliente" required error={!addingClient && !customers.length && errors.customer ? 'No hay clientes registrados. Registra uno nuevo.' : errors.customer}>
          {!addingClient ? <>
            <select className="order-control" value={form.customer} onChange={(event) => updateField('customer', event.target.value)}>
              <option value="">Seleccionar cliente...</option>
              {customers.map((customer) => <option value={customer} key={customer}>{customer}</option>)}
            </select>
            <button className="order-add-client" type="button" onClick={() => { setAddingClient(true); updateField('customer', ''); }}>+ Registrar nuevo cliente si no existe</button>
          </> : <>
            <input className="order-control" value={form.customer} onChange={(event) => updateField('customer', event.target.value)} placeholder="Nombre del nuevo cliente" autoComplete="name" />
            <button className="order-add-client" type="button" onClick={() => { setAddingClient(false); updateField('customer', ''); }}>Seleccionar cliente existente</button>
          </>}
        </LabeledField>}

        <div className="order-form-grid">
          <LabeledField label="Producto" required error={errors.product}>
            <select className="order-control" value={form.product} onChange={(event) => updateField('product', event.target.value)}>
              <option value="">Seleccionar producto...</option>
              {ORDER_PRODUCTS.map((product) => <option key={product.value} value={product.value}>{product.label}</option>)}
            </select>
          </LabeledField>
          <LabeledField label="Cantidad" required error={errors.quantity}>
            <input className="order-control" type="number" min="1" step="1" inputMode="numeric" value={form.quantity} onChange={(event) => updateField('quantity', event.target.value)} placeholder="Ej. 12" />
          </LabeledField>
        </div>

        <div className="order-form-grid">
          <LabeledField label="Fecha de entrega" required error={errors.deliveryDate}>
            <input className="order-control" type="date" min={form.registeredDate} value={form.deliveryDate} onChange={(event) => updateField('deliveryDate', event.target.value)} />
          </LabeledField>
          <LabeledField label="Hora de entrega" error={errors.deliveryTime}>
            <input className="order-control" type="time" value={form.deliveryTime} onChange={(event) => updateField('deliveryTime', event.target.value)} />
          </LabeledField>
        </div>

        <LabeledField label="Modalidad de entrega" required error={errors.deliveryMode}>
          <div className="order-delivery-toggle" role="group" aria-label="Modalidad de entrega">
            {[['retiro', 'Retiro en local'], ['domicilio', 'Domicilio']].map(([value, label]) => <button key={value} type="button" className={form.deliveryMode === value ? 'order-delivery-toggle__option is-active' : 'order-delivery-toggle__option'} aria-pressed={form.deliveryMode === value} onClick={() => updateField('deliveryMode', value)}>{label}</button>)}
          </div>
        </LabeledField>

        {form.deliveryMode === 'domicilio' && <LabeledField label="Dirección de entrega" required error={errors.address}>
          <input className="order-control" value={form.address} onChange={(event) => updateField('address', event.target.value)} placeholder="Dirección para el domicilio" autoComplete="street-address" />
        </LabeledField>}

        {!isEdit && <LabeledField label="Observaciones" error={errors.observations}>
          <textarea className="order-control order-control--textarea" value={form.observations} onChange={(event) => updateField('observations', event.target.value)} placeholder="Indicaciones adicionales del pedido..." />
        </LabeledField>}

        <LabeledField label="Estado" required error={errors.status}>
          <select className="order-control" value={form.status} onChange={(event) => updateField('status', event.target.value)}>
            {ORDER_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
          </select>
        </LabeledField>

        <footer className="order-form__footer">
          <Button variant="quiet" onClick={onClose}>Cancelar</Button>
          <Button type="submit">{isEdit ? 'Guardar cambios' : 'Guardar pedido'}</Button>
        </footer>
      </form>
    </section>
  </div>;
}
