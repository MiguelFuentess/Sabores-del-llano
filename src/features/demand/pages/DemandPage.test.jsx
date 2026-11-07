import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DemandPage from './DemandPage.jsx';
import * as demandApi from '../services/demandApi.js';

vi.mock('../services/demandApi.js', () => ({
  getDemandHistoricalContext: vi.fn(),
  requestDemandForecast: vi.fn(),
  downloadDemandReportCsv: vi.fn(),
  normalizeDemandProductName: vi.fn((val) => val),
}));

describe('DemandPage - Utilizar todo el historial sin selector sintético', () => {
  const mockContext = {
    fecha_minima_global: '2024-11-02',
    fecha_maxima_global: '2026-10-31',
    fecha_inicio_datos_reales: '2026-06-06',
    fecha_maxima_datos_reales: '2026-10-31',
    minimo_dias_operativos_requeridos: 3,
    dias_operativos_recomendados: 8,
    productos: [
      {
        producto_id: 1,
        producto_nombre: 'Hayaca',
        unidad_base: 'Unidad',
        fecha_minima_ventas: '2024-11-02',
        fecha_maxima_ventas: '2026-10-31',
        dias_operativos_totales: 240,
        dias_reales: 49,
        dias_sinteticos: 191,
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    demandApi.getDemandHistoricalContext.mockResolvedValue(mockContext);
  });

  it('no muestra el selector ni checkbox de registros sintéticos y muestra las jornadas disponibles', async () => {
    render(
      <MemoryRouter>
        <DemandPage />
      </MemoryRouter>
    );

    // Esperar a que se cargue el contexto
    await waitFor(() => {
      expect(screen.queryByText('Consultando contexto histórico...')).not.toBeInTheDocument();
    });

    // El checkbox o selector de incluir sintéticos no debe existir
    expect(
      screen.queryByLabelText(/Incluir registros históricos sintéticos/i)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Incluir registros históricos sintéticos/i)
    ).not.toBeInTheDocument();

    // Debe mostrar las jornadas operativas totales en el historial
    expect(
      screen.getByText(/240 jornadas operativas en el historial disponible/i)
    ).toBeInTheDocument();
  });

  it('solicita la estimación con el rango completo y sin excluir registros', async () => {
    demandApi.requestDemandForecast.mockResolvedValue({
      producto_nombre: 'Hayaca',
      horizonte_etiqueta: 'Próxima semana',
      fecha_inicio_horizonte: '2026-11-01',
      fecha_fin_horizonte: '2026-11-07',
      demanda_total_estimada: 120,
      produccion_total_sugerida: 110,
      sobrantes_totales_disponibles: 10,
      total_dias_operativos_proyectados: 2,
      unidad_base: 'Unidad',
      planificacion_diaria: [],
      metricas_precision: {
        nivel_confianza: 'alta',
        muestras_evaluadas: 20,
        mae_base: 3.5,
        mape_porcentaje: 8.2,
        origen_evaluacion: 'datos_reales_y_operativos',
        nota_metodologica: 'Validación sobre historial operativo.',
      },
      resumen_historico: {
        dias_operativos_con_ventas: 240,
        registros_reales: 49,
        registros_operativos: 0,
        registros_sinteticos: 191,
        proporcion_datos_reales: 20.4,
      },
    });

    render(
      <MemoryRouter>
        <DemandPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.queryByText('Consultando contexto histórico...')).not.toBeInTheDocument();
    });

    const submitBtn = screen.getByRole('button', { name: /Generar estimación/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(demandApi.requestDemandForecast).toHaveBeenCalledWith(
        expect.objectContaining({
          fechaDesde: '2024-11-02',
          fechaHasta: '2026-10-31',
          incluirSinteticos: true,
        })
      );
    });

    // Muestra jornadas analizadas en el resultado
    expect(
      screen.getByText(/240 jornadas del historial analizadas/i)
    ).toBeInTheDocument();

    // Comprueba la jerarquía visual del resultado
    expect(screen.getByText('Producción total sugerida:')).toHaveClass('demand-result__desc');
    expect(screen.getByText('110 unidades')).toHaveClass('demand-result__val');
    expect(screen.getByText('Sobrantes disponibles aplicados:')).toHaveClass('demand-result__desc');
    expect(screen.getByText('10 unidades')).toHaveClass('demand-result__val');
    expect(screen.getByText('2')).toHaveClass('demand-result__val');
    expect(screen.getByText('jornadas operativas proyectadas.')).toHaveClass('demand-result__desc');
  });

  it('no muestra error de conexión al cargar correctamente y no deja residuales', async () => {
    render(
      <MemoryRouter>
        <DemandPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.queryByText('Consultando contexto histórico...')).not.toBeInTheDocument();
    });

    // No debe mostrar ningún mensaje de desconexión
    expect(
      screen.queryByText(/No fue posible conectar con el servidor/i)
    ).not.toBeInTheDocument();
  });

  it('si la solicitud de contexto falla, muestra un mensaje específico y permite generar la estimación sin bloquear', async () => {
    demandApi.getDemandHistoricalContext.mockRejectedValueOnce(
      new Error('No fue posible sincronizar automáticamente el calendario histórico.')
    );
    demandApi.requestDemandForecast.mockResolvedValue({
      producto_nombre: 'Hayaca',
      horizonte_etiqueta: 'Próxima semana',
      fecha_inicio_horizonte: '2026-11-01',
      fecha_fin_horizonte: '2026-11-07',
      demanda_total_estimada: 100,
      produccion_total_sugerida: 100,
      sobrantes_totales_disponibles: 0,
      total_dias_operativos_proyectados: 2,
      unidad_base: 'Unidad',
      planificacion_diaria: [],
      metricas_precision: {
        nivel_confianza: 'media',
        muestras_evaluadas: 10,
        mae_base: 4,
        mape_porcentaje: 9,
        origen_evaluacion: 'datos_reales_y_operativos',
        nota_metodologica: 'Prueba',
      },
      resumen_historico: {
        dias_operativos_con_ventas: 50,
      },
    });

    render(
      <MemoryRouter>
        <DemandPage />
      </MemoryRouter>
    );

    // Muestra el mensaje específico sin alegar que todo el servidor está desconectado
    await waitFor(() => {
      expect(
        screen.getByText(/No fue posible sincronizar automáticamente el calendario histórico/i)
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/No fue posible conectar con el servidor de Sabores del Llano/i)
    ).not.toBeInTheDocument();

    // Asignar fechas manuales y generar estimación
    const fechaDesdeInput = screen.getByLabelText('Fecha desde');
    const fechaHastaInput = screen.getByLabelText('Fecha hasta');
    fireEvent.change(fechaDesdeInput, { target: { value: '2026-10-01' } });
    fireEvent.change(fechaHastaInput, { target: { value: '2026-10-31' } });

    const submitBtn = screen.getByRole('button', { name: /Generar estimación/i });
    fireEvent.click(submitBtn);

    // Al generarse exitosamente, el resultado aparece y el mensaje previo de advertencia se limpia
    await waitFor(() => {
      expect(
        screen.getByText(/Producción total sugerida:/i)
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/No fue posible sincronizar automáticamente el calendario histórico/i)
    ).not.toBeInTheDocument();
  });

  it('muestra el rango de fechas proyectado del 6 al 8 de noviembre de 2026 en zona horaria de Colombia y diferencia demanda estimada de producción sugerida', async () => {
    demandApi.requestDemandForecast.mockResolvedValue({
      producto_nombre: 'Hayaca',
      horizonte_etiqueta: 'Próxima semana',
      fecha_inicio_horizonte: '2026-11-06',
      fecha_fin_horizonte: '2026-11-08',
      demanda_total_estimada: 311,
      produccion_total_sugerida: 300,
      sobrantes_totales_disponibles: 11,
      total_dias_operativos_proyectados: 2,
      unidad_base: 'Unidad',
      planificacion_diaria: [
        {
          fecha: '2026-11-07',
          etiqueta_dia: 'Sábado',
          producto_nombre: 'Hayaca',
          unidad_base: 'Unidad',
          demanda_estimada: 156,
          sobrantes_disponibles: 11,
          produccion_sugerida: 145,
          rango_minimo_esperado: 138,
          rango_maximo_esperado: 174,
        },
        {
          fecha: '2026-11-08',
          etiqueta_dia: 'Domingo',
          producto_nombre: 'Hayaca',
          unidad_base: 'Unidad',
          demanda_estimada: 155,
          sobrantes_disponibles: 0,
          produccion_sugerida: 155,
          rango_minimo_esperado: 142,
          rango_maximo_esperado: 168,
        },
      ],
      metricas_precision: {
        nivel_confianza: 'alta',
        muestras_evaluadas: 20,
        mae_base: 11.86,
        mape_porcentaje: 7.29,
        origen_evaluacion: 'datos_reales_y_operativos',
        nota_metodologica: 'Validación walk-forward sobre 20 jornadas.',
      },
      resumen_historico: {
        dias_operativos_con_ventas: 240,
      },
      recomendaciones: [],
    });

    render(
      <MemoryRouter>
        <DemandPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.queryByText('Consultando contexto histórico...')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Generar estimación/i }));

    await waitFor(() => {
      expect(screen.getByText(/Período proyectado:/i)).toBeInTheDocument();
    });

    const periodBanner = screen.getByText(/Período proyectado:/i).textContent;
    expect(periodBanner).toMatch(/0?6.*nov.*2026/i);
    expect(periodBanner).toMatch(/0?8.*nov.*2026/i);
    expect(periodBanner).not.toMatch(/0?1.*nov.*2026/i);

    expect(screen.getByText(/0?7.*nov.*2026/i)).toBeInTheDocument();
    expect(
      screen.getAllByText(/0?8.*nov.*2026/i).length
    ).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('156')).toBeInTheDocument();
    expect(screen.getByText('145')).toBeInTheDocument();
    expect(screen.getByText('0 unidades')).toBeInTheDocument();
  });
});
