import { useEffect, useMemo, useState } from 'react';
import Button from '../../../components/ui/Button.jsx';
import { getDefaultUnitPrice, SALE_PRODUCTS } from '../data/salesOptions.js';
import { calculateSaleTotal } from '../utils/saleCalculations.js';
import { formatCOP } from '../utils/filterSales.js';
import { validateSale } from '../utils/validateSale.js';
import useOrders from '../../orders/hooks/useOrders.js';

function localDateTime() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function CloseIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>; }

function mapOrderToSaleProduct(order) {
  const detail = Array.isArray(order.detalles) && order.detalles.length > 0 ? order.detalles[0] : null;
  const prodName = String(detail?.producto_nombre ?? order.product ?? '').toLowerCase();
  if (prodName.includes('hayaca')) {
    return 'hayacas';
  }
  return 'lechona';
}

function extractOrderQuantity(order) {
  const detail = Array.isArray(order.detalles) && order.detalles.length > 0 ? order.detalles[0] : null;
  const rawQty = detail?.cantidad ?? order.quantity ?? 1;
  return String(Math.round(Number(rawQty)));
}

function extractOrderUnitPrice(order, saleProduct) {
  const detail = Array.isArray(order.detalles) && order.detalles.length > 0 ? order.detalles[0] : null;
  if (detail?.precio_unitario && Number(detail.precio_unitario) > 0) {
    return String(Math.round(Number(detail.precio_unitario)));
  }
  return String(getDefaultUnitPrice(saleProduct));
}

