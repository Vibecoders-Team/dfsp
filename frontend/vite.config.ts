import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',     // jsdom для DOM API
    globals: true,            // делает test/expect global'ными
    setupFiles: './src/setupTests.ts' // файл подготовки
  }
})

