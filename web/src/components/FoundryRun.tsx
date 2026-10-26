// "Real Microsoft Foundry Run": what the same agents did with a real model (gpt-4.1-mini on Microsoft Foundry) on this
// match's data and half-time, next to the deterministic replay the rest of the site shows. Every value comes from the
// recorded run (eval/results/foundry/probe_seed204.json via public/foundry_run.json).
import type { FoundryRun as Run } from "../lib/foundry";

const TOOL_LABEL: Record<string, string> = {
  get_player_profile: "a player's profile",
  get_team_tendencies: "team tendencies",
  get_set_piece_profile: "set pieces",
  list_matches: "past matches",
};

const fmt = (n: number) => n.toLocaleString("en-GB");
const ci = (c: [number, number]) => `${c[0]} to ${c[1]}`;

function tools(names: string[]): string {  // "a player's profile ×3, team tendencies"
  const counts = new Map<string, number>();
  for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
  return [...counts].map(([n, k]) => `${TOOL_LABEL[n] ?? n}${k > 1 ? ` ×${k}` : ""}`).join(", ");
}

function regret(b: { regret_xpts: number; regret_ci90: [number, number]; best_response: string; choice: string }) {
  return b.regret_xpts === 0 && b.best_response === b.choice
    ? "regret 0 xPts: it was the best answer to what the other bench did"
    : `regret ${b.regret_xpts} xPts (likely range ${ci(b.regret_ci90)}) vs ${b.best_response}`;
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="fd-tile">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export function FoundryRunPanel({ run, colors, names = {} }: {
  run: Run;
  colors: Record<string, string>;
  names?: Record<string, string>;
}) {
  const name = (club: string) => names[club] ?? club;
  const t = run.totals;
  const date = run.run.started_utc.slice(0, 10);
  const clubs = Object.keys(run.halftime.benches);
  const toolsBy = (club: string) => run.turns.filter((x) => x.club === club && x.tools.length);
  return (
    <div className="foundry" aria-label="Real Microsoft Foundry Run">
      <header className="fd-head">
        <div>
          <span className="fd-badge">Real model calls · {date}</span>
          <h3>Real Microsoft Foundry Run</h3>
          <p className="fd-sub">
            The same agents, MCP tools and validators, run with <b>{run.run.model.join(", ")}</b> on Microsoft Foundry,
            on this match's data and its 1-1 half-time.
          </p>
        </div>
        <div className="fd-modes">
          <p className="fd-mode real"><b>This tab</b>a recorded run with real calls to a model in Microsoft Foundry</p>
          <p className="fd-mode replay"><b>Rest of the site</b>a deterministic replay of the same agents (offline rules),
            so every number can be re-checked</p>
        </div>
      </header>

      <div className="fd-tiles">
        <Tile label="Model" value={run.run.model.join(", ")} note="Global Standard deployment" />
        <Tile label="Model turns" value={String(t.model_turns)}
              note={`${t.with_service_response_id} of ${t.model_turns} answered with a service response id`} />
        <Tile label="Tokens" value={`${fmt(t.input_tokens)} in`} note={`${fmt(t.output_tokens)} out · same as Azure Monitor`} />
        <Tile label="Tool calls the model chose" value={String(t.tool_calls_by_model)} note="through each club's own MCP server" />
        <Tile label="Demo match" value={run.run.demo_bundle_unchanged ? "unchanged ✓" : "CHANGED"}
              note={`bundle sha256 ${run.run.demo_bundle_sha256.slice(0, 10)}…`} />
      </div>

      <div className="fd-grid">
        <section className="fd-card">
          <h4>What the agents decided to look up</h4>
          <p className="fd-note">Beyond the workflow's own calls, the model itself asked its club's MCP server for:</p>
          {clubs.map((club) => (
            <div key={club} className="fd-tools">
              <b style={{ color: colors[club] }}>{name(club)}</b>
              {toolsBy(club).map((turn) => (
                <span key={turn.response_id ?? turn.output} className="fd-chip">
                  {turn.role}: {tools(turn.tools)}
                </span>
              ))}
              {toolsBy(club).length === 0 && <span className="fd-chip muted">no extra calls</span>}
            </div>
          ))}
        </section>

        <section className="fd-card">
          <h4>Guardrails at work</h4>
          <p className="fd-note">The validators rejected these drafts; the agent had to fix them within the retry limit.</p>
          <ul className="fd-guards">
            {run.guardrails.map((g) => (
              <li key={`${g.club}-${g.item}`}>
                <div className="fd-guard-head">
                  <b style={{ color: colors[g.club] }}>{name(g.club)}</b> {g.agent} · {g.item}
                  <span className={`fd-pill ${g.outcome.includes("discarded") ? "bad" : "good"}`}>{g.outcome}</span>
                </div>
                <span className="fd-why">rejected because it {[...new Set(g.rejections.map((r) => r.plain))].join("; ")}</span>
                <details><summary>validator messages</summary>
                  <ul>{g.rejections.map((r) => <li key={r.message}><code>{r.message}</code></li>)}</ul>
                </details>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="fd-card wide">
        <h4>Half-time decisions on the same {Object.values(run.halftime.score).join("-")}</h4>
        <p className="fd-note">
          Both runs start from the identical half-time state (plans, score, tactics in force and every first-half event
          checked equal). Each regret is measured against what the other bench chose in that run.
        </p>
        <div className="fd-benches">
          {clubs.map((club) => {
            const b = run.halftime.benches[club];
            return (
              <div key={club} className="fd-bench" style={{ borderTopColor: colors[club] }}>
                <h5 style={{ color: colors[club] }}>{name(club)}'s bench</h5>
                <div className="fd-cols">
                  <div className="fd-col real">
                    <span className="fd-tag">Foundry agents</span>
                    <strong>{b.foundry.choice}</strong>
                    <small>options proposed: {b.foundry.options.map((o) => o.label).join(" · ")}</small>
                    <small>{regret(b.foundry)}</small>
                  </div>
                  <div className="fd-col replay">
                    <span className="fd-tag">Offline demo</span>
                    <strong>{b.demo.choice}</strong>
                    <small>options: {b.demo.options.join(" · ")}</small>
                    <small>{regret(b.demo)}</small>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="fd-card wide">
        <h4>Pre-match plans (compared, not played)</h4>
        <table className="kpi-table">
          <thead><tr><th>club</th><th>Foundry agents' plan</th><th>offline demo plan</th><th>seal</th><th>report attempts</th></tr></thead>
          <tbody>
            {Object.entries(run.plans).map(([club, p]) => (
              <tr key={club}><td style={{ color: colors[club] }}>{name(club)}</td><td>{p.foundry_plan}</td><td>{p.demo_plan}</td>
                <td>{p.seal_verifies ? "verifies" : "fails"}</td><td>{p.report_attempts}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      {run.comparison && (
        <section className="fd-card wide" id="fd-comparison">
          <h4>{run.comparison.title}</h4>
          <p className="fd-note">{run.comparison.design}</p>
          <table className="kpi-table">
            <thead><tr><th>measure</th><th>rule agents</th><th>Foundry agents</th><th>difference (90% CI)</th><th></th></tr></thead>
            <tbody>
              {run.comparison.rows.map((r) => (
                <tr key={r.metric}>
                  <td>{r.metric}</td>
                  <td>{r.rules.value}{r.rules.ci90 ? ` (${ci(r.rules.ci90)})` : ""}</td>
                  <td>{r.llm.value}{r.llm.ci90 ? ` (${ci(r.llm.ci90)})` : ""}</td>
                  <td>{r.diff.value > 0 ? "+" : ""}{r.diff.value} ({ci(r.diff.ci90)})</td>
                  <td className={r.significant ? "at_risk" : ""}>{r.significant ? "significant" : "not significant"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="legend">{run.comparison.note} {run.comparison.calls} model turns, about €{run.comparison.cost_eur} of
            credit. Full report: <code>{run.comparison.report}</code></p>
        </section>
      )}

      <details className="fd-card wide fd-calls">
        <summary>Every model call ({run.turns.length})</summary>
        <table className="trace">
          <thead><tr><th>phase</th><th>club</th><th>agent</th><th>output</th><th>service model</th><th>response id</th><th>tokens in / out</th><th>tools the model called</th></tr></thead>
          <tbody>
            {run.turns.map((x) => (
              <tr key={x.response_id ?? `${x.club}-${x.ms}`}>
                <td>{x.phase}</td><td>{name(x.club)}</td><td>{x.role}</td><td>{x.output}</td><td>{x.service_model ?? "–"}</td>
                <td><code title={x.response_id ?? ""}>{x.response_id ? `${x.response_id.slice(0, 14)}…` : "–"}</code></td>
                <td>{x.input_tokens ?? "–"} / {x.output_tokens ?? "–"}</td><td>{x.tools.join(", ") || "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="legend">Source: <code>{run.sources.evidence}</code> (sha256 {run.sources.evidence_sha256.slice(0, 12)}…),
          endpoint {run.run.endpoint_domain}. No keys, tenant or subscription ids are recorded.</p>
      </details>
    </div>
  );
}
