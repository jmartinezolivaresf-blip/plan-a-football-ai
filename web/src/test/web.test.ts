// Frontend tests (node environment): fixture loading, score from events, clock, positions, seal verification,
// and a server-side render of the broadcast view with the real fixture bundle.
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Broadcast } from "../App";
import { FoundryRunPanel } from "../components/FoundryRun";
import type { FoundryRun } from "../lib/foundry";
import type { MatchBundle } from "../contracts/bundle";
import { clockReducer, initClock } from "../lib/clock";
import { changedLevers, kpiTarget, objective } from "../lib/levers";
import { parseTime, readParams } from "../lib/params";
import { frameIndex, matchEnd, playerName, positionsAt, possessionAt, scoreAt, teams } from "../lib/match";
import { canonicalJson, verifyPlan } from "../lib/seal";

const bundle: MatchBundle = JSON.parse(
  readFileSync(new URL("../../../fixtures/match_bundle_fixture.json", import.meta.url), "utf8"),
);

describe("fixture bundle", () => {
  it("loads with both teams, events, frames and plans", () => {
    const [home, away] = teams(bundle);
    expect([home, away]).toEqual(["KES", "HAR"]);
    expect(bundle.events.length).toBeGreaterThan(100);
    expect(bundle.render_frames.length).toBe(bundle.events.length);
    expect(Object.keys(bundle.plans).sort()).toEqual(["HAR", "KES"]);
  });
});

describe("score from events", () => {
  const codes = teams(bundle);
  const goals = bundle.events.filter((e) => e.type === "goal");
  it("is 0-0 at kick-off and matches the final snapshot", () => {
    expect(scoreAt(bundle.events, 0, codes)).toEqual({ KES: 0, HAR: 0 });
    expect(scoreAt(bundle.events, matchEnd(bundle), codes)).toEqual(bundle.snapshots[bundle.snapshots.length - 1].score);
  });
  it("changes exactly at each goal", () => {
    for (const g of goals) {
      const before = scoreAt(bundle.events, g.t - 0.05, codes)[g.team];
      expect(scoreAt(bundle.events, g.t, codes)[g.team]).toBe(before + 1);
    }
  });
  it("matches the half-time snapshot", () => {
    expect(scoreAt(bundle.events, 45 * 60 - 0.01, codes)).toEqual(bundle.snapshots[45].score);
  });
});

describe("playback clock", () => {
  it("advances only while playing and stops at the end", () => {
    let s = initClock(5400, 30);
    s = clockReducer(s, { type: "tick", dt: 1 });
    expect(s.time).toBe(0);
    s = clockReducer(s, { type: "play" });
    s = clockReducer(s, { type: "tick", dt: 2 });
    expect(s.time).toBe(60);
    s = clockReducer(s, { type: "pause" });
    s = clockReducer(s, { type: "tick", dt: 10 });
    expect(s.time).toBe(60);
    s = clockReducer(s, { type: "play" });
    s = clockReducer(s, { type: "tick", dt: 1000 });
    expect(s.time).toBe(5400);
    expect(s.playing).toBe(false);
  });
  it("seeks within bounds and changes speed", () => {
    let s = initClock(5400);
    s = clockReducer(s, { type: "seek", time: -5 });
    expect(s.time).toBe(0);
    s = clockReducer(s, { type: "seek", time: 99999 });
    expect(s.time).toBe(5400);
    s = clockReducer(s, { type: "speed", speed: 120 });
    expect(s.speed).toBe(120);
    s = clockReducer(s, { type: "play" });
    expect(s.time).toBe(0); // replay from the start after the end
  });
});

describe("positions and possession", () => {
  it("interpolates between frames and finds the right frame", () => {
    const f = bundle.render_frames;
    expect(frameIndex(f, -1)).toBe(-1);
    expect(frameIndex(f, f[10].t)).toBe(10);
    const mid = (f[10].t + f[11].t) / 2;
    const pos = positionsAt(f, mid)!;
    const expected = ((f[10].ball[0] as number) + (f[11].ball[0] as number)) / 2;
    expect(pos.ball[0]).toBeCloseTo(expected, 6);
    expect(Object.keys(pos.players)).toHaveLength(22);
  });
  it("possession follows the latest on-ball event", () => {
    const e = bundle.events.find((x) => x.type === "possession_change")!;
    expect(possessionAt(bundle.events, e.t)).toBe(e.team);
  });
});

