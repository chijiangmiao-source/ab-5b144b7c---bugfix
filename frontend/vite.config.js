import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During local development the React dev server runs on 5173 and proxies
// API/health calls to a local FastAPI on 8000. In Docker, nginx serves
// the built assets and proxies the same paths to the api service.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