export default function SaleFormModal({ sale, onClose, onSave }) {
  const isEdit = Boolean(sale);
  const initialProduct = sale?.product ?? 'lechona';
  const [form, setForm] = useState(() => ({
    dateTime: sale ? `${sale.date}T${sale.time || '12:00'}` : localDateTime(),
    product: initialProduct,
    quantity: sale ? String(sale.quantity) : '',
    unitPrice: sale ? String(sale.unitPrice) : String(getDefaultUnitPrice(initialProduct)),
  }));
  const [selectedOrderId, setSelectedOrderId] = useState(() => (sale?.pedidoId ? String(sale.pedidoId) : ''));
  const [errors, setErrors] = useState({});
  const [saveError, setSaveError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const { orders, loading: loadingOrders } = useOrders({ soloOperativos: true });

  const eligibleOrders = useMemo(() => {
    return orders.filter(
      (order) =>
        !order.esHistorico &&
        order.status !== 'Entregado' &&
        order.status !== 'Cancelado'
    );
  }, [orders]);

  const selectedOrder = useMemo(() => {
    if (!selectedOrderId) return null;
    return (
      eligibleOrders.find((o) => String(o.id) === String(selectedOrderId)) ||
      (sale?.pedidoId && String(sale.pedidoId) === String(selectedOrderId)
        ? orders.find((o) => String(o.id) === String(selectedOrderId)) || null
        : null)
    );
  }, [selectedOrderId, eligibleOrders, orders, sale]);

  const hasMultipleDetails = Boolean(
    selectedOrder &&
    Array.isArray(selectedOrder.detalles) &&
    selectedOrder.detalles.length > 1
  );

  const [date = '', time = ''] = form.dateTime.split('T');
  const total = calculateSaleTotal(form.quantity, form.unitPrice);

  useEffect(() => {
    function onKeyDown(event) { if (event.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  function change(name, value) {
    setForm((current) => {
      if (name === 'product') {
        const previousDefault = String(getDefaultUnitPrice(current.product));
        const shouldUpdatePrice =
          !current.unitPrice || current.unitPrice === previousDefault;
        return {
          ...current,
          product: value,
          unitPrice: shouldUpdatePrice
            ? String(getDefaultUnitPrice(value))
            : current.unitPrice,
        };
      }
      return { ...current, [name]: value };
    });
    setErrors((current) => ({ ...current, [name === 'dateTime' ? 'date' : name]: '' }));
    setSaveError('');
  }

  function handleOrderSelectChange(event) {
    const orderId = event.target.value;
    setSelectedOrderId(orderId);
    setSaveError('');
    if (!orderId) {
      return;
    }
    const order = eligibleOrders.find((o) => String(o.id) === String(orderId));
    if (!order) return;

    if (Array.isArray(order.detalles) && order.detalles.length > 1) {
      return;
    }

    const mappedProd = mapOrderToSaleProduct(order);
    const qty = extractOrderQuantity(order);
    const unitPrice = extractOrderUnitPrice(order, mappedProd);

    setForm((current) => ({
      ...current,
      product: mappedProd,
      quantity: qty,
      unitPrice,
    }));
    setErrors({});
  }

  function handleClearOrder() {
    setSelectedOrderId('');
    setSaveError('');
  }

  async function submit(event) {
    event.preventDefault();
    setSaveError('');
    const nextErrors = validateSale({
      date,
      time,
      product: form.product,
      quantity: form.quantity,
      unitPrice: form.unitPrice,
    });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    if (hasMultipleDetails) return;

    setIsSaving(true);
    try {
      await onSave({
        date,
        time,
        product: form.product,
        quantity: Number(form.quantity),
        unitPrice: Number(form.unitPrice),
        pedidoId: selectedOrderId ? Number(selectedOrderId) : undefined,
      });
    } catch (err) {
      setSaveError(err.message || 'No fue posible guardar la venta.');
      setIsSaving(false);
    }
  }

  return <div className="orders-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="orders-modal sales-form-modal" role="dialog" aria-modal="true" aria-labelledby="sale-modal-title">
      <header className="orders-modal__header sales-form-modal__header">
        <div>
          <h2 id="sale-modal-title">{isEdit ? 'Modificar venta' : 'Registrar venta'}</h2>
          <p>{isEdit ? `Venta #${String(sale.receiptNumber).padStart(3, '0')}` : 'Ingresa los datos de la operación de venta realizada.'}</p>
        </div>
        <button className="orders-modal__close" type="button" aria-label="Cerrar modal" onClick={onClose}><CloseIcon /></button>
      </header>
      <form className="sales-form" onSubmit={submit} noValidate>
        {isEdit && sale?.pedidoId ? (
          <div className="sales-linked-badge">
            Venta vinculada al Pedido #{sale.pedidoId}
          </div>
        ) : !isEdit ? (
          <div className="sales-field sales-order-selector-field">
            <label htmlFor="sale-order-select">
              ¿Asociar a un pedido pendiente? <small style={{ fontWeight: 400, color: '#888' }}>(opcional)</small>
            </label>
            {loadingOrders ? (
              <div className="sales-order-loading">Cargando pedidos pendientes...</div>
            ) : eligibleOrders.length === 0 ? (
              <p className="sales-order-empty-hint">
                No hay pedidos pendientes disponibles para asociar.
              </p>
            ) : (
              <select
                id="sale-order-select"
                className="sales-control"
                value={selectedOrderId}
                onChange={handleOrderSelectChange}
              >
                <option value="">Venta directa (sin pedido asociado)</option>
                {eligibleOrders.map((o) => (
                  <option key={o.id} value={o.id}>
                    Pedido #{o.orderNumber} — {o.customer} ({o.deliveryDate || o.registeredDate})
                  </option>
                ))}
              </select>
            )}

            {selectedOrder && !hasMultipleDetails && (
              <div className="sales-order-preview">
                <div>
                  <strong>Pedido #{selectedOrder.orderNumber}</strong> · {selectedOrder.customer}
                  <small style={{ display: 'block', color: '#686057', marginTop: '2px' }}>
                    Entrega: {selectedOrder.deliveryDate || 'Hoy'} ({selectedOrder.deliveryMode === 'domicilio' ? 'Domicilio' : 'Retiro en local'})
                  </small>
                </div>
                <button
                  type="button"
                  className="sales-order-clear-btn"
                  onClick={handleClearOrder}
                  title="Desvincular pedido"
                >
                  Limpiar selección
                </button>
              </div>
            )}

            {hasMultipleDetails && (
              <div className="sales-order-warning" role="alert">
                <strong>⚠️ Pedido con múltiples productos:</strong>
                <p style={{ margin: '4px 0 0' }}>
                  El pedido #{selectedOrder.orderNumber} contiene {selectedOrder.detalles.length} productos (
                  {selectedOrder.detalles.map((d) => `${Math.round(d.cantidad)} ${d.producto_nombre}`).join(', ')}
                  ). El formulario actual registra una línea de producto. Para registrarlo sin omitir productos, desvincula el pedido y gestiona cada producto individualmente.
                </p>
                <button
                  type="button"
                  className="sales-order-clear-btn"
                  style={{ marginTop: '6px', display: 'inline-block' }}
                  onClick={handleClearOrder}
                >
                  Desvincular pedido
                </button>
              </div>
            )}
          </div>
        ) : null}

        <div className="sales-field">
          <label htmlFor="sale-date">Fecha <span>*</span></label>
          <input id="sale-date" className="sales-control" type="datetime-local" value={form.dateTime} onChange={(event) => change('dateTime', event.target.value)} aria-invalid={Boolean(errors.date)} aria-describedby={errors.date ? 'sale-date-error' : undefined} />
          {errors.date && <p id="sale-date-error" className="sales-field__error" role="alert">{errors.date}</p>}
          {errors.time && <p className="sales-field__error" role="alert">{errors.time}</p>}
        </div>
        <div className="sales-field">
          <span className="sales-field__label" id="sale-product-label">Producto <span>*</span></span>
          <div className="sales-product-toggle" role="group" aria-labelledby="sale-product-label">
            {SALE_PRODUCTS.map(({ value }) => <button key={value} type="button" className={form.product === value ? 'is-active' : ''} aria-pressed={form.product === value} onClick={() => change('product', value)}>{value === 'hayacas' ? 'Hayaca' : 'Lechona'}</button>)}
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

        {saveError && (
          <p className="sales-field__error" role="alert" style={{ fontSize: '11px', marginTop: '2px' }}>
            {saveError}
          </p>
        )}

        <footer className="sales-form__actions">
          <Button variant="quiet" onClick={onClose} disabled={isSaving}>Cancelar</Button>
          <Button type="submit" disabled={isSaving || Boolean(hasMultipleDetails)}>
            {isSaving ? 'Guardando...' : (isEdit ? 'Guardar cambios' : 'Guardar venta')}
          </Button>
        </footer>
      </form>
    </section>
  </div>;
}
