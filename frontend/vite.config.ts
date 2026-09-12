import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // satellite.js 7 ships an optional wasm runtime that uses top-level await
  optimizeDeps: { esbuildOptions: { target: "esnext" } },
  build: { target: "esnext" },
  worker: { format: "es" },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
