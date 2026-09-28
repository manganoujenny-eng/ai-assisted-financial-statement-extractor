import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The proxy is the point of this file. With it, the frontend calls
// `/api/cases` — a same-origin URL — and Vite forwards it to Flask on port
// 5000. Without it you would hardcode `http://localhost:5000` everywhere and
// then have to find every occurrence again the day the backend moves.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
