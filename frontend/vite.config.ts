import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import path from 'path';

const OUT_DIR = process.env.VITE_OUT_DIR || 'build';

export default defineConfig({
  server: {
    port: 5173,
    host: true,
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  worker: {
    format: 'es',
  },
  build: {
    target: 'esnext',
    outDir: OUT_DIR,
    rollupOptions: {
      plugins: process.env.ANALYZE === '1' ? [
        visualizer({ filename: path.resolve(OUT_DIR, 'stats.html'), title: 'DFSP bundle analysis', gzipSize: true })
      ] : []
    }
  },
});
