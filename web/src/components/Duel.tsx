// The Duel at half-time: two rooms deciding blind, seals, reveal and the payoff matrix.
import { useEffect, useState } from "react";
import type { MatchBundle, Matrix, Option } from "../contracts/bundle";
import { type ClaimIndex, fill } from "../lib/claims";
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

function ChoiceSeal({ bundle, team }: { bundle: MatchBundle; team: string }) {
  const duel = bundle.duel!;
  const sealed = duel.private[team].choice;
  const revealed = duel.broadcast.revealed[team];
  const [state, setState] = useState<SealState>("verifying");
  useEffect(() => {
    verifyChoice(sealed.sha256, duel.match_id, team, revealed.option_id, revealed.salt).then(setState, () =>
      setState("unavailable"));
  }, [sealed.sha256, duel.match_id, team, revealed.option_id, revealed.salt]);
  return (
    <span className={`seal ${state}`} data-testid={`choice-seal-${team}`}>
      {state === "verified" ? "✓ choice seal verified" : state === "mismatch" ? "✕ seal mismatch" : "● sealed"}
      <code>{sealed.sha256.slice(0, 10)}…</code>
    </span>
  );
}

export function DuelRooms({ bundle, revealed, lang, mode, colors }: {
  bundle: MatchBundle;
  revealed: boolean;
  lang: Lang;
  mode: Mode;
  colors: Record<string, string>;
}) {
  const duel = bundle.duel!;
  return (
    <div className="rooms">
      {[bundle.meta.home, bundle.meta.away].map((team) => {
        const priv = duel.private[team];
        const choice = duel.broadcast.revealed[team];
        return (
          <section key={team} className="room" style={{ borderTopColor: colors[team] }} aria-label={`${team} room`}>
            <h3>{bundle.squads.teams[team].name}</h3>
            <ol>
              {priv.options.map((o) => (
                <li key={o.option_id} className={revealed && o.option_id === choice.option_id ? "chosen" : ""}>
                  {o.label[lang]}
                  {revealed && o.option_id === choice.option_id && <em> · {choice.rule.replace("_", " ")}</em>}
                </li>
              ))}
            </ol>
            {mode === "analyst" && (
              <p className="estimate">
                {lang === "en" ? "Their guess of the other bench: " : "Su estimación del rival: "}
                {priv.opponent_estimate.options.map((e) => `${e.option.label[lang]} ${Math.round(e.probability * 100)}%`).join(" · ")}
              </p>
            )}
            <ChoiceSeal bundle={bundle} team={team} />
          </section>
        );
      })}
    </div>
  );
}

