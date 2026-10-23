// Human-readable lever and KPI labels (display text only; numbers come from the plan's structured fields).
import type { Kpi, Levers } from "../contracts/bundle";

export const DEFAULT_LEVERS: Levers = {
  press_height: "mid",
  press_target: null,
  build_up: "mixed",
  attack_channel: "balanced",
  corner_delivery: "near_post",
};

export const LEVER_LABEL: Record<keyof Levers, string> = {
  press_height: "Press",
  press_target: "Press target",
  build_up: "Build-up",
  attack_channel: "Attack channel",
  corner_delivery: "Corners",
};

const VALUE_LABEL: Record<string, string> = {
  high: "High",
  mid: "Mid",
  low: "Low",
  short: "Short",
  mixed: "Mixed",
  direct: "Direct",
  left: "Left",
  center: "Centre",
  right: "Right",
  balanced: "Balanced",
  near_post: "Near post",
  far_post: "Far post",
};

export function leverValue(lever: keyof Levers, value: string | null, nameOf: (id: string) => string): string {
  if (lever === "press_target") return value ? nameOf(value) : "None";
  return VALUE_LABEL[value ?? ""] ?? String(value);
}

export function changedLevers(levers: Levers): (keyof Levers)[] {
  return (Object.keys(DEFAULT_LEVERS) as (keyof Levers)[]).filter((k) => levers[k] !== DEFAULT_LEVERS[k]);
}

const KPI_LABEL: Record<string, string> = {
  high_turnovers: "High turnovers",
  final_third_entries_share: "Final-third entries",
  set_piece_xg: "Set-piece xG",
  balls_in_behind_conceded: "Balls in behind conceded",
};

export function kpiLabel(k: Kpi): string {
  const base = KPI_LABEL[k.metric] ?? k.metric;
  const channel = k.params?.channel ? ` (${VALUE_LABEL[k.params.channel] ?? k.params.channel})` : "";
  return `${base}${channel}`;
}

export function kpiTarget(k: Kpi): string {
  const share = k.metric === "final_third_entries_share";
  const op = k.target.match(/^(>=|<=|>|<)/)?.[0] ?? "";
  const num = Number(k.target.slice(op.length));
  const value = share ? `${Math.round(num * 100)}%` : String(num);
  const sym = { ">=": "≥", "<=": "≤", ">": ">", "<": "<" }[op] ?? op;
  return `${sym} ${value} by ${k.by_minute}'`;
}

/** One-line objective built from the levers (template text, no claims needed). */
export function objective(levers: Levers, nameOf: (id: string) => string): string {
  const parts: string[] = [];
  if (levers.press_height === "high") parts.push(levers.press_target ? `press high on ${nameOf(levers.press_target)}` : "press high");
  if (levers.press_height === "low") parts.push("defend deep");
  if (levers.build_up === "direct") parts.push("go direct");
  if (levers.build_up === "short") parts.push("build short");
  if (levers.attack_channel !== "balanced") parts.push(`attack the ${VALUE_LABEL[levers.attack_channel].toLowerCase()}`);
  if (levers.corner_delivery === "far_post") parts.push("aim corners at the far post");
  if (levers.corner_delivery === "short") parts.push("play corners short");
  if (parts.length === 0) return "Keep the default shape.";
  const text = parts.join(", ");
  return text.charAt(0).toUpperCase() + text.slice(1) + ".";
}
