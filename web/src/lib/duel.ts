// Read a duel payoff matrix from one team's perspective (mirrors engine/duel.py: payoffs / readings).
import type { Matrix } from "../contracts/bundle";

export interface View {
  own: string[];
  opp: string[];
  xpts: number[][]; // [own][opp] for `team`
  ci: [number, number][][];
  claim: (string | null)[][];
}

export function view(m: Matrix, team: string): View {
  const rowView = team === m.row_team;
  const own = rowView ? m.rows : m.cols;
  const opp = rowView ? m.cols : m.rows;
  const at = (i: number, j: number) => (rowView ? m.cells[i][j] : m.cells[j][i]);
  return {
    own,
    opp,
    xpts: own.map((_, i) => opp.map((_, j) => at(i, j).xpts[team])),
    ci: own.map((_, i) => opp.map((_, j) => at(i, j).ci90[team] as [number, number])),
    claim: own.map((_, i) => opp.map((_, j) => at(i, j).claim_id ?? null)),
  };
}

/** Delta vs the Stay/Stay cell for display (derived, never stored). */
export function deltas(v: View): number[][] {
  const base = v.xpts[0][0];
  return v.xpts.map((row) => row.map((x) => x - base));
}

export function bestResponseRow(v: View, col: number): number {
  let best = 0;
  v.xpts.forEach((row, i) => {
    if (row[col] > v.xpts[best][col]) best = i;
  });
  return best;
}

export type Phase = "prematch" | "first_half" | "halftime" | "second_half" | "full_time";

export function phaseAt(time: number, end: number, halftimeSeen: boolean): Phase {
  if (time <= 0) return "prematch";
  if (time < 2700) return "first_half";
  if (time >= 2700 && !halftimeSeen) return "halftime";
  if (time >= end) return "full_time";
  return "second_half";
}
