import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const proxy = {
  '/api': {
    target: process.env.API_URL ?? 'http://localhost:28000',
    rewrite: (path: string) => path.replace(/^\/api/, ''),
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
})
