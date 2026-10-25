// Broadcast overlays: settings, timed cues, Plan Tracker lower third.
import type { Cue, MatchBundle } from "../contracts/bundle";
import { type ClaimIndex, fill } from "../lib/claims";
import { kpiLabel } from "../lib/levers";

export type Mode = "casual" | "analyst";
export type Lang = "en" | "es";

export interface Settings {
  mode: Mode;
  lang: Lang;
  club: string;
}

export function SettingsBar({ bundle, settings, onChange }: {
  bundle: MatchBundle;
  settings: Settings;
  onChange: (s: Settings) => void;
}) {
  const codes = [bundle.meta.home, bundle.meta.away];
  return (
    <div className="settings" role="group" aria-label="Viewer settings">
      <label>
        View
        <select value={settings.mode} onChange={(e) => onChange({ ...settings, mode: e.target.value as Mode })}>
          <option value="casual">Fan</option>
          <option value="analyst">Analyst</option>
        </select>
      </label>
      <label>
        Language
        <select value={settings.lang} onChange={(e) => onChange({ ...settings, lang: e.target.value as Lang })}>
          <option value="en">English</option>
          <option value="es">Español</option>
        </select>
      </label>
      <label>
        Your club
        <select value={settings.club} onChange={(e) => onChange({ ...settings, club: e.target.value })}>
          {codes.map((c) => (
            <option key={c} value={c}>{bundle.squads.teams[c].short_name}</option>
          ))}
        </select>
      </label>
    </div>
  );
}

export function cueSeconds(c: Cue): number {
  const [m, s] = c.t_match.split(":").map(Number);
  return m * 60 + s;
}

/** Cues visible at `time`: start <= time < start + ttl (in match seconds at the default 30x playback). */
export function activeCues(cues: Cue[], time: number, mode: Mode, exclude: string[] = []): Cue[] {
  return cues.filter((c) => {
    const start = cueSeconds(c);
    return c.mode.includes(mode) && !exclude.includes(c.template) && time >= start && time < start + c.ttl_s * 30;
  });
}

export function CueStack({ cues, claims, lang, colors }: {
  cues: Cue[];
  claims: ClaimIndex;
  lang: Lang;
  colors: Record<string, string>;
}) {
  if (cues.length === 0) return null;
  return (
    <div className="cue-stack" aria-live="polite">
      {cues.slice(-3).map((c) => (
        <div key={c.cue_id} className={`cue cue-${c.template}`} style={{ borderLeftColor: c.team ? colors[c.team] : "#fff" }}>
          <span className="cue-tag">{c.template.replaceAll("_", " ")}</span>
          <p>{fill(c.text[lang], claims)}</p>
        </div>
      ))}
    </div>
  );
}

const STATUS_LABEL: Record<string, { en: string; es: string; icon: string }> = {
  on_track: { en: "on track", es: "en camino", icon: "✓" },
  at_risk: { en: "at risk", es: "en riesgo", icon: "!" },
  failing: { en: "failing", es: "fallando", icon: "✕" },
  insufficient_evidence: { en: "too early", es: "pronto", icon: "…" },
};

export function PlanTrackerLT({ bundle, minute, mode, lang, colors }: {
  bundle: MatchBundle;
  minute: number;
  mode: Mode;
  lang: Lang;
  colors: Record<string, string>;
}) {
  const snap = bundle.snapshots[Math.min(minute, bundle.snapshots.length - 1)];
  if (!snap || snap.kpis.length === 0) return null;
  return (
    <div className="tracker" aria-label="Plan Tracker">
      {[bundle.meta.home, bundle.meta.away].map((team) => (
        <div key={team} className="tracker-team" style={{ borderTopColor: colors[team] }}>
          <strong>{bundle.squads.teams[team].short_name}</strong>
          {snap.kpis.filter((k) => k.team === team).map((k) => {
            const kpi = bundle.plans[team].kpis.find((x) => x.id === k.kpi_id);
            const st = STATUS_LABEL[k.status];
            return (
              <span key={k.kpi_id} className={`kpi ${k.status}`} data-testid={`kpi-${team}-${k.kpi_id}`}>
                <b>{st.icon}</b> {kpi ? kpiLabel(kpi) : k.kpi_id} · {st[lang]}
                {mode === "analyst" && (
                  <small> {fmt(k.value, kpi?.metric)} (exp. {k.expected === null ? "–" : fmt(k.expected, kpi?.metric)}, n {k.n})</small>
                )}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function fmt(v: number | null | undefined, metric?: string): string {
  if (v === null || v === undefined) return "–";
  if (metric?.endsWith("_share")) return `${Math.round(v * 100)}%`;
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}
