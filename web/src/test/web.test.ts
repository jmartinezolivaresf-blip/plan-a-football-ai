// Frontend tests (node environment): fixture loading, score from events, clock, positions, seal verification,
// and a server-side render of the broadcast view with the real fixture bundle.
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Broadcast } from "../App";
import type { MatchBundle } from "../contracts/bundle";
import { clockReducer, initClock } from "../lib/clock";
import { changedLevers, kpiTarget, objective } from "../lib/levers";
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
