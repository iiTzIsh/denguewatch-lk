import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev: the dashboard calls /api/... and Vite forwards it to FastAPI on :8000 (no CORS needed).
// Docker: nginx does the same forwarding (web/nginx.conf).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    // map + chart libraries in their own files: cached separately, app code stays small
    rolldownOptions: {
      output: {
        advancedChunks: {
          groups: [
            { name: "maplibre", test: /maplibre/ },
            { name: "echarts", test: /echarts|zrender/ },
          ],
        },
      },
    },
    chunkSizeWarningLimit: 1100,
  },
});
