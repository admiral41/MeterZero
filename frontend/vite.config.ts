import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI server (server/main.py) serves /api; during development Vite proxies to it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 2500,
    rollupOptions: {
      output: {
        // Keep the 3D engine and the charts in their own cacheable chunks.
        manualChunks(id: string) {
          if (/node_modules[\\/](three|@react-three|three-stdlib|troika)/.test(id)) return 'three'
          if (/node_modules[\\/](recharts|d3-|victory)/.test(id)) return 'charts'
          return undefined
        },
      },
    },
  },
})
