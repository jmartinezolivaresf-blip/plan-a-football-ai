// Seal status of a plan. "Verified" is shown only after recomputing the SHA-256 in the browser.
import { useEffect, useState } from "react";
import type { Plan } from "../contracts/bundle";
import { type SealState, verifyPlan } from "../lib/seal";

const LABEL: Record<SealState, string> = {
  unsealed: "Not sealed",
  verifying: "Checking seal…",
  verified: "Seal verified",
  mismatch: "Seal mismatch",
  unavailable: "Sealed (not verified here)",
};

export function SealBadge({ plan, initial = "verifying" }: { plan: Plan; initial?: SealState }) {
  const [state, setState] = useState<SealState>(plan.sealed ? initial : "unsealed");
  useEffect(() => {
    let alive = true;
    verifyPlan(plan).then((s) => alive && setState(s), () => alive && setState("unavailable"));
    return () => {
      alive = false;
    };
  }, [plan]);
  return (
    <div className={`seal ${state}`} data-testid="seal" title={plan.sealed?.sha256}>
      <span className="seal-icon" aria-hidden>{state === "verified" ? "✓" : state === "mismatch" ? "✕" : "●"}</span>
      <span>{LABEL[state]}</span>
      {plan.sealed && <code>sha256 {plan.sealed.sha256.slice(0, 10)}…</code>}
    </div>
  );
}
