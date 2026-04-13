/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Why a /api proxy instead of CORS-in-browser:
// the Flask backend allows CORS, but proxying through Vite keeps the
// frontend origin-agnostic in dev — the same-origin fetch ('/api/v1/...')
// works identically in `vite dev` and in prod behind nginx.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: 'http://flask:5000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
