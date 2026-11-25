import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/goals": "http://localhost:8000",
      "/inbound": "http://localhost:8000",
      "/notifications": "http://localhost:8000",
      "/sessions": "http://localhost:8000",
      "/voice": "http://localhost:8000",
    },
  },
});
