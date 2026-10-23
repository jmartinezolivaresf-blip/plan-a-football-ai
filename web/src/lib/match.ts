// Pure helpers over the match bundle: score, possession and interpolated positions at a match time.
import type { Event, MatchBundle, RenderFrame } from "../contracts/bundle";

export type Score = Record<string, number>;

const ON_BALL = new Set(["pass", "long_ball", "cross", "carry", "shot", "goal_kick", "corner", "kick_off", "throw_in"]);

export function teams(bundle: MatchBundle): [string, string] {
  return [bundle.meta.home, bundle.meta.away];
}

/** Score after every goal event with t <= time. */
export function scoreAt(events: Event[], time: number, codes: [string, string]): Score {
  const score: Score = { [codes[0]]: 0, [codes[1]]: 0 };
  for (const e of events) {
    if (e.t > time) break;
    if (e.type === "goal") score[e.team] = (score[e.team] ?? 0) + 1;
  }
  return score;
}

/** Team in possession: the team of the latest on-ball event at or before `time`. */
export function possessionAt(events: Event[], time: number): string | null {
  let team: string | null = null;
  for (const e of events) {
    if (e.t > time) break;
    if (ON_BALL.has(e.type) || e.type === "possession_change") team = e.team;
  }
  return team;
}

/** Match clock label, e.g. 37' or 45+' is not used: halves end at 45:00 / 90:00 in this data. */
export function minuteLabel(time: number): string {
  const m = Math.floor(time / 60);
  const s = Math.floor(time % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function matchEnd(bundle: MatchBundle): number {
  const last = bundle.events[bundle.events.length - 1];
  return last ? Math.max(last.t, 90 * 60) : 90 * 60;
}

/** Index of the last frame with frame.t <= time (binary search); -1 before the first frame. */
export function frameIndex(frames: RenderFrame[], time: number): number {
  let lo = 0;
  let hi = frames.length - 1;
  let best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t <= time) {
      best = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return best;
}

export interface Positions {
  ball: [number, number];
  players: Record<string, [number, number]>;
}

/** Positions at `time`, linearly interpolated between the surrounding frames (visual layer only). */
export function positionsAt(frames: RenderFrame[], time: number): Positions | null {
  if (frames.length === 0) return null;
  const i = frameIndex(frames, time);
  if (i < 0) return { ball: frames[0].ball as [number, number], players: frames[0].players as Positions["players"] };
  const a = frames[i];
  const b = frames[Math.min(i + 1, frames.length - 1)];
  const span = b.t - a.t;
  const k = span > 0 ? Math.min(1, Math.max(0, (time - a.t) / span)) : 0;
  const lerp = (p: number[], q: number[]): [number, number] => [p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k];
  const players: Positions["players"] = {};
  for (const [id, pos] of Object.entries(a.players)) {
    const next = b.players[id] ?? pos;
    players[id] = lerp(pos as number[], next as number[]);
  }
  return { ball: lerp(a.ball as number[], b.ball as number[]), players };
}

export function playerName(bundle: MatchBundle, playerId: string | null | undefined): string {
  if (!playerId) return "";
  for (const squad of Object.values(bundle.squads.teams)) {
    const p = squad.players.find((x) => x.player_id === playerId);
    if (p) return p.name;
  }
  return playerId;
}
