// Analyst desk: scouting reports with evidence, plans, KPIs, agent traces, matrix comparison, validation panel.
import { useEffect, useState } from "react";
import type { MatchBundle } from "../contracts/bundle";
import { type ClaimIndex, fill } from "../lib/claims";
import { kpiLabel } from "../lib/levers";
import { type FoundryRun, loadFoundryRun } from "../lib/foundry";
import { DuelMatrix } from "./Duel";
import { FoundryRunPanel } from "./FoundryRun";
import type { Lang } from "./Overlays";

function ClaimRow({ id, claims }: { id: string; claims: ClaimIndex }) {
  const c = claims.get(id);
  if (!c) return <li className="missing">{id} (not in bundle)</li>;
  return (
    <li>
      <code>{c.claim_id}</code> {c.metric.replaceAll("_", " ")}: <strong>{String(c.value)}</strong>
      {c.league_ref !== null && c.league_ref !== undefined && <> vs ref {c.league_ref}</>}
      {c.n !== null && c.n !== undefined && <> · n {c.n}</>}
      {c.interval_low !== null && c.interval_low !== undefined && <> · [{c.interval_low}, {c.interval_high}]</>}
      {c.status === "insufficient" && <em> · insufficient</em>}
      {c.label && <> · {c.label}</>}
    </li>
  );
}

