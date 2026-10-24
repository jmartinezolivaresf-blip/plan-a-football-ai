// Deep links: ?t=45:00&tab=desk&mode=analyst&lang=es&club=HAR&reveal=1&matrix=believed&section=validation
// (for judges, screenshots and the video).
export interface LinkParams {
  t: number | null; // match seconds
  tab: "broadcast" | "desk" | null;
  mode: "casual" | "analyst" | null;
  lang: "en" | "es" | null;
  club: string | null;
  reveal: boolean;
  matrix: "true" | "believed" | null;
  section: "validation" | "trace" | null;
}

export function parseTime(raw: string | null): number | null {
  if (!raw) return null;
  const m = /^(\d{1,3}):([0-5]\d)$/.exec(raw);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  return /^\d+$/.test(raw) ? Number(raw) : null;
}

export function readParams(search: string): LinkParams {
  const q = new URLSearchParams(search);
  const pick = <T extends string>(key: string, allowed: readonly T[]): T | null => {
    const v = q.get(key);
    return v !== null && (allowed as readonly string[]).includes(v) ? (v as T) : null;
  };
  const mode = q.get("mode") === "fan" ? "casual" : pick("mode", ["casual", "analyst"] as const);
  return {
    t: parseTime(q.get("t")),
    tab: pick("tab", ["broadcast", "desk"] as const),
    mode,
    lang: pick("lang", ["en", "es"] as const),
    club: q.get("club"),
    reveal: q.get("reveal") === "1",
    matrix: pick("matrix", ["true", "believed"] as const),
    section: pick("section", ["validation", "trace"] as const),
  };
}
