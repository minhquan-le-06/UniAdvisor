/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run dev` proxies /api to the Python server (uvicorn uniadvisor.api.app:create_app --factory --port 8000), so
// the browser sees one origin, as in production where FastAPI serves web/dist.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        // react and the router change rarely: their own file stays cached across releases
        manualChunks(id: string) {
          if (/node_modules\/(react|react-dom|react-router|scheduler)\//.test(id)) return "react";
          if (id.includes("node_modules/@radix-ui") || id.includes("node_modules/cmdk")) return "radix";
        },
      },
    },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"], setupFiles: ["src/test-setup.ts"], css: { modules: { classNameStrategy: "non-scoped" } } },
});
