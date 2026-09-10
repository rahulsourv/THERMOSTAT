import { defineConfig } from "vite";
import preact from "@preact/preset-vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [preact(), tailwindcss()],
  server: {
    port: 5173,
    // Anything starting with /api is forwarded to FastAPI by the dev server.
    // The browser then only ever talks to ONE origin, so no CORS, no
    // preflight, and nothing for a network policy to block. It is also how
    // this runs in production behind nginx.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
