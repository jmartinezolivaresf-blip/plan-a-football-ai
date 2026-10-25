# Publishing the demo (static site)

The demo is a static site: `web/dist` (the app) plus the committed, synthetic `match_bundle.json` (season 2026, match
seed 204). No backend, no keys, no MCP server exposed. Whoever has the URL can open it, which is the point: judges
must reach it without logging in until 10 Nov 2026. Nothing below has been run yet.

## Options

| Option | Status | Needs | URL |
|---|---|---|---|
| **Azure Static Web Apps (Free)**, the plan | ready: `infra/swa_deploy.sh` (guards, Free plan, anonymous check), config verified in the SWA emulator | the personal Azure subscription (in review) | `https://<name>.azurestaticapps.net` |
| **GitHub Pages**, the simplest fallback | ready: `.github/workflows/pages.yml`, manual only | the repository public (GitHub Free) or a Pro plan; Pages enabled by the owner | `https://jmartinezolivaresf-blip.github.io/plan-a-football-ai/` |
| Netlify or Cloudflare Pages | not prepared beyond the build | an account on that service; works from a private repository | `https://<name>.netlify.app` / `https://<name>.pages.dev` |

GitHub Pages is the simplest fallback: no new account, no cost, HTTPS, and the repository becomes public at
submission anyway. If the URL is needed while the repository must stay private, Netlify or Cloudflare Pages are the
next simplest (`npx netlify-cli deploy --dir web/dist --prod` or `npx wrangler pages deploy web/dist`, after logging
in to that service).

## What the build guarantees on any host

- The default build (`npm run build`) is for a domain root; GitHub Pages builds for `/<repository>/`
  (`npm run build -- --base=/plan-a-football-ai/`). Both were checked in Chrome on 127.0.0.1: the duel, full time,
  the analyst desk and the in-browser seal checks work. Deep links are query strings (`?t=45:00&reveal=1&club=HAR`),
  so no server routing is needed.
- The page carries the same Content-Security-Policy as `web/public/staticwebapp.config.json` as a meta tag (added at
  build time from that file), so hosts that cannot set headers still enforce it. Hosts without headers lose only
  `frame-ancestors` and the other response headers set by Static Web Apps.
- No source maps, no credentials (the Pages workflow checks both), and the workflow refuses to publish a bundle that
  is not the frozen demo (for example the CI fixture).

## GitHub Pages, when the owners decide to publish

1. Make the repository public (an owner decision, also needed for the submission) or use a plan that allows Pages
   on private repositories. Either way the published site is public.
2. Settings > Pages > Build and deployment > Source: **GitHub Actions**.
3. Actions > **pages** > Run workflow (branch `main`).
4. Verify as an anonymous visitor (a private browser window, or `curl` without credentials) and require success:
   `curl -sI https://jmartinezolivaresf-blip.github.io/plan-a-football-ai/` and `.../match_bundle.json` return 200;
   `.../?t=45:00&reveal=1&club=HAR` shows the duel with "Matches the locked choice" on both benches.
5. Put the URL in the README (`<!-- DEMO_URL -->`), `docs/PITCH.md` and `docs/SUBMISSION.md`.

To take it down: Settings > Pages > Unpublish site (or disable Pages).
