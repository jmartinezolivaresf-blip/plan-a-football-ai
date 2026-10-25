import { readFileSync } from "node:fs";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// The demo is fully static: match_bundle.json is served from /public. No backend is required.
// The default build is for a domain root (Azure Static Web Apps, Netlify); a sub-path host (GitHub Pages) builds with
// `npm run build -- --base=/<repository>/` (.github/workflows/pages.yml).

// The Content-Security-Policy of staticwebapp.config.json, also as a meta tag in the built page, so hosts that cannot
// set headers (GitHub Pages) enforce the same policy. frame-ancestors only works as a header and is left out here.
// Build only: the dev server needs inline scripts.
function cspMeta(): Plugin {
  const swa = JSON.parse(readFileSync(new URL("./public/staticwebapp.config.json", import.meta.url), "utf8"));
  const csp = String(swa.globalHeaders["content-security-policy"])
    .split(";").map((d) => d.trim()).filter((d) => d && !d.startsWith("frame-ancestors")).join("; ");
  return {
    name: "plan-a-csp-meta",
    apply: "build",
    transformIndexHtml: () => [{ tag: "meta", attrs: { "http-equiv": "Content-Security-Policy", content: csp },
                                 injectTo: "head-prepend" }],
  };
}

export default defineConfig({
  plugins: [react(), cspMeta()],
});
