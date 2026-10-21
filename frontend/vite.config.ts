import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '');
  return {
    plugins: [react()],
    envDir: '..',
    server: {
      proxy: {
        '/api': {
          target: process.env.API_PROXY_TARGET || env.API_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: false,
        },
      },
    },
    test: { environment: 'jsdom', setupFiles: './src/test-setup.ts' },
  };
});
