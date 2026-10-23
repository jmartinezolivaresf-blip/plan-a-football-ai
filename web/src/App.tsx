// H0 placeholder: a developer inspector for match_bundle.json, NOT the broadcast UI (that starts at H1).
import { useEffect, useState } from "react";
import type { MatchBundle } from "./contracts/bundle";
import { loadBundle } from "./bundle";

export function App() {
  const [bundle, setBundle] = useState<MatchBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadBundle().then(setBundle, (e: Error) => setError(e.message));
  }, []);

  if (error) return <p role="alert">{error}</p>;
  if (!bundle) return <p>Loading bundle…</p>;

  const { meta, snapshots, events, plans, duel } = bundle;
  const ht = snapshots[45]?.score;
  const ft = snapshots[snapshots.length - 1]?.score;
  const tm = duel?.broadcast.true_matrix;

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: 24, maxWidth: 960 }}>
      <h1>Plan A: The Battle of the Benches</h1>
      <p>
        <strong>Bundle inspector (H0).</strong> {bundle.illustrative ? "Illustrative fixture data, not simulated." : ""}{" "}
        {meta.precomputed ? "Precomputed demo." : ""} Schema {bundle.schema_version}.
      </p>
      <p>
        {meta.home} vs {meta.away} · HT {ht?.[meta.home]}-{ht?.[meta.away]} · FT {ft?.[meta.home]}-{ft?.[meta.away]} ·{" "}
        {events.length} events · {snapshots.length} snapshots · {bundle.cues.length} cues
      </p>
      <h2>Sealed plans</h2>
      <ul>
        {Object.values(plans).map((p) => (
          <li key={p.plan_id}>
            {p.team}: {p.name.en} <code>{p.sealed?.sha256.slice(0, 12)}…</code>
          </li>
        ))}
      </ul>
      {tm && (
        <>
          <h2>True matrix (ΔxPts for {tm.row_team} vs Stay/Stay)</h2>
          <table style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th />
                {tm.cols.map((c) => (
                  <th key={c} style={{ padding: 6 }}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tm.cells.map((row, i) => (
                <tr key={tm.rows[i]}>
                  <th style={{ padding: 6, textAlign: "left" }}>{tm.rows[i]}</th>
                  {row.map((cell, j) => (
                    <td key={j} style={{ padding: 6, textAlign: "right" }}>
                      {(cell.xpts[tm.row_team] - tm.cells[0][0].xpts[tm.row_team]).toFixed(2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