describe("plans and seals", () => {
  it("canonical JSON sorts keys and has no spaces", () => {
    expect(canonicalJson({ b: 1, a: [true, null, "é"] })).toBe('{"a":[true,null,"é"],"b":1}');
    expect(() => canonicalJson({ x: 0.5 })).toThrow();
  });
  it("verifies the Python-made seals of both fixture plans", async () => {
    for (const plan of Object.values(bundle.plans)) {
      expect(await verifyPlan(plan)).toBe("verified");
    }
  });
  it("detects a tampered plan", async () => {
    const plan = structuredClone(bundle.plans.KES);
    plan.levers.press_height = "low";
    expect(await verifyPlan(plan)).toBe("mismatch");
  });
  it("describes levers and KPIs without inventing numbers", () => {
    const kes = bundle.plans.KES;
    expect(changedLevers(kes.levers)).toEqual(["press_height", "press_target", "attack_channel", "corner_delivery"]);
    expect(objective(kes.levers, (id) => playerName(bundle, id))).toContain(playerName(bundle, "HAR-5"));
    expect(kpiTarget(kes.kpis[0]!)).toBe("≥ 6 by 45'");
    expect(kpiTarget(kes.kpis[1]!)).toBe("≥ 40% by 90'");
  });
});

describe("broadcast view", () => {
  it("renders scorebug, pitch and both plan cards from the fixture", () => {
    const html = renderToString(createElement(Broadcast, { bundle }));
    expect(html).toContain("Kestrel");
    expect(html).toContain("Harbourside");
    expect(html).toContain(bundle.plans.KES.name.en);
    expect(html).toContain(bundle.plans.HAR.name.en);
    expect(html).toContain('data-testid="score-KES"');
    expect(html).toContain("00:00");
    expect(html).toContain("illustrative fixture data");
    expect(html.match(/data-player=/g)?.length).toBe(22);
  });
});

import { fill, formatValue, indexClaims } from "../lib/claims";
import { deltas, view } from "../lib/duel";
import { verifyChoice } from "../lib/seal";

