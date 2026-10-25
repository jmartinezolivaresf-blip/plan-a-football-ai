// The Duel at half-time: two rooms deciding blind, locked choices, the reveal, and what each bench believed next
// to what was really true. Full time: what each plan and each call was worth.
import { useEffect, useState } from "react";
import type { MatchBundle, Matrix, Option } from "../contracts/bundle";
import { type ClaimIndex, fill } from "../lib/claims";
import { kpiLabel, kpiTarget } from "../lib/levers";
import { bestResponseRow, deltas, view } from "../lib/duel";
import { type SealState, verifyChoice } from "../lib/seal";
import type { Lang, Mode } from "./Overlays";

function optionMap(bundle: MatchBundle): Map<string, Option> {
  const m = new Map<string, Option>();
  for (const priv of Object.values(bundle.duel?.private ?? {})) {
    for (const o of priv.options) m.set(o.option_id, o);
    for (const e of priv.opponent_estimate.options) m.set(e.option.option_id, e.option);
  }
  return m;
}

const RULE_TEXT: Record<string, { en: string; es: string }> = {
  safe_pick: { en: "the safest option on what they believed", es: "la opción más segura según lo que creían" },
  best_guess: { en: "the best option against their guess of the other bench", es: "la mejor opción contra su estimación del rival" },
  gamble: { en: "a calculated risk", es: "un riesgo calculado" },
};

function ChoiceSeal({ bundle, team, revealed, lang }: { bundle: MatchBundle; team: string; revealed: boolean; lang: Lang }) {
  const duel = bundle.duel!;
  const sealed = duel.private[team].choice;
  const reveal = duel.broadcast.revealed[team];
  const [state, setState] = useState<SealState>("verifying");
  useEffect(() => {
    if (!revealed) return;
    verifyChoice(sealed.sha256, duel.match_id, team, reveal.option_id, reveal.salt).then(setState, () =>
      setState("unavailable"));
  }, [revealed, sealed.sha256, duel.match_id, team, reveal.option_id, reveal.salt]);
  const text = !revealed
    ? (lang === "en" ? "🔒 Choice locked in" : "🔒 Decisión bloqueada")
    : state === "verified" ? (lang === "en" ? "✓ Matches the locked choice" : "✓ Coincide con la decisión bloqueada")
      : state === "mismatch" ? "✕ seal mismatch" : "…";
  return (
    <span className={`seal ${revealed ? state : "locked"}`} data-testid={`choice-seal-${team}`}>
      {text}<code>{sealed.sha256.slice(0, 10)}…</code>
    </span>
  );
}

export function DuelRooms({ bundle, revealed, lang, colors }: {
  bundle: MatchBundle;
  revealed: boolean;
  lang: Lang;
  mode?: Mode;
  colors: Record<string, string>;
}) {
  const duel = bundle.duel!;
  return (
    <div className="rooms">
      {[bundle.meta.home, bundle.meta.away].map((team) => {
        const priv = duel.private[team];
        const choice = duel.broadcast.revealed[team];
        return (
          <section key={team} className={`room ${revealed ? "revealed" : ""}`} style={{ borderTopColor: colors[team] }}
                   aria-label={`${team} room`}>
            <h3 style={{ color: colors[team] }}>
              {lang === "en" ? `${bundle.squads.teams[team].short_name}'s bench` : `Banquillo de ${bundle.squads.teams[team].short_name}`}
            </h3>
            <ol>
              {priv.options.map((o) => {
                const chosen = revealed && o.option_id === choice.option_id;
                return (
                  <li key={o.option_id} className={chosen ? "chosen" : revealed ? "not-chosen" : ""}>
                    <span>{o.label[lang]}</span>
                    {chosen && <span className="pill" style={{ background: colors[team] }}>{lang === "en" ? "CHOSEN" : "ELEGIDA"}</span>}
                  </li>
                );
              })}
            </ol>
            {revealed && <p className="why">{lang === "en" ? "Why: " : "Por qué: "}{RULE_TEXT[choice.rule]?.[lang] ?? choice.rule}</p>}
            <p className="estimate">
              {lang === "en" ? "Their guess of the other bench: " : "Su estimación del rival: "}
              {priv.opponent_estimate.options.map((e) => `${e.option.label[lang]} ${Math.round(e.probability * 100)}%`).join(" · ")}
            </p>
            <ChoiceSeal bundle={bundle} team={team} revealed={revealed} lang={lang} />
          </section>
        );
      })}
    </div>
  );
}

