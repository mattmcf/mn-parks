import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 4174,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:3451",
        changeOrigin: true,
      },
    },
  },
})