describe("claims and placeholders", () => {
  const claims = indexClaims(bundle);
  it("formats shares as percentages and other numbers plainly (same rule as Python)", () => {
    const share = { claim_id: "cx", type: "observed_tendency", metric: "goal_kick_short_share", value: 0.784 } as never;
    const count = { claim_id: "cy", type: "kpi_status", metric: "high_turnovers", value: 4.0 } as never;
    expect(formatValue(share, "value")).toBe("78%");
    expect(formatValue(count, "value")).toBe("4");
  });
  it("fills every cue in the fixture without unknown claims", () => {
    for (const cue of bundle.cues) {
      expect(fill(cue.text.en, claims)).not.toContain("?");
      expect(fill(cue.text.en, claims)).not.toMatch(/\{c[\w-]+\./);
    }
  });
});

describe("duel matrix views", () => {
  const m = bundle.duel!.broadcast.true_matrix;
  it("transposes for the column team and centres deltas on Stay/Stay", () => {
    const home = view(m, m.row_team);
    const away = view(m, m.col_team);
    expect(home.own).toEqual(m.rows);
    expect(away.own).toEqual(m.cols);
    expect(away.xpts[1][2]).toBe(m.cells[2][1].xpts[m.col_team]);
    expect(deltas(home)[0][0]).toBe(0);
  });
  it("verifies both sealed half-time choices with the revealed salts", async () => {
    const d = bundle.duel!;
    for (const team of Object.keys(d.private)) {
      const r = d.broadcast.revealed[team];
      expect(await verifyChoice(d.private[team].choice.sha256, d.match_id, team, r.option_id, r.salt)).toBe("verified");
      expect(await verifyChoice(d.private[team].choice.sha256, d.match_id, team, "other", r.salt)).toBe("mismatch");
    }
  });
});

describe("analyst desk", () => {
  it("renders traces, plans and both matrices", () => {
    const html = renderToString(createElement(Broadcast, { bundle, initialTab: "desk" }));
    expect(html).toContain("Agent trace");
    expect(html).toContain("Validation panel");
    expect(html).toContain("What was really true");
    expect(html).toContain("What Kestrel believed");
  });
});

describe("deep links", () => {
  it("parses time, tab, mode, language, club and reveal", () => {
    expect(parseTime("45:00")).toBe(2700);
    expect(parseTime("90")).toBe(90);
    expect(parseTime("4500:00")).toBeNull();
    expect(readParams("?t=45:00&tab=desk&mode=fan&lang=es&club=HAR&reveal=1&matrix=believed&section=trace")).toEqual({
      t: 2700, tab: "desk", mode: "casual", lang: "es", club: "HAR", reveal: true, matrix: "believed", section: "trace",
    });
    expect(readParams("?tab=admin&mode=x")).toMatchObject({ tab: null, mode: null, reveal: false });
  });
});

describe("frozen demo bundle (simulated, not the fixture)", () => {
  const demo: MatchBundle = JSON.parse(
    readFileSync(new URL("../../public/match_bundle.json", import.meta.url), "utf8"),
  );
  const at = (search: string) => renderToString(createElement(Broadcast, { bundle: demo, link: readParams(search) }));

  it("is simulated data with a duel, cues and an evaluation panel", () => {
    expect(demo.illustrative).toBe(false);
    expect(demo.duel).toBeTruthy();
    expect(demo.cues.length).toBeGreaterThan(10);
    expect((demo.eval as Record<string, unknown>).E1).toBeTruthy();
  });
  it("renders kick-off, the revealed half-time duel, full time and the analyst desk", () => {
    expect(at("?t=0:00")).toContain("Plan Tracker");
    const ht = at("?t=45:00&reveal=1&mode=analyst");
    expect(ht).toContain("Half-time · The Duel");
    expect(ht).toContain("Duel matrix");
    expect(at("?t=90:00")).toContain("Whose plan won?");
    const desk = at("?tab=desk&t=50:00&mode=analyst&lang=es");
    expect(desk).toContain("Validation panel");
    expect(desk).toContain("Agent trace");
  });
  it("never leaves an unfilled claim placeholder in a rendered cue", () => {
    for (const t of ["?t=30:00", "?t=45:00&reveal=1", "?t=60:00&mode=analyst", "?t=90:00&lang=es"]) {
      expect(at(t)).not.toMatch(/\{c[\w-]+\.\w+\}/);
    }
  });
});

describe("plan card shows levers changed during the match", () => {
  it("marks the first in-match lever change only from its minute on", () => {
    const demo: MatchBundle = JSON.parse(readFileSync(new URL("../../public/match_bundle.json", import.meta.url), "utf8"));
    let found: { team: string; lever: string; minute: number } | null = null;
    for (const snap of demo.snapshots) {
      for (const [team, lv] of Object.entries(snap.active_levers)) {
        for (const [lever, value] of Object.entries(lv)) {
          if (!found && value !== (demo.plans[team].levers as unknown as Record<string, unknown>)[lever]) {
            found = { team, lever, minute: snap.minute };
          }
        }
      }
    }
    expect(found).not.toBeNull();
    const { team, lever, minute } = found!;
    const at = (m: number) => renderToString(createElement(Broadcast, { bundle: demo, link: readParams(`?t=${m * 60 + 30}`) }));
    expect(at(minute - 1)).not.toContain(`now-${team}-${lever}`);
    expect(at(minute)).toContain(`now-${team}-${lever}`);
  });
});


describe("pitch markers", () => {
  it("never overlap after separation", async () => {
    const { separate } = await import("../components/Pitch2D");
    const out = separate({ "KES-9": [50, 30], "HAR-2": [50, 30], "KES-2": [50.5, 30.4], "HAR-5": [10, 10] });
    const ids = Object.keys(out);
    for (let a = 0; a < ids.length; a++)
      for (let b = a + 1; b < ids.length; b++)
        expect(Math.hypot(out[ids[a]][0] - out[ids[b]][0], out[ids[a]][1] - out[ids[b]][1])).toBeGreaterThan(2.5);
    expect(out["HAR-5"]).toEqual([10, 10]);
  });
});

describe("Real Microsoft Foundry Run panel", () => {
  const run: FoundryRun = JSON.parse(readFileSync(new URL("../../public/foundry_run.json", import.meta.url), "utf8"));
  const html = renderToString(createElement(FoundryRunPanel, { run, colors: { KES: "#2dd4bf", HAR: "#f59e0b" },
                                                               names: { KES: "Kestrel", HAR: "Harbourside" } }));

  it("shows the real model, every call and the tools the model chose", () => {
    expect(html).toContain("Real Microsoft Foundry Run");
    expect(html).toContain("gpt-4.1-mini");
    expect(run.turns).toHaveLength(run.totals.model_turns);
    for (const t of run.turns) expect(html).toContain(t.response_id!.slice(0, 14));
    expect(html).toContain("a player&#x27;s profile ×3");
  });

  it("separates the real run from the deterministic replay and compares their half-time calls", () => {
    expect(html).toContain("a recorded run with real calls to a model in Microsoft Foundry");
    expect(html).toContain("a deterministic replay of the same agents");
    for (const b of Object.values(run.halftime.benches)) {
      expect(html).toContain(b.foundry.choice);
      expect(html).toContain(b.demo.choice);
    }
    expect(html).toContain("Foundry agents");
    expect(html).toContain("Offline demo");
  });

  it("shows what the validators rejected and how each agent reacted", () => {
    for (const g of run.guardrails) expect(html).toContain(g.outcome);
    expect(html).toContain("typed a number instead of citing recorded data");
  });

  it("opens from a deep link without loading anything else into the match", () => {
    expect(readParams("?tab=desk&section=foundry").section).toBe("foundry");
    const desk = renderToString(createElement(Broadcast, { bundle, link: readParams("?tab=desk&section=foundry") }));
    expect(desk).toContain("Real Microsoft Foundry Run");
    expect(desk).toContain("Loading the recorded run");  // fetched on the client, separate from the bundle
  });
});
