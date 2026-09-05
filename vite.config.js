import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '0.0.0.0',
    port: 5193,
    cors: true,
    allowedHosts: true,
    proxy: {
      '/api': 'http://127.0.0.1:5178',
      '/party': 'http://127.0.0.1:5178',
      '/mobile': 'http://127.0.0.1:5178',
      '/media': 'http://127.0.0.1:5178',
    },
  },
})
