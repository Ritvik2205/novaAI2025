import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_PROXY_TARGET = process.env.VITE_API_BASE ?? "http://localhost:8000";

export default defineConfig({
  base: "/static/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/rag": API_PROXY_TARGET,
      "/health": API_PROXY_TARGET,
    },
  },
  build: {
    outDir: "../app/static",
    emptyOutDir: true,
    manifest: true,
  },
});
