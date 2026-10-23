import type { MatchBundle } from "./contracts/bundle";

// The demo never needs a backend: the precomputed bundle is a static file.
export async function loadBundle(url = "/match_bundle.json"): Promise<MatchBundle> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load ${url} (${res.status}). Run \`make web-bundle\`.`);
  return (await res.json()) as MatchBundle;
}
