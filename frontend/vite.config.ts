import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Phase 6: dev-server proxy forwards /api and /health to the existing
// FastAPI backend (assumed running on 127.0.0.1:8000, per README's Phase 4
// "How to start the server" instructions). This means the backend needs NO
// CORS changes and NO code changes at all for the frontend to work in dev
// mode — the browser only ever talks to the Vite origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
