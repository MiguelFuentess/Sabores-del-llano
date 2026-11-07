import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SalesPage from './SalesPage.jsx';
import useSales from '../hooks/useSales.js';
import { downloadSalesReport } from '../services/salesStorage.js';

vi.mock('../hooks/useSales.js', () => ({
  default: vi.fn(),
}));

vi.mock('../services/salesStorage.js', () => ({
  downloadSalesReport: vi.fn(),
}));

describe('SalesPage - Descarga de reporte Excel (.xlsx)', () => {
  const mockSales = [
    {
      id: 10,
      receiptNumber: 10,
      pedidoId: 4,
      date: '2026-10-31',
      time: '13:30',
      weekday: 'sáb',
      product: 'lechona',
      quantity: 12,
      unitPrice: 12000,
      total: 144000,
      estado: 'concretada',
      observations: 'Pedido familiar',
    },
    {
      id: 11,
      receiptNumber: 11,
      pedidoId: null,
      date: '2026-10-25',
      time: '',
      weekday: 'dom',
      product: 'hayacas',
      quantity: 30,
      unitPrice: 10000,
      total: 300000,
      estado: 'concretada',
      observations: '',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    useSales.mockReturnValue({
      sales: mockSales,
      error: '',
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    });
  });

  it('descarga el reporte Excel respetando los filtros aplicados de búsqueda, período y producto', async () => {
    downloadSalesReport.mockResolvedValue(
      'reporte_historial_ventas_hayacas_2026-11-06.xlsx'
    );

    render(
      <MemoryRouter>
        <SalesPage />
      </MemoryRouter>
    );

    // Aplicar filtro de producto y búsqueda
    fireEvent.change(screen.getByLabelText('Filtrar por producto'), {
      target: { value: 'hayacas' },
    });
    fireEvent.change(
      screen.getByLabelText('Buscar por producto, recibo o fecha'),
      { target: { value: '#011' } }
    );

    const downloadBtn = screen.getByRole('button', {
      name: /Descargar reporte/i,
    });
    expect(downloadBtn).not.toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(downloadBtn);

    await waitFor(() => {
      expect(downloadSalesReport).toHaveBeenCalledWith({
        search: '#011',
        period: 'all',
        product: 'hayacas',
      });
    });

    expect(
      await screen.findByText(
        /Reporte descargado: reporte_historial_ventas_hayacas_2026-11-06\.xlsx/i
      )
    ).toBeInTheDocument();
  });

  it('informa al usuario y evita descargar un archivo vacío cuando los filtros no arrojan ventas', async () => {
    render(
      <MemoryRouter>
        <SalesPage />
      </MemoryRouter>
    );

    fireEvent.change(
      screen.getByLabelText('Buscar por producto, recibo o fecha'),
      { target: { value: 'sin-coincidencias-xyz' } }
    );

    fireEvent.click(
      screen.getByRole('button', { name: /Descargar reporte/i })
    );

    expect(downloadSalesReport).not.toHaveBeenCalled();
    expect(
      await screen.findByText(
        /No hay ventas registradas para los filtros seleccionados/i
      )
    ).toBeInTheDocument();
  });
});
