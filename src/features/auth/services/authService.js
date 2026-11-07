const AUTH_SESSION_KEY = 'sabores-del-llano-auth-session-v1';
const REMEMBERED_USERNAME_KEY = 'sabores-del-llano-remembered-user-v1';
const LEGACY_DEMO_ACCESS_KEY = 'sabores-del-llano-demo-access';
export const AUTH_CHANGE_EVENT = 'sabores-del-llano:auth-changed';

const CONNECTION_ERROR_MESSAGE =
  'No fue posible conectar con el servidor de Sabores del Llano.';

export function getApiBaseUrl(env = import.meta.env) {
  const configured = env?.VITE_API_URL;
  const normalized = configured ? String(configured).trim().replace(/\/+$/, '') : '';
  if (normalized) {
    return normalized;
  }
  if (env?.PROD) {
    return '';
  }
  return 'http://127.0.0.1:8000';
}

function shouldRetryViaDevProxy(baseUrl, env = import.meta.env) {
  return Boolean(env?.DEV) && !env?.PROD && baseUrl !== '/api';
}

function isJsonContentType(contentType) {
  const normalized = String(contentType || '').toLowerCase();
  return normalized.includes('application/json') || normalized.includes('+json');
}

function isValidSpreadsheetContentType(contentType) {
  const normalized = String(contentType || '').toLowerCase();
  if (!normalized) {
    return true;
  }
  if (normalized.includes('text/html') || normalized.includes('application/json')) {
    return false;
  }
  return (
    normalized.includes('spreadsheetml') ||
    normalized.includes('application/vnd.ms-excel') ||
    normalized.includes('application/octet-stream')
  );
}

async function performApiFetch(path, fetchOptions, { signal, env = import.meta.env } = {}) {
  const baseUrl = getApiBaseUrl(env);
  if (!baseUrl) {
    throw new Error(CONNECTION_ERROR_MESSAGE);
  }

  try {
    return await window.fetch(`${baseUrl}${path}`, fetchOptions);
  } catch (error) {
    if (signal?.aborted || error?.name === 'AbortError') {
      const abortError = new Error('La solicitud fue cancelada.');
      abortError.name = 'AbortError';
      throw abortError;
    }
    if (!shouldRetryViaDevProxy(baseUrl, env)) {
      throw new Error(CONNECTION_ERROR_MESSAGE);
    }
    try {
      return await window.fetch(`/api${path}`, fetchOptions);
    } catch (fallbackError) {
      if (signal?.aborted || fallbackError?.name === 'AbortError') {
        const abortError = new Error('La solicitud fue cancelada.');
        abortError.name = 'AbortError';
        throw abortError;
      }
      throw new Error(CONNECTION_ERROR_MESSAGE);
    }
  }
}

