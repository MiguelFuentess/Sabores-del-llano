import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from './DashboardPage.jsx';
import useOrders from '../../orders/hooks/useOrders.js';
import useSales from '../../sales/hooks/useSales.js';

vi.mock('../../orders/hooks/useOrders.js', () => ({
  default: vi.fn(),
}));

vi.mock('../../sales/hooks/useSales.js', () => ({
  default: vi.fn(),
}));

describe('DashboardPage - Filtro por mes y año', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockSales = [
    {
      id: 1,
      receiptNumber: '001',
      date: '2026-10-03',
      product: 'lechona',
      quantity: 10,
      unitPrice: 15000,
      total: 150000,
      detalles: [
        { producto_nombre: 'Lechona', cantidad: 10, precio_unitario: 15000, subtotal: 150000 },
      ],
    },
    {
      id: 2,
      receiptNumber: '002',
      date: '2026-10-10',
      product: 'hayacas',
      quantity: 5,
      unitPrice: 10000,
      total: 50000,
      detalles: [
        { producto_nombre: 'Hayaca', cantidad: 5, precio_unitario: 10000, subtotal: 50000 },
      ],
    },
    {
      id: 3,
      receiptNumber: '003',
      date: '2026-09-15', // Septiembre de 2026
      product: 'lechona',
      quantity: 20,
      unitPrice: 15000,
      total: 300000,
      detalles: [
        { producto_nombre: 'Lechona', cantidad: 20, precio_unitario: 15000, subtotal: 300000 },
      ],
    },
    {
      id: 4,
      receiptNumber: '004',
      date: '2025-10-12', // Octubre pero de 2025
      product: 'hayacas',
      quantity: 15,
      unitPrice: 10000,
      total: 150000,
      detalles: [
        { producto_nombre: 'Hayaca', cantidad: 15, precio_unitario: 10000, subtotal: 150000 },
      ],
    },
  ];

  const mockOrders = [
    {
      id: 101,
      orderNumber: '101',
      customer: 'Carlos Pérez',
      product: 'lechona',
      quantity: 2,
      registeredDate: '2026-10-05',
      deliveryDate: '2026-10-07',
      deliveryTime: '13:00',
      deliveryMode: 'retiro',
      status: 'Pendiente',
    },
    {
      id: 102,
      orderNumber: '102',
      customer: 'María Gómez',
      product: 'hayacas',
      quantity: 6,
      registeredDate: '2026-09-20', // Septiembre
      deliveryDate: '2026-09-22',
      deliveryTime: '10:00',
      deliveryMode: 'domicilio',
      address: 'Calle 10 # 5-20',
      status: 'Entregado',
    },
    {
      id: 103,
      orderNumber: '103',
      customer: 'Lucía Santos',
      product: 'lechona',
      quantity: 4,
      registeredDate: '2025-10-25', // Octubre 2025
      deliveryDate: '2025-10-26',
      deliveryTime: '11:00',
      deliveryMode: 'retiro',
      status: 'Entregado',
    },
  ];

  it('al ingresar al módulo aparece seleccionado octubre de 2026 por defecto', () => {
    useOrders.mockReturnValue({ orders: [] });
    useSales.mockReturnValue({ sales: [] });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    const monthSelect = screen.getByLabelText('Seleccionar mes');
    const yearSelect = screen.getByLabelText('Seleccionar año');

    expect(monthSelect).toHaveValue('10');
    expect(yearSelect).toHaveValue('2026');
  });

  it('las cuatro tarjetas muestran exclusivamente los datos de octubre de 2026', () => {
    useOrders.mockReturnValue({ orders: mockOrders });
    useSales.mockReturnValue({ sales: mockSales });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    // Ventas registradas de octubre 2026: $150.000 + $50.000 = $200.000
    const ventasCard = screen.getByText('Ventas registradas').closest('.stat-card');
    expect(ventasCard).toHaveTextContent('$ 200.000');

    // Pedidos registrados de octubre 2026: solo el pedido 101
    const pedidosCard = screen.getByText('Pedidos registrados').closest('.stat-card');
    expect(pedidosCard).toHaveTextContent('1');

    // Lechona vendida en octubre 2026: 10 porciones
    const lechonaCard = screen.getByText('Lechona vendida').closest('.stat-card');
    expect(lechonaCard).toHaveTextContent('10');

    // Hayacas vendidas en octubre 2026: 5 unidades
    const hayacasCard = screen.getByText('Hayacas vendidas').closest('.stat-card');
    expect(hayacasCard).toHaveTextContent('5');
  });

  it('la gráfica muestra el título dinámico de octubre de 2026 y renderiza los días del mes', () => {
    useOrders.mockReturnValue({ orders: mockOrders });
    useSales.mockReturnValue({ sales: mockSales });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    const chartTitle = screen.getByRole('heading', { level: 3, name: /ventas por días del mes/i });
    expect(chartTitle).toHaveTextContent('Ventas por días del mes de octubre de 2026');

    // Debe mostrar los 31 días de octubre en el eje horizontal dentro de la gráfica
    const chart = document.querySelector('.dashboard-chart');
    expect(chart).toBeInTheDocument();
    expect(screen.getByText('31')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
  });

  it('al seleccionar otro mes y año, las tarjetas y la gráfica se actualizan correctamente', () => {
    useOrders.mockReturnValue({ orders: mockOrders });
    useSales.mockReturnValue({ sales: mockSales });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    const monthSelect = screen.getByLabelText('Seleccionar mes');
    fireEvent.change(monthSelect, { target: { value: '9' } }); // Septiembre 2026

    // Título de la gráfica actualizado a septiembre de 2026
    const chartTitle = screen.getByRole('heading', { level: 3, name: /ventas por días del mes/i });
    expect(chartTitle).toHaveTextContent('Ventas por días del mes de septiembre de 2026');

    // Tarjetas de septiembre 2026:
    // Venta: $300.000, Pedidos: 1, Lechona: 20, Hayacas: 0
    const ventasCard = screen.getByText('Ventas registradas').closest('.stat-card');
    expect(ventasCard).toHaveTextContent('$ 300.000');

    const pedidosCard = screen.getByText('Pedidos registrados').closest('.stat-card');
    expect(pedidosCard).toHaveTextContent('1');

    const lechonaCard = screen.getByText('Lechona vendida').closest('.stat-card');
    expect(lechonaCard).toHaveTextContent('20');

    const hayacasCard = screen.getByText('Hayacas vendidas').closest('.stat-card');
    expect(hayacasCard).toHaveTextContent('0');

    // Cambiar a un periodo sin información (ej: Enero 2026)
    fireEvent.change(monthSelect, { target: { value: '1' } });
    expect(ventasCard).toHaveTextContent('$ 0');
    expect(pedidosCard).toHaveTextContent('0');
    expect(lechonaCard).toHaveTextContent('0');
    expect(hayacasCard).toHaveTextContent('0');
  });

  it('evita duplicaciones cuando una venta contiene múltiples detalles', () => {
    const multiDetailSales = [
      {
        id: 10,
        date: '2026-10-18',
        total: 175000,
        detalles: [
          { producto_nombre: 'Lechona', cantidad: 5, precio_unitario: 15000, subtotal: 75000 },
          { producto_nombre: 'Hayaca', cantidad: 10, precio_unitario: 10000, subtotal: 100000 },
        ],
      },
    ];

    useOrders.mockReturnValue({ orders: [] });
    useSales.mockReturnValue({ sales: multiDetailSales });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    const ventasCard = screen.getByText('Ventas registradas').closest('.stat-card');
    expect(ventasCard).toHaveTextContent('$ 175.000');

    const lechonaCard = screen.getByText('Lechona vendida').closest('.stat-card');
    expect(lechonaCard).toHaveTextContent('5');

    const hayacasCard = screen.getByText('Hayacas vendidas').closest('.stat-card');
    expect(hayacasCard).toHaveTextContent('10');
  });

  it('la sección de Últimos Pedidos no se ve afectada por el filtro de mes y año', () => {
    useOrders.mockReturnValue({ orders: mockOrders });
    useSales.mockReturnValue({ sales: mockSales });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    // Cambiar el filtro a un mes sin pedidos (ej: Febrero)
    const monthSelect = screen.getByLabelText('Seleccionar mes');
    fireEvent.change(monthSelect, { target: { value: '2' } });

    // Últimos pedidos sigue mostrando todos los pedidos prioritarios (incluyendo los de sept/oct)
    expect(screen.getByText('Carlos Pérez')).toBeInTheDocument();
    expect(screen.getByText('María Gómez')).toBeInTheDocument();
    expect(screen.getByText('Lucía Santos')).toBeInTheDocument();
    expect(screen.getByText(/3 pedidos prioritarios/i)).toBeInTheDocument();
  });
});