export function DuelMatrix({ bundle, matrix, perspective, mode, lang, colors, title }: {
  bundle: MatchBundle;
  matrix: Matrix;
  perspective: string;
  mode: Mode;
  lang: Lang;
  claims?: ClaimIndex;
  colors: Record<string, string>;
  title?: string;
}) {
  const v = view(matrix, perspective);
  const d = deltas(v);
  const opts = optionMap(bundle);
  const reading = matrix.readings[perspective];
  const duel = bundle.duel!;
  const opp = perspective === matrix.row_team ? matrix.col_team : matrix.row_team;
  const isTrue = matrix.kind === "true";
  const chosenOwn = duel.broadcast.revealed[perspective].option_id;
  const chosenOpp = isTrue ? duel.broadcast.revealed[opp].option_id : null;
  const oppCol = chosenOpp ? v.opp.indexOf(chosenOpp) : -1;
  const bestRow = oppCol >= 0 ? bestResponseRow(v, oppCol) : -1;
  const max = Math.max(0.05, ...d.flat().map(Math.abs));
  const color = (x: number) => {
    const a = Math.min(1, Math.abs(x) / max);
    return x >= 0 ? `rgba(45, 212, 191, ${0.15 + 0.6 * a})` : `rgba(248, 113, 113, ${0.15 + 0.6 * a})`;
  };
  const label = (id: string) => opts.get(id)?.label[lang] ?? id;
  const me = bundle.squads.teams[perspective].short_name;
  const them = bundle.squads.teams[opp].short_name;
  const caption = title ?? (isTrue ? (lang === "en" ? "What was really true" : "Lo que era cierto")
    : (lang === "en" ? `What ${bundle.squads.teams[matrix.believer!].short_name} believed` : `Lo que creía ${bundle.squads.teams[matrix.believer!].short_name}`));
  return (
    <figure className={`duel-matrix ${isTrue ? "true" : "believed"}`} aria-label="Duel matrix">
      <figcaption>
        <strong>{caption}</strong>
        <span>
          {lang === "en"
            ? ` · expected points for ${me} compared with both benches staying the course`
            : ` · puntos esperados para ${me} frente a que ninguno cambie`}
          {mode === "analyst" ? ` · R=${matrix.R}` : ""}
        </span>
      </figcaption>
      <table>
        <thead>
          <tr>
            <th className="corner">
              <span style={{ color: colors[perspective] }}>{lang === "en" ? `${me} chooses ↓` : `${me} elige ↓`}</span>
              <span style={{ color: colors[opp] }}>{isTrue ? (lang === "en" ? `${them} chooses →` : `${them} elige →`) : (lang === "en" ? `${me}'s guess of ${them} →` : `Lo que ${me} esperaba de ${them} →`)}</span>
            </th>
            {v.opp.map((id) => (
              <th key={id} className={id === chosenOpp ? "picked" : ""} style={id === chosenOpp ? { color: colors[opp] } : undefined}>
                {label(id)}{id === chosenOpp && <small>{lang === "en" ? `${them}'s choice` : `elección de ${them}`}</small>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {v.own.map((id, i) => (
            <tr key={id}>
              <th className={id === chosenOwn ? "picked" : ""} style={id === chosenOwn ? { color: colors[perspective] } : undefined}>
                {label(id)}
                {id === chosenOwn && <small>{lang === "en" ? `${me}'s choice` : `elección de ${me}`}</small>}
                <span className="badges">
                  {reading?.safe_pick === id && <span className="badge safe">SAFE</span>}
                  {reading?.gamble === id && <span className="badge gamble">GAMBLE</span>}
                  {reading?.dominant === id && <span className="badge dominant">{lang === "en" ? "BEST WHATEVER THEY DO" : "MEJOR HAGAN LO QUE HAGAN"}</span>}
                </span>
              </th>
              {v.opp.map((oid, j) => {
                const happened = id === chosenOwn && oid === chosenOpp;
                const best = j === oppCol && i === bestRow && !happened;
                return (
                  <td key={oid} style={{ background: color(d[i][j]) }}
                      className={`${happened ? "happened" : ""} ${best ? "best-answer" : ""}`}
                      data-testid={`cell-${i}-${j}`} title={v.claim[i][j] ?? ""}>
                    <strong>{d[i][j] >= 0 ? "+" : ""}{d[i][j].toFixed(2)}</strong>
                    {mode === "analyst" && <small>{v.ci[i][j][0].toFixed(2)}–{v.ci[i][j][1].toFixed(2)} xPts</small>}
                    {happened && <span className="mark">{lang === "en" ? "◎ what happened" : "◎ lo que pasó"}</span>}
                    {best && <span className="mark">{lang === "en" ? "★ best answer" : "★ mejor respuesta"}</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export function HalftimeScreen({ bundle, mode, lang, club, claims, colors, onContinue, initialRevealed = false,
                                 initialMatrix = "true" }: {
  bundle: MatchBundle;
  mode: Mode;
  lang: Lang;
  club: string;
  claims: ClaimIndex;
  colors: Record<string, string>;
  onContinue: () => void;
  initialRevealed?: boolean;
  initialMatrix?: "true" | "believed";
}) {
  const [revealed, setRevealed] = useState(initialRevealed);
  const duel = bundle.duel;
  if (!duel) return null;
  const [home, away] = [bundle.meta.home, bundle.meta.away];
  const ht = bundle.snapshots[Math.min(45, bundle.snapshots.length - 1)].score;
  const name = (t: string) => bundle.squads.teams[t].short_name;
  const regretCue = bundle.cues.find((c) => c.template === "bench_regret" && c.team === club);
  return (
    <div className="halftime" role="dialog" aria-label="Half-time duel">
      <header className="ht-head">
        <div>
          <p className="kicker">{lang === "en" ? "Half-time · The Duel" : "Descanso · El duelo"}</p>
          <h2>
            <span style={{ color: colors[home] }}>{name(home)}</span> {ht[home]} – {ht[away]}{" "}
            <span style={{ color: colors[away] }}>{name(away)}</span>
          </h2>
        </div>
        <p className="ht-sub">
          {lang === "en"
            ? "Both benches choose at the same time from three options. Neither can see the other's options. Each choice is locked in before the reveal."
            : "Los dos banquillos eligen a la vez entre tres opciones, sin ver las del rival. Cada decisión queda bloqueada antes de revelarla."}
        </p>
      </header>
      <DuelRooms bundle={bundle} revealed={revealed} lang={lang} mode={mode} colors={colors} />
      {!revealed ? (
        <button type="button" className="primary big" onClick={() => setRevealed(true)}>
          {lang === "en" ? "Reveal both choices" : "Revelar las dos decisiones"}
        </button>
      ) : (
        <>
          <div className={`ht-matrices ${initialMatrix === "believed" ? "focus-believed" : "focus-true"}`}>
            <DuelMatrix bundle={bundle} matrix={duel.private[club].believed_matrix} perspective={club} mode={mode}
                        lang={lang} claims={claims} colors={colors} />
            <DuelMatrix bundle={bundle} matrix={duel.broadcast.true_matrix} perspective={club} mode={mode} lang={lang}
                        claims={claims} colors={colors} />
          </div>
          <p className="legend">
            {lang === "en"
              ? "Green: better for the selected club than both staying; red: worse. ◎ the pair of choices that really happened · ★ the best answer to what the other bench really chose. Values from our simulator."
              : "Verde: mejor para el club elegido que si ninguno cambia; rojo: peor. ◎ lo que pasó · ★ la mejor respuesta a lo que eligió el rival. Valores de nuestro simulador."}
          </p>
          <div className="ht-foot">
            {regretCue && <p className="verdict" style={{ borderLeftColor: colors[club] }}>{fill(regretCue.text[lang], claims)}</p>}
            <button type="button" className="primary" onClick={onContinue}>
              {lang === "en" ? "Play the second half" : "Jugar la segunda parte"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function FinalPanel({ bundle, lang, mode, claims, colors }: {
  bundle: MatchBundle;
  lang: Lang;
  mode: Mode;
  claims: ClaimIndex;
  colors: Record<string, string>;
}) {
  const last = bundle.snapshots[bundle.snapshots.length - 1];
  const ht = bundle.snapshots[Math.min(45, bundle.snapshots.length - 1)].score;
  const [home, away] = [bundle.meta.home, bundle.meta.away];
  const name = (t: string) => bundle.squads.teams[t].short_name;
  const opts = optionMap(bundle);
  const cueFor = (template: string, team: string) => bundle.cues.find((c) => c.template === template && c.team === team);
  return (
    <div className="final" aria-label="Full time">
      <header className="ht-head">
        <div>
          <p className="kicker">{lang === "en" ? "Full time · Whose plan won?" : "Final · ¿Qué plan ganó?"}</p>
          <h2>
            <span style={{ color: colors[home] }}>{name(home)}</span> {last.score[home]} – {last.score[away]}{" "}
            <span style={{ color: colors[away] }}>{name(away)}</span>
          </h2>
          <p className="ht-sub">{lang === "en" ? `Half-time ${ht[home]}–${ht[away]}` : `Descanso ${ht[home]}–${ht[away]}`}</p>
        </div>
        <ol className="goal-line" aria-label={lang === "en" ? "Goals" : "Goles"}>
          {bundle.events.filter((e) => e.type === "goal").map((e) => (
            <li key={e.event_id} style={{ borderColor: colors[e.team] }}>
              <b>{e.minute}'</b> {name(e.team)}
            </li>
          ))}
        </ol>
      </header>
      <div className="recap">
        {[home, away].map((team) => {
          const plan = bundle.plans[team];
          const choice = bundle.duel?.broadcast.revealed[team];
          const score = cueFor("plan_scorecard", team);
          const regret = cueFor("bench_regret", team);
          return (
            <section key={team} className="recap-card" style={{ borderTopColor: colors[team] }}>
              <h3 style={{ color: colors[team] }}>{bundle.squads.teams[team].name}</h3>
              <dl>
                <dt>{lang === "en" ? "Sealed plan" : "Plan sellado"}</dt><dd>{plan.name[lang]}</dd>
                {score && <><dt>KPIs</dt><dd>{fill(score.text[lang], claims).split(": ").slice(1).join(": ")}</dd></>}
                {choice && <><dt>{lang === "en" ? "Half-time call" : "Decisión al descanso"}</dt><dd>{opts.get(choice.option_id)?.label[lang]}</dd></>}
              </dl>
              <ul className="kpi-verdicts">
                {last.kpis.filter((k) => k.team === team).map((k) => {
                  const def = plan.kpis.find((x) => x.id === k.kpi_id);
                  const met = k.status === "on_track";
                  return (
                    <li key={k.kpi_id} className={met ? "met" : "missed"}>
                      <b>{met ? "✓" : "✕"}</b> {def ? kpiLabel(def) : k.kpi_id} <span>{def ? kpiTarget(def) : ""}</span>
                    </li>
                  );
                })}
              </ul>
              {regret && <p className="verdict" style={{ borderLeftColor: colors[team] }}>{fill(regret.text[lang], claims)}</p>}
            </section>
          );
        })}
      </div>
      <p className="legend">
        {lang === "en"
          ? "One replay is an anecdote. The matrix compares every pair of choices on the same simulated second halves; that comparison, not the final score, judges the call."
          : "Una repetición es una anécdota. La matriz compara cada pareja de decisiones sobre las mismas segundas partes simuladas; esa comparación, no el resultado, juzga la decisión."}
        {mode === "analyst" ? (lang === "en" ? " Intervals: analyst desk." : " Intervalos: mesa de análisis.") : ""}
      </p>
    </div>
  );
}
