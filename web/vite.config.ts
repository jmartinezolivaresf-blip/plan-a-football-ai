import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The demo is fully static: match_bundle.json is served from /public. No backend is required.
export default defineConfig({
  plugins: [react()],
});
