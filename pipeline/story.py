"""Describe the frozen demo match from the bundle itself (README block and video facts; no number typed by hand).

    python -m pipeline.story            # prints the story and updates the README block
"""

from __future__ import annotations

from pathlib import Path

from contracts import MatchBundle

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "web" / "public" / "match_bundle.json"
README = ROOT / "README.md"
START, END = "<!-- DEMO_STORY -->", "<!-- /DEMO_STORY -->"


def describe(b: MatchBundle) -> list[str]:
    home, away = b.meta.home, b.meta.away
    name = {t: b.squads.teams[t].short_name for t in (home, away)}
    story, build = b.eval["story"], b.eval.get("build", {})
    claims = {c.claim_id: c for c in b.claims}
    ht, ft = story["ht_score"], story["final_score"]
    duel = b.duel
    label = {o.option_id: o.label.en for p in duel.private.values() for o in p.options}
    lines = [
        f"**The demo match** (season {build.get('season_seed')}, match seed {build.get('match_seed')}, agents: "
        f"{', '.join(sorted(set(build.get('models', {}).values())))}): {name[home]} {ht[home]}-{ht[away]} "
        f"{name[away]} at half-time, {ft[home]}-{ft[away]} at full time.",
        f"- Plans: {name[home]} \"{b.plans[home].name.en}\", {name[away]} \"{b.plans[away].name.en}\".",
    ]
    for team in (home, away):
        detected = story["adaptation"].get(team)
        if detected:
            changes = story["build_up_changes"][team]
            lines.append(f"- {name[team]} changed its build-up at minute {changes[0] if changes else '?'}; the live "
                         f"detector flagged it at minute {detected} (estimated change minute "
                         f"{story['change_point'][team]}).")
    for team in (home, away):
        r = duel.broadcast.revealed[team]
        lines.append(f"- Half-time: {name[team]} chose \"{label[r.option_id]}\" ({r.rule.replace('_', ' ')} on its "
                     f"own believed matrix).")
    for team in (home, away):
        rg = duel.broadcast.regret[team]
        c = claims[rg.claim_id]
        dom = duel.broadcast.true_matrix.readings[team].dominant
        extra = f"; \"{label[dom]}\" was dominant in the true matrix" if dom else ""
        if rg.regret_xpts <= 1e-9:
            lines.append(f"- {name[team]}: no regret, its choice was the best answer to the other bench{extra}.")
        else:
            lines.append(f"- {name[team]}: regret {rg.regret_xpts} xPts (paired 90% interval {c.interval_low} to "
                         f"{c.interval_high}) against \"{label[rg.best_response]}\"{extra}.")
    return lines


def update_readme(lines: list[str]) -> bool:
    text = README.read_text()
    if START not in text:
        return False
    before, rest = text.split(START, 1)
    after = rest.split(END, 1)[1] if END in rest else rest
    README.write_text(before + START + "\n" + "\n".join(lines) + "\n" + END + after)
    return True


def main() -> int:
    lines = describe(MatchBundle.model_validate_json(BUNDLE.read_text()))
    print("\n".join(lines))
    print("README updated" if update_readme(lines) else "README has no DEMO_STORY marker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
