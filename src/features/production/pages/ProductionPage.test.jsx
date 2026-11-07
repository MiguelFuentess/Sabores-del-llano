import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProductionPage from './ProductionPage.jsx';
import useProductionRecords from '../hooks/useProductionRecords.js';
import { downloadProductionReport } from '../services/productionStorage.js';
import useSales from '../../sales/hooks/useSales.js';

vi.mock('../hooks/useProductionRecords.js', () => ({
  default: vi.fn(),
}));

vi.mock('../services/productionStorage.js', () => ({
  downloadProductionReport: vi.fn(),
}));

vi.mock('../../sales/hooks/useSales.js', () => ({
  default: vi.fn(),
}));

describe('ProductionPage - Periodo predeterminado y paginación', () => {
  const generateMockRecords = (count) => {
    return Array.from({ length: count }, (_, i) => {
      const day = String((i % 28) + 1).padStart(2, '0');
      return {
        id: i + 1,
        date: `2026-10-${day}`,
        product: i % 2 === 0 ? 'lechona' : 'hayacas',
        quantity: 50,
        soldQuantity: 40,
        leftovers: 10,
        baseUnit: i % 2 === 0 ? 'Plato' : 'Unidad',
        esHistorico: false,
        origenRegistro: 'operativo',
      };
    });
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useSales.mockReturnValue({ sales: [] });
  });

  it('inicia con el periodo "Últimos 15 días" predeterminado y sin paginación', () => {
    const records = generateMockRecords(25);
    useProductionRecords.mockReturnValue({
      records,
      error: '',
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    });

    render(
      <MemoryRouter>
        <ProductionPage />
      </MemoryRouter>
    );

    const btn15Days = screen.getByRole('button', { name: 'Últimos 15 días' });
    expect(btn15Days).toHaveAttribute('aria-pressed', 'true');
    expect(btn15Days).toHaveClass('is-active');

    // La paginación NO debe aparecer en el periodo de 15 días
    expect(screen.queryByLabelText('Paginación de producción')).not.toBeInTheDocument();
  });

  it('al seleccionar "Todo el historial" muestra máximo 15 registros y activa la paginación', () => {
    const records = generateMockRecords(35);
    useProductionRecords.mockReturnValue({
      records,
      error: '',
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    });

    render(
      <MemoryRouter>
        <ProductionPage />
      </MemoryRouter>
    );

    // Cambiar a "Todo el historial"
    const btnAll = screen.getByRole('button', { name: 'Todo el historial' });
    fireEvent.click(btnAll);

    expect(btnAll).toHaveAttribute('aria-pressed', 'true');

    // La paginación debe estar presente
    const paginationNav = screen.getByLabelText('Paginación de producción');
    expect(paginationNav).toBeInTheDocument();

    // Debe indicar Página 1 de 3 con 35 registros en total
    expect(
      screen.getByText(/Mostrando/i)
    ).toHaveTextContent('Mostrando 1–15 de 35 registros de producción (35 en total · Página 1 de 3)');

    // Filas en la tabla: exactamente 15 registros
    const rows = screen.getAllByRole('row');
    // 1 fila thead + 15 filas tbody = 16 filas en total
    expect(rows.length).toBe(16);
  });

  it('permite navegar entre páginas y reinicia a la página 1 al cambiar de periodo', () => {
    const records = generateMockRecords(35);
    useProductionRecords.mockReturnValue({
      records,
      error: '',
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    });

    render(
      <MemoryRouter>
        <ProductionPage />
      </MemoryRouter>
    );

    // Cambiar a "Todo el historial"
    fireEvent.click(screen.getByRole('button', { name: 'Todo el historial' }));

    // Avanzar a la página 2 con el botón siguiente
    const nextBtn = screen.getByRole('button', { name: 'Página siguiente' });
    fireEvent.click(nextBtn);

    expect(
      screen.getByText(/Mostrando/i)
    ).toHaveTextContent('Mostrando 16–30 de 35 registros de producción (35 en total · Página 2 de 3)');

    // Cambiar a "Últimos 15 días" y volver a "Todo el historial"
    fireEvent.click(screen.getByRole('button', { name: 'Últimos 15 días' }));
    expect(screen.queryByLabelText('Paginación de producción')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Todo el historial' }));
    // Debe haber vuelto a la página 1
    expect(
      screen.getByText(/Mostrando/i)
    ).toHaveTextContent('Mostrando 1–15 de 35 registros de producción (35 en total · Página 1 de 3)');
  });

  it('habilita acciones de editar y eliminar para registros históricos', () => {
    const historicalRecord = {
      id: 99,
      date: '2026-10-15',
      product: 'hayacas',
      quantity: 100,
      soldQuantity: 80,
      leftovers: 20,
      baseUnit: 'Unidad',
      esHistorico: true,
      origenRegistro: 'historico_excel',
    };
    useProductionRecords.mockReturnValue({
      records: [historicalRecord],
      error: '',
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    });

    render(
      <MemoryRouter>
        <ProductionPage />
      </MemoryRouter>
    );

    // Cambiar a "Todo el historial" para ver el registro
    fireEvent.click(screen.getByRole('button', { name: 'Todo el historial' }));

    // No debe mostrar "Solo lectura"
    expect(screen.queryByText('Solo lectura')).not.toBeInTheDocument();

    // Debe mostrar los botones de editar y eliminar
    const editBtn = screen.getByRole('button', {
      name: /Editar producción de Hayacas/i,
    });
    const deleteBtn = screen.getByRole('button', {
      name: /Eliminar producción de Hayacas/i,
    });
    expect(editBtn).toBeInTheDocument();
    expect(deleteBtn).toBeInTheDocument();

    // Al hacer clic en editar, abre el modal de edición
    fireEvent.click(editBtn);
    expect(screen.getByRole('heading', { name: 'Editar producción' })).toBeInTheDocument();
  });

  it('descarga el reporte Excel enviando el período y producto filtrados', async () => {
    const records = generateMockRecords(10);
    useProductionRecords.mockReturnValue({
      records,
      error: '',
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    });
    downloadProductionReport.mockResolvedValueOnce(
      'reporte_produccion_balance_hayacas_2026-11-06.xlsx'
    );

    render(
      <MemoryRouter>
        <ProductionPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: 'Todo el historial' }));
    fireEvent.change(screen.getByLabelText('Filtrar productos'), {
      target: { value: 'hayacas' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Descargar reporte' }));

    await waitFor(() => {
      expect(downloadProductionReport).toHaveBeenCalledTimes(1);
    });
    expect(downloadProductionReport).toHaveBeenCalledWith({
      period: 'all',
      product: 'hayacas',
    });
    expect(
      await screen.findByText(
        /Reporte descargado: reporte_produccion_balance_hayacas_2026-11-06\.xlsx/i
      )
    ).toBeInTheDocument();
  });

  it('informa al usuario y evita descargar un archivo vacío cuando no hay registros de producción', () => {
    useProductionRecords.mockReturnValue({
      records: [],
      error: '',
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    });

    render(
      <MemoryRouter>
        <ProductionPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: 'Descargar reporte' }));

    expect(downloadProductionReport).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent(
      /No hay registros de producción para los filtros seleccionados\. Ajusta el período o el producto antes de descargar\./i
    );
  });
});
