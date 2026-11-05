import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Limpieza del DOM entre pruebas para evitar interferencias
afterEach(() => {
  cleanup();
});
