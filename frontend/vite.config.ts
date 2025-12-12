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
        target: "https://congenial-zebra-g4j64jqw49gjfwrww-8000.github.dev", // FastAPI dentro del contenedor
        changeOrigin: true,
      },
    },
  },
});
