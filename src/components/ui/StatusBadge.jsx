const tones = { Pendiente: 'pending', Confirmado: 'confirmed', 'En preparación': 'preparing', Preparando: 'preparing', Entregado: 'delivered', Cancelado: 'danger', Pagado: 'success' };

export default function StatusBadge({ children, tone }) {
  const variant = tone || tones[children] || 'neutral';
  return <span className={`status-badge status-badge--${variant}`}>{children}</span>;
}
