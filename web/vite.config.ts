/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // Pre-bundle everything up front: late discovery makes the dev server reload mid-run (flaky e2e on a cold cache).
  optimizeDeps: {
    include: ['react', 'react-dom/client', 'react-router-dom', '@xyflow/react', 'msw/browser'],
  },
  server: { port: 18473, strictPort: true, host: '127.0.0.1' },
  preview: { port: 18473, strictPort: true, host: '127.0.0.1' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
