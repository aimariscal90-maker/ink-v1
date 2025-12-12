import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,      // necesario en Codespaces
    port: 5173,
    proxy: {
      // Todo lo que empiece por /api se reenvía al backend
      "/api": {
        target: "http://127.0.0.1:8000", // Reenvía al servidor backend local
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
