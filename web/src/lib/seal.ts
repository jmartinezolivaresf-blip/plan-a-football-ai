// Verify a sealed plan in the browser: SHA-256 of the canonical JSON of the plan without `sealed`.
// Canonical form matches contracts/sealing.py (sorted keys, no spaces, UTF-8, non-ASCII kept). Plans hold only
// strings, integers, booleans and nulls, so number formatting is identical in Python and JavaScript.
import type { Plan } from "../contracts/bundle";

export type SealState = "unsealed" | "verifying" | "verified" | "mismatch" | "unavailable";

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    if (typeof value === "number" && !Number.isInteger(value)) {
      throw new Error("canonicalJson: non-integer numbers are not supported for sealed payloads");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(",")}}`;
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function planDigest(plan: Plan): Promise<string> {
  const { sealed: _sealed, ...rest } = plan;
  return sha256Hex(canonicalJson(rest));
}

export async function verifyPlan(plan: Plan): Promise<SealState> {
  if (!plan.sealed) return "unsealed";
  if (!globalThis.crypto?.subtle) return "unavailable";
  return (await planDigest(plan)) === plan.sealed.sha256 ? "verified" : "mismatch";
}
