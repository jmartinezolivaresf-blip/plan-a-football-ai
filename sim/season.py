"""Synthetic league: 6 fictional clubs, 18-player squads, archetypes, 3 hidden traits each, an 8-match season.

Public output (`SeasonPublic`): squads and the event logs of past matches, which is what scouting may read.
Evaluator-only output (`Truth`, `SimConfig`): archetypes and hidden traits. Season plans (which levers each club used
in each past match) are part of the world and are not published either: scouting must infer from events.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from contracts import Attributes, Event, I18nText, Kpi, Levers, Plan, Player, Squad, Squads
from contracts.eval_only import HiddenTrait, SimConfig, TeamTruth, Truth

from .api import simulate

ROLES = ["GK", "RB", "CB", "CB", "LB", "DM", "CM", "CM", "RW", "ST", "LW"]
BENCH = ["GK", "CB", "LB", "CM", "RW", "LW", "ST"]

# code, name, short name, archetype, split. Names are invented; check before publishing (see docs/SUBMISSION.md).
CLUBS = [
    ("KES", "Kestrel Athletic", "Kestrel", "pressing", "dev"),
    ("HAR", "Harbourside United", "Harbourside", "possession", "test"),
    ("MOR", "Moorgate Rovers", "Moorgate", "direct", "dev"),
    ("WEX", "Wexmoor Town", "Wexmoor", "low_block", "dev"),
    ("BRY", "Brayton City", "Brayton", "possession", "dev"),
    ("ASH", "Ashgrove Albion", "Ashgrove", "direct", "test"),
]
# Hidden traits per club (kind, role of the affected player or side). Strengths are drawn from the seed.
TRAITS = {
    "KES": [("late_fade", None), ("cb_low_pace", "CB"), ("weak_channel", "left")],
    "HAR": [("fb_low_press_resistance", "LB"), ("back_post_weak", None), ("gk_short_bias", None)],
    "MOR": [("back_post_weak", None), ("late_fade", None), ("fb_low_press_resistance", "RB")],
    "WEX": [("gk_short_bias", None), ("weak_channel", "right"), ("cb_low_pace", "CB")],
    "BRY": [("fb_low_press_resistance", "LB"), ("weak_channel", "left"), ("gk_short_bias", None)],
    "ASH": [("cb_low_pace", "CB"), ("back_post_weak", None), ("late_fade", None)],
}
ARCHETYPE_ATTR = {  # (pace, passing, stamina, press_resistance, aerial, finishing) offsets
    "pressing": (4, 0, 8, 0, 0, 0),
    "possession": (0, 8, 0, 8, -4, 2),
    "direct": (5, -4, 2, -4, 8, 2),
    "low_block": (-2, -2, 4, 0, 6, -2),
}
ARCHETYPE_LEVERS = {
    "pressing": dict(press_height="high", build_up="mixed"),
    "possession": dict(press_height="mid", build_up="short"),
    "direct": dict(press_height="mid", build_up="direct"),
    "low_block": dict(press_height="low", build_up="mixed"),
}
FIRST = ["Aldous", "Rory", "Ezra", "Milo", "Theo", "Jasper", "Callum", "Ilan", "Dorian", "Silas", "Wren", "Bram",
         "Otis", "Lev", "Fenn", "Rafe", "Kit", "Ansel", "Hugo", "Ned", "Ivo", "Gideon", "Lorcan", "Tobin", "Emmett",
         "Ciaran", "Jules", "Abel", "Rhys", "Basil", "Oren", "Linus", "Teo", "Monty", "Ash", "Quin", "Arlo", "Cosmo"]
LAST = ["Venn", "Tamsin", "Halloway", "Quarrie", "Brannock", "Lund", "Reave", "Mercer", "Faulk", "Okoro", "Castell",
        "Ellery", "Harrow", "Dunmore", "Asquith", "Selden", "Morrow", "Prior", "Marsh", "Calloway", "Strand", "Peake",
        "Vey", "Ashgrove", "Rook", "Holt", "Penrose", "Northcott", "Tallow", "Pike", "Garrow", "Calder", "Sable",
        "Fairlie", "Dorsey", "Wick", "Hale", "Brandt", "Corrigan", "Ostrow"]


@dataclass
class SeasonMatch:
    match_id: str
    home: str
    away: str
    events: list[Event]
    score: dict[str, int]


@dataclass
class SeasonPublic:
    season_id: str
    squads: Squads
    names: dict[str, tuple[str, str]]  # code -> (name, short)
    matches: list[SeasonMatch] = field(default_factory=list)

    def matches_of(self, team: str) -> list[SeasonMatch]:
        return [m for m in self.matches if team in (m.home, m.away)]


@dataclass
class Season:
    public: SeasonPublic
    truth: Truth
    config: SimConfig
    plans: dict[str, dict[str, Plan]]  # match_id -> plans used (world-internal)


def make_squads(seed: int) -> Squads:
    rng = random.Random(seed)
    used: set[str] = set()
    teams = {}
    for code, name, short, archetype, _ in CLUBS:
        off = ARCHETYPE_ATTR[archetype]
        players = []
        for k, role in enumerate(ROLES + BENCH):
            while True:
                full = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                if full not in used:
                    used.add(full)
                    break
            base = {"pace": 72 if role in ("RW", "LW", "ST", "RB", "LB") else 62,
                    "passing": 74 if role in ("DM", "CM", "AM") else 64, "stamina": 70,
                    "press_resistance": 68 if role != "GK" else 55,
                    "aerial": 76 if role in ("CB", "ST", "GK") else 58,
                    "finishing": 76 if role in ("ST", "RW", "LW") else 45}
            attrs = {key: max(30, min(95, v + o + rng.randint(-7, 7)))
                     for (key, v), o in zip(base.items(), off, strict=True)}
            players.append(Player(player_id=f"{code}-{k + 1}", name=full, shirt=k + 1, position=role, starter=k < 11,
                                  attributes=Attributes(**attrs)))
        teams[code] = Squad(team=code, name=name, short_name=short, players=players)
    return Squads(teams=teams)


def make_truth(squads: Squads, season_id: str, seed: int) -> Truth:
    rng = random.Random(seed + 1)
    teams = {}
    for code, _, _, archetype, split in CLUBS:
        traits = []
        for kind, arg in TRAITS[code]:
            strength = round(rng.uniform(0.55, 0.85), 2)
            player_id = side = None
            if arg in ("LB", "RB", "CB"):
                player_id = next(p.player_id for p in squads.teams[code].players if p.starter and p.position == arg)
            elif arg in ("left", "right"):
                side = arg
            traits.append(HiddenTrait(kind=kind, player_id=player_id, side=side, strength=strength))
        teams[code] = TeamTruth(team=code, archetype=archetype, split=split, traits=traits)
    return Truth(season_id=season_id, teams=teams)


def default_plan(team: str, opponent: str, archetype: str, rng: random.Random, plan_id: str) -> Plan:
    lev = dict(ARCHETYPE_LEVERS[archetype])
    lev["corner_delivery"] = rng.choice(["near_post", "far_post", "near_post"])
    lev["attack_channel"] = rng.choice(["balanced", "balanced", "left", "right", "center"])
    return Plan(plan_id=plan_id, team=team, opponent=opponent, name=I18nText(en="Season plan", es="Plan de liga"),
                levers=Levers(**lev), kpis=[Kpi(id="k1", metric="balls_in_behind_conceded", target="<=3")])


def schedule() -> list[tuple[str, str]]:
    """8 rounds of 3 matches: a single round robin (5 rounds) plus 3 return rounds; each club plays 8."""
    codes = [c[0] for c in CLUBS]
    rounds = []
    teams = codes[:]
    for _ in range(len(codes) - 1):
        pairs = [(teams[i], teams[-1 - i]) for i in range(len(teams) // 2)]
        rounds.append(pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    rounds += [[(b, a) for a, b in rnd] for rnd in rounds[:3]]
    return [pair for rnd in rounds for pair in rnd]


def build_season(seed: int = 2026, season_id: str = "s-2026") -> Season:
    squads = make_squads(seed)
    truth = make_truth(squads, season_id, seed)
    config = SimConfig(season_id=season_id, seed=seed, coefficients={})
    archetype = {c[0]: c[3] for c in CLUBS}
    rng = random.Random(seed + 2)
    public = SeasonPublic(season_id=season_id, squads=squads, names={c[0]: (c[1], c[2]) for c in CLUBS})
    plans_used: dict[str, dict[str, Plan]] = {}
    for k, (home, away) in enumerate(schedule()):
        mid = f"{season_id}-m{k + 1:02d}"
        plans = {home: default_plan(home, away, archetype[home], rng, f"{mid}-{home}"),
                 away: default_plan(away, home, archetype[away], rng, f"{mid}-{away}")}
        res = simulate(plans, squads, seed=seed * 100 + k, R=1, log=True, truth=truth, config=config, match_id=mid,
                       home=home)
        public.matches.append(SeasonMatch(match_id=mid, home=home, away=away, events=res.events,
                                          score=res.final_state.snapshot.score))
        plans_used[mid] = plans
    return Season(public=public, truth=truth, config=config, plans=plans_used)


def match_squads(squads: Squads, home: str, away: str) -> Squads:
    return Squads(teams={home: squads.teams[home], away: squads.teams[away]})
