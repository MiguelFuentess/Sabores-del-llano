import fs from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  apiDownloadFile,
  apiRequest,
  clearAuthSession,
  getApiBaseUrl,
} from './authService.js';

const AUTH_SESSION_KEY = 'sabores-del-llano-auth-session-v1';

function seedValidSession() {
  window.sessionStorage.setItem(
    AUTH_SESSION_KEY,
    JSON.stringify({
      accessToken: 'header.eyJleHAiOjQxMDI0NDQ4MDB9.signature',
      tokenType: 'bearer',
      expiresAt: Date.now() + 3600_000,
      usuario: { id: 1, nombre_usuario: 'luz.admin', nombre_completo: 'Doña Luz' },
    })
  );
}

describe('IMP-01 — Configuración SPA Rewrite para Render y sitios estáticos', () => {
  it('incluye public/_redirects con regla SPA /* -> /index.html 200', () => {
    const redirectsPath = path.resolve(process.cwd(), 'public', '_redirects');
    expect(fs.existsSync(redirectsPath)).toBe(true);
    const content = fs.readFileSync(redirectsPath, 'utf-8').trim();
    expect(content).toBe('/* /index.html 200');
  });

  it('incluye render.yaml con runtime static y rewrite /* -> /index.html', () => {
    const renderYamlPath = path.resolve(process.cwd(), 'render.yaml');
    expect(fs.existsSync(renderYamlPath)).toBe(true);
    const content = fs.readFileSync(renderYamlPath, 'utf-8');
    expect(content).toContain('runtime: static');
    expect(content).toContain('staticPublishPath: ./dist');
    expect(content).toContain('type: rewrite');
    expect(content).toContain('source: /*');
    expect(content).toContain('destination: /index.html');
  });
});

describe('IMP-02 — Blindaje de authService frente a fallback /api y respuestas HTML en SPA', () => {
  const originalFetch = window.fetch;
  const originalCreateObjectURL = window.URL.createObjectURL;
  const originalRevokeObjectURL = window.URL.revokeObjectURL;

  beforeEach(() => {
    clearAuthSession();
    window.fetch = vi.fn();
    window.URL.createObjectURL = vi.fn(() => 'blob:reporte-mock');
    window.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    clearAuthSession();
    window.fetch = originalFetch;
    window.URL.createObjectURL = originalCreateObjectURL;
    window.URL.revokeObjectURL = originalRevokeObjectURL;
    vi.restoreAllMocks();
  });

  it('getApiBaseUrl devuelve cadena vacía en producción si falta VITE_API_URL y usa localhost en desarrollo', () => {
    expect(getApiBaseUrl({ PROD: true, DEV: false, VITE_API_URL: '' })).toBe('');
    expect(getApiBaseUrl({ PROD: false, DEV: true, VITE_API_URL: '' })).toBe(
      'http://127.0.0.1:8000'
    );
    expect(
      getApiBaseUrl({
        PROD: true,
        DEV: false,
        VITE_API_URL: 'https://sabores-del-llano-api.onrender.com/',
      })
    ).toBe('https://sabores-del-llano-api.onrender.com');
  });

  it('en producción sin VITE_API_URL falla de inmediato sin llamar a 127.0.0.1 ni a /api/*', async () => {
    await expect(
      apiRequest('/health', {
        auth: false,
        env: { PROD: true, DEV: false, VITE_API_URL: '' },
      })
    ).rejects.toThrow('No fue posible conectar con el servidor de Sabores del Llano.');

    expect(window.fetch).not.toHaveBeenCalled();
  });

  it('en producción NO reintenta /api/* cuando la API entra en cold start o falla la red', async () => {
    window.fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    await expect(
      apiRequest('/auth/login', {
        method: 'POST',
        auth: false,
        body: { nombre_usuario: 'luz', password: 'secret' },
        env: {
          PROD: true,
          DEV: false,
          VITE_API_URL: 'https://sabores-del-llano-api.onrender.com',
        },
      })
    ).rejects.toThrow('No fue posible conectar con el servidor de Sabores del Llano.');

    expect(window.fetch).toHaveBeenCalledTimes(1);
    expect(window.fetch).toHaveBeenCalledWith(
      'https://sabores-del-llano-api.onrender.com/auth/login',
      expect.any(Object)
    );
  });

  it('en desarrollo (DEV=true) conserva el reintento por proxy /api/* de Vite', async () => {
    window.fetch
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

    const result = await apiRequest('/health', {
      auth: false,
      env: { PROD: false, DEV: true, VITE_API_URL: 'http://127.0.0.1:8000' },
    });

    expect(result).toEqual({ status: 'ok' });
    expect(window.fetch).toHaveBeenCalledTimes(2);
    expect(window.fetch.mock.calls[1][0]).toBe('/api/health');
  });

  it('apiRequest rechaza un 200 OK con Content-Type text/html (SPA index.html) en vez de devolver null', async () => {
    window.fetch.mockResolvedValueOnce(
      new Response('<!doctype html><html><body>SPA</body></html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      })
    );

    await expect(
      apiRequest('/ventas', {
        auth: false,
        env: {
          PROD: true,
          DEV: false,
          VITE_API_URL: 'https://sabores-del-llano-api.onrender.com',
        },
      })
    ).rejects.toThrow('No fue posible conectar con el servidor de Sabores del Llano.');
  });

  it('apiDownloadFile rechaza un 200 OK text/html sin descargar un .xlsx corrupto y acepta spreadsheetml válido', async () => {
    seedValidSession();
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});

    // 1. Respuesta HTML (ej. rewrite SPA erróneo) -> debe fallar sin descargar
    window.fetch.mockResolvedValueOnce(
      new Response('<!doctype html><html><body>index</body></html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      })
    );

    await expect(
      apiDownloadFile('/ventas/reporte', {
        fallbackFilename: 'reporte_ventas.xlsx',
        env: {
          PROD: true,
          DEV: false,
          VITE_API_URL: 'https://sabores-del-llano-api.onrender.com',
        },
      })
    ).rejects.toThrow('No fue posible conectar con el servidor de Sabores del Llano.');
    expect(clickSpy).not.toHaveBeenCalled();

    // 2. Respuesta Excel válida -> descarga correctamente
    window.fetch.mockResolvedValueOnce(
      new Response(new Uint8Array([80, 75, 3, 4]), {
        status: 200,
        headers: {
          'Content-Type':
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Content-Disposition':
            "attachment; filename*=UTF-8''reporte_ventas_2026-11-07.xlsx",
        },
      })
    );

    const filename = await apiDownloadFile('/ventas/reporte', {
      fallbackFilename: 'reporte_ventas.xlsx',
      env: {
        PROD: true,
        DEV: false,
        VITE_API_URL: 'https://sabores-del-llano-api.onrender.com',
      },
    });

    expect(filename).toBe('reporte_ventas_2026-11-07.xlsx');
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });
});