function decodeJwtExpMs(token) {
  try {
    const [, payloadSegment] = String(token || '').split('.');
    if (!payloadSegment) return null;
    const base64 = payloadSegment.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const payload = JSON.parse(window.atob(padded));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function clearAuthSession() {
  window.sessionStorage.removeItem(AUTH_SESSION_KEY);
  window.localStorage.removeItem(AUTH_SESSION_KEY);
  window.sessionStorage.removeItem(LEGACY_DEMO_ACCESS_KEY);
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

export function readAuthSession() {
  window.sessionStorage.removeItem(LEGACY_DEMO_ACCESS_KEY);
  const raw =
    window.sessionStorage.getItem(AUTH_SESSION_KEY) ??
    window.localStorage.getItem(AUTH_SESSION_KEY);
  if (!raw) return null;

  try {
    const session = JSON.parse(raw);
    if (!session || typeof session.accessToken !== 'string' || !session.accessToken) {
      clearAuthSession();
      return null;
    }
    const jwtExpMs = decodeJwtExpMs(session.accessToken);
    const expiresAt = Number(session.expiresAt) || jwtExpMs || 0;
    if (expiresAt && Date.now() >= expiresAt) {
      clearAuthSession();
      return null;
    }
    return { ...session, expiresAt };
  } catch {
    clearAuthSession();
    return null;
  }
}

export function getAccessToken() {
  return readAuthSession()?.accessToken ?? null;
}

export function getCurrentUserSnapshot() {
  return readAuthSession()?.usuario ?? null;
}

export function hasAuthenticatedSession() {
  return Boolean(getAccessToken());
}

export function getRememberedUsername() {
  return window.localStorage.getItem(REMEMBERED_USERNAME_KEY) ?? '';
}

function formatApiErrorDetail(payload, fallbackMessage) {
  if (!payload) return fallbackMessage;
  if (typeof payload.detail === 'string' && payload.detail.trim()) {
    return payload.detail;
  }
  if (Array.isArray(payload.detail) && payload.detail.length > 0) {
    const first = payload.detail[0];
    if (first && typeof first.msg === 'string') {
      return first.msg.replace(/^Value error,\s*/i, '');
    }
  }
  return fallbackMessage;
}

export async function apiRequest(
  path,
  { method = 'GET', body, headers = {}, auth = true, signal, env = import.meta.env } = {}
) {
  const requestHeaders = { ...headers };

  if (auth) {
    const token = getAccessToken();
    if (!token) {
      clearAuthSession();
      const error = new Error('Tu sesión ha expirado. Por favor inicia sesión nuevamente.');
      error.status = 401;
      throw error;
    }
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  let serializedBody;
  if (body !== undefined) {
    requestHeaders['Content-Type'] = 'application/json';
    serializedBody = JSON.stringify(body);
  }

  const fetchOptions = {
    method,
    headers: requestHeaders,
    body: serializedBody,
    signal,
  };

  const response = await performApiFetch(path, fetchOptions, { signal, env });

  if (response.status === 502 || response.status === 503 || response.status === 504) {
    let proxyData = null;
    try {
      proxyData = await response.clone().json();
    } catch {
      proxyData = null;
    }
    if (!proxyData || !proxyData.detail) {
      throw new Error(CONNECTION_ERROR_MESSAGE);
    }
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = String(response.headers?.get?.('content-type') || '').toLowerCase();
  let data = null;
  let jsonParseFailed = false;
  try {
    data = await response.json();
  } catch {
    data = null;
    jsonParseFailed = true;
  }

  if (!response.ok) {
    if (auth && (response.status === 401 || response.status === 403)) {
      clearAuthSession();
    }
    const error = new Error(
      formatApiErrorDetail(data, `Error en la solicitud (${response.status}).`)
    );
    error.status = response.status;
    throw error;
  }

  if ((contentType && !isJsonContentType(contentType)) || jsonParseFailed) {
    throw new Error(CONNECTION_ERROR_MESSAGE);
  }

  return data;
}

function extractFilenameFromDisposition(disposition, fallbackFilename) {
  if (!disposition || typeof disposition !== 'string') {
    return fallbackFilename;
  }
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;\s]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1].replace(/["']/g, ''));
    } catch {
      return utf8Match[1].replace(/["']/g, '');
    }
  }
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  if (plainMatch?.[1]) {
    return plainMatch[1].trim();
  }
  return fallbackFilename;
}

export async function apiDownloadFile(
  path,
  { fallbackFilename = 'reporte.xlsx', signal, env = import.meta.env } = {}
) {
  const token = getAccessToken();
  if (!token) {
    clearAuthSession();
    const error = new Error('Tu sesión ha expirado. Por favor inicia sesión nuevamente.');
    error.status = 401;
    throw error;
  }

  const fetchOptions = {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal,
  };

  const response = await performApiFetch(path, fetchOptions, { signal, env });

  if (response.status === 502 || response.status === 503 || response.status === 504) {
    let proxyData = null;
    try {
      proxyData = await response.clone().json();
    } catch {
      proxyData = null;
    }
    if (!proxyData || !proxyData.detail) {
      throw new Error(CONNECTION_ERROR_MESSAGE);
    }
  }

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      clearAuthSession();
    }
    let errorData = null;
    try {
      errorData = await response.json();
    } catch {
      errorData = null;
    }
    const error = new Error(
      formatApiErrorDetail(
        errorData,
        `No fue posible generar el reporte (${response.status}).`
      )
    );
    error.status = response.status;
    throw error;
  }

  const contentType = String(response.headers?.get?.('content-type') || '').toLowerCase();
  if (!isValidSpreadsheetContentType(contentType)) {
    throw new Error(CONNECTION_ERROR_MESSAGE);
  }

  const blob = await response.blob();
  if (!blob || blob.size === 0) {
    throw new Error('No hay información disponible para descargar con los filtros actuales.');
  }

  const filename = extractFilenameFromDisposition(
    response.headers?.get?.('Content-Disposition'),
    fallbackFilename
  );

  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => {
    window.URL.revokeObjectURL(objectUrl);
  }, 1000);

  return filename;
}

export async function loginWithCredentials({
  username,
  password,
  rememberCredentials = false,
}) {
  const cleanedUsername = String(username ?? '').trim();
  const data = await apiRequest('/auth/login', {
    method: 'POST',
    auth: false,
    body: {
      nombre_usuario: cleanedUsername,
      password: String(password ?? ''),
    },
  });

  const jwtExpMs = decodeJwtExpMs(data.access_token);
  const expiresAt =
    jwtExpMs || Date.now() + Math.max(1, Number(data.expires_in) || 28800) * 1000;

  const sessionPayload = JSON.stringify({
    accessToken: data.access_token,
    tokenType: data.token_type || 'bearer',
    expiresAt,
    usuario: data.usuario,
  });

  window.sessionStorage.setItem(AUTH_SESSION_KEY, sessionPayload);

  if (rememberCredentials) {
    window.localStorage.setItem(REMEMBERED_USERNAME_KEY, cleanedUsername);
    window.localStorage.setItem(AUTH_SESSION_KEY, sessionPayload);
  } else {
    window.localStorage.removeItem(REMEMBERED_USERNAME_KEY);
    window.localStorage.removeItem(AUTH_SESSION_KEY);
  }

  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
  return data;
}

export async function fetchCurrentUser({ signal } = {}) {
  const usuario = await apiRequest('/auth/me', { method: 'GET', auth: true, signal });
  const current = readAuthSession();
  if (current) {
    const updated = JSON.stringify({ ...current, usuario });
    window.sessionStorage.setItem(AUTH_SESSION_KEY, updated);
    if (window.localStorage.getItem(AUTH_SESSION_KEY) !== null) {
      window.localStorage.setItem(AUTH_SESSION_KEY, updated);
    }
  }
  return usuario;
}

export function subscribeAuthChanges(listener) {
  window.addEventListener(AUTH_CHANGE_EVENT, listener);
  window.addEventListener('storage', listener);
  return () => {
    window.removeEventListener(AUTH_CHANGE_EVENT, listener);
    window.removeEventListener('storage', listener);
  };
}