export function AnalystDesk({ bundle, claims, minute, lang, colors, section = null }: {
  bundle: MatchBundle;
  claims: ClaimIndex;
  minute: number;
  lang: Lang;
  colors: Record<string, string>;
  section?: "validation" | "trace" | "foundry" | null;
}) {
  const first = (name: "validation" | "trace") => (section === name ? { order: -1 } : undefined);  // deep-link focus
  const [team, setTeam] = useState(bundle.meta.home);
  const [view, setView] = useState<"club" | "foundry">(section === "foundry" ? "foundry" : "club");
  const [run, setRun] = useState<FoundryRun | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  useEffect(() => {  // the recorded Foundry run is a separate file, loaded only when its tab is opened
    if (view === "foundry" && !run && !runError) loadFoundryRun().then(setRun, (e: Error) => setRunError(e.message));
  }, [view, run, runError]);
  const report = bundle.scouting[team];
  const plan = bundle.plans[team];
  const snap = bundle.snapshots[Math.min(minute, bundle.snapshots.length - 1)];
  const traces = bundle.traces.filter((t) => t.scope === team);
  const ev = bundle.eval as Record<string, any>;
  return (
    <div className="desk">
      <div className="desk-tabs" role="tablist">
        {[bundle.meta.home, bundle.meta.away].map((t) => (
          <button key={t} type="button" role="tab" aria-selected={view === "club" && t === team}
                  className={view === "club" && t === team ? "on" : ""}
                  style={{ borderBottomColor: colors[t] }} onClick={() => { setTeam(t); setView("club"); }}>
            {bundle.squads.teams[t].name}
          </button>
        ))}
        <button type="button" role="tab" aria-selected={view === "foundry"} className={`fd-tab ${view === "foundry" ? "on" : ""}`}
                onClick={() => setView("foundry")}>
          Real Microsoft Foundry Run
        </button>
      </div>
      {view === "foundry" ? (
        run ? <FoundryRunPanel run={run} colors={colors}
                               names={Object.fromEntries(Object.entries(bundle.squads.teams).map(([c, t]) => [c, t.short_name]))} />
          : <p className="fd-loading">{runError ? `The recorded run could not be loaded: ${runError}` : "Loading the recorded run…"}</p>
      ) : (
      <div className="desk-grid">
        <section>
          <h3>Scouting report {report ? `· ${report.model}` : ""}</h3>
          {report?.findings.map((f) => (
            <div key={f.claim_id} className="finding">
              <p>{fill(f.headline, claims)}</p>
              <ul className="evidence"><ClaimRow id={f.claim_id} claims={claims} /></ul>
            </div>
          ))}
          {report?.opponent_estimate && (
            <p className="estimate">
              Expected opponent levers:{" "}
              {Object.entries(report.opponent_estimate.levers).map(([k, v]) => `${k} ${v ?? "none"}`).join(" · ")}
            </p>
          )}
        </section>
        <section>
          <h3>Sealed plan · {plan.name[lang]}</h3>
          <ul className="evidence">
            {Object.entries(plan.lever_evidence).map(([lever, ids]) => (
              <li key={lever}>
                <strong>{lever}</strong> = {String((plan.levers as unknown as Record<string, unknown>)[lever])}
                <ul>{ids.map((id) => <ClaimRow key={id} id={id} claims={claims} />)}</ul>
              </li>
            ))}
            {plan.valuation && <ClaimRow id={plan.valuation} claims={claims} />}
          </ul>
          <h3>KPIs at {minute}'</h3>
          <table className="kpi-table">
            <thead><tr><th>KPI</th><th>value</th><th>expected</th><th>band</th><th>n</th><th>status</th></tr></thead>
            <tbody>
              {snap?.kpis.filter((k) => k.team === team).map((k) => (
                <tr key={k.kpi_id}>
                  <td>{(() => { const def = plan.kpis.find((x) => x.id === k.kpi_id); return def ? kpiLabel(def) : k.kpi_id; })()}</td>
                  <td>{k.value}</td><td>{k.expected ?? "–"}</td>
                  <td>{k.band_low}–{k.band_high}</td><td>{k.n}</td><td className={k.status}>{k.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="wide" id="desk-trace" style={first("trace")}>
          <h3>Agent trace ({traces.length} steps)</h3>
          <table className="trace">
            <thead><tr><th>#</th><th>workflow</th><th>agent</th><th>tool / model</th><th>status</th><th>claims</th><th>ms</th></tr></thead>
            <tbody>
              {traces.map((t) => (
                <tr key={t.trace_id} className={t.status}>
                  <td>{t.step}</td><td>{t.workflow}</td><td>{t.agent}</td><td>{t.tool ?? t.message}</td>
                  <td>{t.status}{t.status !== "ok" && t.message ? `: ${t.message}` : ""}</td>
                  <td>{t.result_claims.slice(0, 4).join(", ")}{t.result_claims.length > 4 ? "…" : ""}</td><td>{t.duration_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        {bundle.duel && (
          <section className="wide">
            <h3>Matrices: what {bundle.squads.teams[team].short_name} believed vs reality</h3>
            <div className="two">
              <DuelMatrix bundle={bundle} matrix={bundle.duel.private[team].believed_matrix} perspective={team} mode="analyst"
                          lang={lang} claims={claims} colors={colors} />
              <DuelMatrix bundle={bundle} matrix={bundle.duel.broadcast.true_matrix} perspective={team} mode="analyst"
                          lang={lang} claims={claims} colors={colors} />
            </div>
          </section>
        )}
        <section className="wide" id="desk-validation" style={first("validation")}>
          <h3>Validation panel (inside our simulator)</h3>
          {ev?.E1 ? (
            <ul className="eval">
              <li>E1 scouting vs hidden truth ({ev.E1.scouted_teams} clubs in {ev.E1.seasons?.length} unseen seasons with random trait kinds): precision {ev.E1.precision}, recall {ev.E1.recall} ({ev.E1.flagged} flagged, {ev.E1.true_traits} real traits)</li>
              <li>E2 Monte Carlo stability (R={ev.E2.R?.join(" vs ")}): sign agreement {ev.E2.sign_agreement}, mean abs error {ev.E2.mean_abs_error_xpts} xPts, CI coverage {ev.E2.ci90_coverage_of_reference}</li>
              <li>E3 levers citing served claims: {ev.E3.levers_citing_served_claims}; plans attacking a real weakness: {ev.E3.plans_attacking_a_real_weakness}</li>
              <li>E4 reports valid at first try: {ev.E4.reports_valid_first_try}; cues dropped by the verifier: {ev.E4.cues_dropped}; numbers written by the LLM: {ev.E4.llm_numbers}</li>
              <li>E7 probability on the other bench's real intent: {ev.E7.prob_on_actual_intent.mean} (uniform {ev.E7.uniform_baseline}, n {ev.E7.prob_on_actual_intent.n})</li>
              <li>E8 regret (xPts): AI {ev.E8.ai_regret.mean} [{ev.E8.ai_regret.ci90.join(", ")}] · always stay {ev.E8.always_stay_regret.mean} · random {ev.E8.random_choice_regret.mean}</li>
              {ev.adaptation_detector && (
                <li>Adaptation detector (dev seasons, online): false alarms {ev.adaptation_detector.chosen.false_alarm_rate} per team-match, switches found {ev.adaptation_detector.chosen.power}, median delay {ev.adaptation_detector.chosen.median_delay_min} min</li>
              )}
            </ul>
          ) : (
            <p>{ev?.note ?? "No evaluation in this bundle."}</p>
          )}
          {ev?.calibration && (
            <table className="kpi-table calib">
              <caption>Season statistics of our simulator vs targets (evaluation season {ev.season_seed})</caption>
              <thead><tr><th>statistic</th><th>value</th><th>target</th><th>in range</th></tr></thead>
              <tbody>
                {Object.entries(ev.calibration as Record<string, { value: number; target: number[]; in_range: boolean }>).map(([k, v]) => (
                  <tr key={k}><td>{k.replaceAll("_", " ")}</td><td>{v.value}</td><td>{v.target.join("–")}</td>
                    <td className={v.in_range ? "on_track" : "at_risk"}>{v.in_range ? "yes" : "no"}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {ev?.story && <p className="legend">Demo story criteria: {ev.story_criteria}</p>}
        </section>
      </div>
      )}
    </div>
  );
}
