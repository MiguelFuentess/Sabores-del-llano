const DEMO_ACCESS_KEY = 'sabores-del-llano-demo-access';

export function hasDemoAccess() {
  return window.sessionStorage.getItem(DEMO_ACCESS_KEY) === 'granted';
}

export function grantDemoAccess() {
  window.sessionStorage.setItem(DEMO_ACCESS_KEY, 'granted');
}

export function clearDemoAccess() {
  window.sessionStorage.removeItem(DEMO_ACCESS_KEY);
}