export function DuelMatrix({ bundle, matrix, perspective, mode, lang, claims, colors }: {
  bundle: MatchBundle;
  matrix: Matrix;
  perspective: string;
  mode: Mode;
  lang: Lang;
  claims: ClaimIndex;
  colors: Record<string, string>;
}) {
  const v = view(matrix, perspective);
  const d = deltas(v);
  const opts = optionMap(bundle);
  const reading = matrix.readings[perspective];
  const duel = bundle.duel!;
  const opp = perspective === matrix.row_team ? matrix.col_team : matrix.row_team;
  const isTrue = matrix.kind === "true";
  const chosenOwn = isTrue ? duel.broadcast.revealed[perspective].option_id : null;
  const chosenOpp = isTrue ? duel.broadcast.revealed[opp].option_id : null;
  const max = Math.max(0.05, ...d.flat().map(Math.abs));
  const color = (x: number) => {
    const a = Math.min(1, Math.abs(x) / max);
    return x >= 0 ? `rgba(45, 212, 191, ${0.15 + 0.6 * a})` : `rgba(248, 113, 113, ${0.15 + 0.6 * a})`;
  };
  const label = (id: string) => opts.get(id)?.label[lang] ?? id;
  const cue = bundle.cues.find((c) => c.template === "duel_matrix");
  return (
    <figure className="duel-matrix" aria-label="Duel matrix">
      <figcaption>
        {isTrue ? (lang === "en" ? "The real duel" : "El duelo real") : (lang === "en" ? `${bundle.squads.teams[matrix.believer!].short_name}'s belief` : `Lo que creía ${bundle.squads.teams[matrix.believer!].short_name}`)}
        {" · "}
        {lang === "en" ? `xPts change for ${bundle.squads.teams[perspective].short_name} vs both staying` : `cambio de xPts para ${bundle.squads.teams[perspective].short_name} frente a no tocar nada`}
        {` · R=${matrix.R}`}
      </figcaption>
      <table>
        <thead>
          <tr>
            <th className="corner" style={{ color: colors[perspective] }}>
              {bundle.squads.teams[perspective].short_name} ↓ / {bundle.squads.teams[opp].short_name} →
            </th>
            {v.opp.map((id) => (
              <th key={id} className={id === chosenOpp ? "picked" : ""}>{label(id)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {v.own.map((id, i) => (
            <tr key={id}>
              <th className={id === chosenOwn ? "picked" : ""}>
                {label(id)}
                {reading?.safe_pick === id && <span className="badge safe">SAFE</span>}
                {reading?.gamble === id && <span className="badge gamble">GAMBLE</span>}
                {reading?.dominant === id && <span className="badge dominant">DOMINANT</span>}
              </th>
              {v.opp.map((oid, j) => {
                const best = bestResponseRow(v, j) === i;
                const picked = id === chosenOwn && oid === chosenOpp;
                return (
                  <td key={oid} style={{ background: color(d[i][j]) }} className={`${best ? "best" : ""} ${picked ? "picked-cell" : ""}`}
                      data-testid={`cell-${i}-${j}`} title={v.claim[i][j] ?? ""}>
                    <strong>{d[i][j] >= 0 ? "+" : ""}{d[i][j].toFixed(2)}</strong>
                    {mode === "analyst" && <small>{v.ci[i][j][0].toFixed(2)}–{v.ci[i][j][1].toFixed(2)} xPts</small>}
                    {picked && <span className="crosshair" aria-label="both choices">◎</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {isTrue && cue && <p className="matrix-line">{fill(cue.text[lang], claims)}</p>}
      <p className="legend">
        {lang === "en"
          ? "Bold border: best answer to that column · SAFE: best worst case · ◎: what both benches chose · values from our simulator"
          : "Borde: mejor respuesta a esa columna · SAFE: mejor peor caso · ◎: lo que eligieron ambos · valores de nuestro simulador"}
      </p>
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
  const [which, setWhich] = useState<"true" | "believed">(initialMatrix);
  const duel = bundle.duel;
  if (!duel) return null;
  const matrix = which === "true" ? duel.broadcast.true_matrix : duel.private[club].believed_matrix;
  return (
    <div className="halftime" role="dialog" aria-label="Half-time duel">
      <h2>{lang === "en" ? "Half-time · The Duel" : "Descanso · El duelo"}</h2>
      <p className="ht-sub">
        {lang === "en"
          ? "Both benches chose at the same time, without seeing each other's options. Choices were sealed before the reveal."
          : "Los dos banquillos eligieron a la vez, sin ver las opciones del otro. Las decisiones se sellaron antes de revelarlas."}
      </p>
      <DuelRooms bundle={bundle} revealed={revealed} lang={lang} mode={mode} colors={colors} />
      {!revealed ? (
        <button type="button" className="primary" onClick={() => setRevealed(true)}>
          {lang === "en" ? "Reveal both choices" : "Revelar las dos decisiones"}
        </button>
      ) : (
        <>
          {mode === "analyst" && (
            <div className="toggle">
              <button type="button" className={which === "true" ? "on" : ""} onClick={() => setWhich("true")}>
                {lang === "en" ? "Real matrix" : "Matriz real"}
              </button>
              <button type="button" className={which === "believed" ? "on" : ""} onClick={() => setWhich("believed")}>
                {lang === "en" ? "What your bench believed" : "Lo que creía tu banquillo"}
              </button>
            </div>
          )}
          <DuelMatrix bundle={bundle} matrix={matrix} perspective={club} mode={mode} lang={lang} claims={claims} colors={colors} />
          <button type="button" className="primary" onClick={onContinue}>
            {lang === "en" ? "Play the second half" : "Jugar la segunda parte"}
          </button>
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
  const final = bundle.cues.filter((c) => ["plan_scorecard", "bench_regret", "option_not_taken"].includes(c.template)
    && c.mode.includes(mode));
  const last = bundle.snapshots[bundle.snapshots.length - 1];
  return (
    <div className="final" aria-label="Full time">
      <h2>{lang === "en" ? "Full time · Whose plan won?" : "Final · ¿Qué plan ganó?"}</h2>
      <p className="ft-score">
        {bundle.squads.teams[bundle.meta.home].short_name} {last.score[bundle.meta.home]} – {last.score[bundle.meta.away]}{" "}
        {bundle.squads.teams[bundle.meta.away].short_name}
      </p>
      <ul>
        {final.map((c) => (
          <li key={c.cue_id} style={{ borderLeftColor: c.team ? colors[c.team] : "#fff" }}>{fill(c.text[lang], claims)}</li>
        ))}
      </ul>
      <p className="legend">{lang === "en" ? "One replay is an anecdote; the matrix is the evidence." : "Una repetición es una anécdota; la matriz es la evidencia."}</p>
    </div>
  );
}
