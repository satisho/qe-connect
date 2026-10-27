import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built files are served by the Python backend. In development, `npm run dev`
// proxies /api to a backend started with `python -m app` on port 8000.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false, assetsInlineLimit: 0 },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
