"""Write the season to disk in two parts, and load the PUBLIC part only (for the standalone MCP server).

    python -m pipeline.season_io        # data/season/public.json  +  data/season/eval_only/truth.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from contracts import AttackDirection, Event, MatchMeta, Squads

ROOT = Path(__file__).resolve().parents[1]
SEASON_DIR = ROOT / "data" / "season"


def write_season(seed: int = 2026, out: Path = SEASON_DIR) -> Path:
    from sim.season import build_season

    season = build_season(seed)
    out.mkdir(parents=True, exist_ok=True)
    public = {"season_id": season.public.season_id, "squads": season.public.squads.model_dump(mode="json"),
              "matches": [{"match_id": m.match_id, "home": m.home, "away": m.away,
                           "events": [e.model_dump(mode="json") for e in m.events]} for m in season.public.matches]}
    (out / "public.json").write_text(json.dumps(public))
    (out / "eval_only").mkdir(exist_ok=True)
    (out / "eval_only" / "truth.json").write_text(season.truth.model_dump_json())
    return out / "public.json"


def load_public_engine(path: Path = SEASON_DIR / "public.json", home: str = "KES", away: str = "HAR"):
    """RealEngine over the public season only: scouting and pre-match valuation, no real world in this process."""
    from engine.api import RealEngine
    from engine.scouting import MatchLog
    from sim import bind, bind_beliefs

    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run `make season` first")
    data = json.loads(path.read_text())
    matches = [MatchLog(m["match_id"], m["home"], m["away"], [Event.model_validate(e) for e in m["events"]])
               for m in data["matches"]]
    meta = MatchMeta(match_id=f"{data['season_id']}-demo", home=home, away=away, kickoff_label="Matchday 9 (fictional)",
                     attack=[AttackDirection(period=1, positive_x=home), AttackDirection(period=2, positive_x=away)])
    return RealEngine(matches=matches, squads=Squads.model_validate(data["squads"]), meta=meta,
                      public_world=bind(None), true_world=None, belief_world=bind_beliefs)


if __name__ == "__main__":
    print(f"wrote {write_season(int(sys.argv[1]) if len(sys.argv) > 1 else 2026)}")
