import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const apiTarget = process.env.API_PROXY ?? 'http://127.0.0.1:8000'
const proxy = Object.fromEntries(['/v1', '/healthz', '/readyz'].map((p) => [p, { target: apiTarget, changeOrigin: true }]))

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@mock': fileURLToPath(new URL('./mock', import.meta.url)),
    },
  },
  server: { proxy },
  preview: { proxy },
  build: { target: 'es2022', sourcemap: true },
})
