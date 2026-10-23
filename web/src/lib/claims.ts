// Claim lookup and placeholder filling (same formatting rules as agents/validators/text.py: format_value).
import type { Claim, MatchBundle } from "../contracts/bundle";

const PLACEHOLDER = /\{(c[\w-]+)\.(\w+)\}/g;
const TAG = /\s*\[c[\w-]+\]/g;
const SHARE_FIELDS = new Set(["value", "league_ref", "interval_low", "interval_high"]);

export type ClaimIndex = Map<string, Claim>;

export function indexClaims(bundle: MatchBundle): ClaimIndex {
  return new Map(bundle.claims.map((c) => [c.claim_id, c]));
}

export function formatValue(claim: Claim, field: string): string {
  const value = (claim as unknown as Record<string, unknown>)[field];
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (claim.metric.endsWith("_share") && SHARE_FIELDS.has(field)) return `${Math.round(value * 100)}%`;
    if (Number.isInteger(value)) return String(value);
    return Math.abs(value) < 100 ? String(Number(value.toFixed(2))) : value.toFixed(0);
  }
  return String(value);
}

/** Replace {claim.field} placeholders with values and drop [claim] tags. Unknown claims stay visible as "?". */
export function fill(text: string, claims: ClaimIndex): string {
  return text
    .replace(PLACEHOLDER, (_m, id: string, field: string) => {
      const c = claims.get(id);
      return c ? formatValue(c, field) : "?";
    })
    .replace(TAG, "");
}

export function claimIdsIn(text: string): string[] {
  return [...text.matchAll(PLACEHOLDER)].map((m) => m[1]).concat([...text.matchAll(/\[(c[\w-]+)\]/g)].map((m) => m[1]));
}
