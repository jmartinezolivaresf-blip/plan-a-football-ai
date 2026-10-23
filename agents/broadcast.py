"""Director and chronicler for the broadcast scope: timed cues from KPIs, adaptations, Plan B, goals, the duel
and the final balance. Deterministic templates; every number is a {claim_id.field} placeholder and every cue text
passes the text verifier before it is kept (a cue that does not verify is dropped and counted).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from contracts import Claim, Cue, DuelBroadcast, I18nText, Option, Plan, Snapshot

from .validators import text as tv

STATUS_EN = {"on_track": "on track", "at_risk": "at risk", "failing": "failing", "insufficient_evidence": "too early"}
STATUS_ES = {"on_track": "en camino", "at_risk": "en riesgo", "failing": "fallando", "insufficient_evidence": "pronto"}
ES_ADAPT = {"short to long": "de corto a largo", "long to short": "de largo a corto"}
KPI_EN = {"high_turnovers": "high turnovers", "final_third_entries_share": "entries down the chosen channel",
          "set_piece_xg": "set-piece xG", "balls_in_behind_conceded": "balls in behind conceded"}
KPI_ES = {"high_turnovers": "robos altos", "final_third_entries_share": "entradas por el carril elegido",
          "set_piece_xg": "xG a balón parado", "balls_in_behind_conceded": "balones a la espalda concedidos"}
LEVER_EN = {"press_height": "press", "build_up": "build-up", "attack_channel": "attack channel",
            "corner_delivery": "corners", "press_target": "press target"}


def mmss(minute: int, second: int = 0) -> str:
    return f"{minute}:{second:02d}"


@dataclass
class Director:
    names: dict[str, str]           # team code -> short name
    claims: dict[str, Claim]
    cues: list[Cue] = field(default_factory=list)
    dropped: list[tuple[str, list[str]]] = field(default_factory=list)
    extra_claims: list[Claim] = field(default_factory=list)

    def add_claim(self, c: Claim) -> Claim:
        self.claims[c.claim_id] = c
        self.extra_claims.append(c)
        return c

    def cue(self, cue_id: str, t: str, template: str, priority: int, ttl: int, team: str | None, en: str, es: str,
            claims: list[str], mode=("casual", "analyst"), **fields: str) -> None:
        errors = tv.verify(en, self.claims) + tv.verify(es, self.claims)
        if errors:
            self.dropped.append((cue_id, errors))
            return
        self.cues.append(Cue(cue_id=cue_id, t_match=t, template=template, priority=priority, ttl_s=ttl, team=team,
                             fields=fields, text=I18nText(en=en, es=es), mode=list(mode), claims=claims))

    # ------------------------------------------------------------------ pre-match
    def prematch(self, plans: dict[str, Plan]) -> None:
        vals = [p.valuation for p in plans.values() if p.valuation]
        for team, plan in plans.items():
            v = plan.valuation
            if v:
                self.cue(f"q-000-plan-{team}", "0:00", "plan_card", 2, 15, team,
                         f"{self.names[team]}: {plan.name.en}, worth {{{v}.value}} xPts against a default plan in "
                         "our simulator.",
                         f"{self.names[team]}: {plan.name.es}, vale {{{v}.value}} xPts frente a un plan por defecto "
                         "en nuestro simulador.", [v], plan=plan.plan_id)
        if vals:
            self.cue("q-000-sealed", "0:00", "plan_sealed", 1, 10, None,
                     f"Both plans were sealed before kick-off [{vals[0]}].",
                     f"Los dos planes se sellaron antes del pitido inicial [{vals[0]}].", vals)

    # ------------------------------------------------------------------ live
    def live(self, snapshots: list[Snapshot], events, plans: dict[str, Plan], adaptations: dict[str, list[Claim]],
             upto: int) -> None:
        last_status: dict[tuple[str, str], str] = {}
        last_cue_minute: dict[str, int] = {}
        for s in snapshots:
            if s.minute == 0 or s.minute > upto:
                continue
            for k in s.kpis:
                key = (k.team, k.kpi_id)
                prev = last_status.get(key)
                last_status[key] = k.status
                if k.status == prev or k.status == "insufficient_evidence" or prev is None and k.status == "on_track":
                    continue
                if s.minute - last_cue_minute.get(k.team, -99) < 5:
                    continue
                last_cue_minute[k.team] = s.minute
                kpi = next(x for x in plans[k.team].kpis if x.id == k.kpi_id)
                bad = k.status in ("at_risk", "failing")
                self.cue(f"q-{s.minute:03d}-{k.team}-{k.kpi_id}", mmss(s.minute), "plan_alert" if bad else
                         "plan_tracker_lt", 2 if bad else 3, 12, k.team,
                         f"{self.names[k.team]} · {plans[k.team].name.en}: {KPI_EN[kpi.metric]} "
                         f"{STATUS_EN[k.status]}, {{{k.claim_id}.value}} against a target of {{{k.claim_id}.target}}.",
                         f"{self.names[k.team]} · {plans[k.team].name.es}: {KPI_ES[kpi.metric]} "
                         f"{STATUS_ES[k.status]}, {{{k.claim_id}.value}} con un objetivo de {{{k.claim_id}.target}}.",
                         [k.claim_id], kpi=k.kpi_id, status=k.status, value=f"{{{k.claim_id}.value}}")
        for team, (before, after) in ((t, a) for t, a in adaptations.items() if a):
            if after.minute is None or after.minute > upto:
                continue
            self.cue(f"q-{after.minute:03d}-adapt-{team}", mmss(after.minute, 30), "adaptation_detected", 1, 15, team,
                     f"{self.names[team]} have changed how they build up ({after.label}): long balls from their own "
                     f"half {{{after.claim_id}.value}} since minute {{{after.claim_id}.minute}}, from "
                     f"{{{before.claim_id}.value}} before.",
                     f"{self.names[team]} han cambiado su salida de balón ({ES_ADAPT[after.label]}): balones largos "
                     f"desde su campo {{{after.claim_id}.value}} desde el minuto {{{after.claim_id}.minute}}, antes "
                     f"{{{before.claim_id}.value}}.",
                     [after.claim_id, before.claim_id])
        prev_levers = None
        for s in snapshots:
            if 0 < s.minute <= upto and prev_levers and s.minute not in (45, 46):
                for team, lv in s.active_levers.items():
                    changed = [k for k, v in lv.model_dump().items() if v != prev_levers[team].model_dump()[k]]
                    kpi_claims = [k.claim_id for k in s.kpis if k.team == team and k.claim_id]
                    if changed and kpi_claims:
                        what_en = ", ".join(f"{LEVER_EN[c]} {getattr(lv, c)}" for c in changed)
                        self.cue(f"q-{s.minute:03d}-planb-{team}", mmss(s.minute), "plan_b_fired", 1, 12, team,
                                 f"{self.names[team]} switch to their Plan B: {what_en} [{kpi_claims[0]}].",
                                 f"{self.names[team]} activan su Plan B: {what_en} [{kpi_claims[0]}].",
                                 kpi_claims[:1])
            prev_levers = s.active_levers
        for e in events:
            if e.type == "goal" and e.minute <= upto:
                cid = f"c_goal_{e.event_id}"
                self.add_claim(Claim(claim_id=cid, type="observed_tendency", team=e.team, metric="goal",
                                     value=e.player_id or "", minute=e.minute, evidence=[e.event_id]))
                self.cue(f"q-{e.minute:03d}-goal-{e.event_id[-5:]}", mmss(e.minute, int(e.t % 60)), "goal_flash", 1,
                         8, e.team, f"Goal for {self.names[e.team]} in minute {{{cid}.minute}}.",
                         f"Gol de {self.names[e.team]} en el minuto {{{cid}.minute}}.", [cid])

    # ------------------------------------------------------------------ the duel
    def duel(self, home: str, away: str, options: dict[str, list[Option]], b: DuelBroadcast) -> None:
        m = b.true_matrix
        cell0 = m.cells[0][0].claim_id
        self.cue("q-045-rooms", "45:00", "duel_rooms", 1, 20, None,
                 f"Half-time: both benches choose at the same time, blind to each other [{cell0}].",
                 f"Descanso: los dos banquillos eligen a la vez y a ciegas [{cell0}].", [cell0])
        self.cue("q-045-sealed", "45:00", "duel_sealed", 1, 10, None,
                 f"Both choices are sealed [{cell0}].", f"Las dos decisiones están selladas [{cell0}].", [cell0])
        label = {o.option_id: o.label for team in options for o in options[team]}
        kes, har = b.revealed[home], b.revealed[away]
        i, j = m.rows.index(kes.option_id), m.cols.index(har.option_id)
        chosen_cell = m.cells[i][j].claim_id
        self.cue("q-045-reveal", "45:00", "duel_reveal", 1, 20, None,
                 f"{self.names[home]}: {label[kes.option_id].en} [{chosen_cell}]. {self.names[away]}: "
                 f"{label[har.option_id].en} [{chosen_cell}].",
                 f"{self.names[home]}: {label[kes.option_id].es} [{chosen_cell}]. {self.names[away]}: "
                 f"{label[har.option_id].es} [{chosen_cell}].", [chosen_cell])
        r = m.readings[home]
        dominant = r.dominant
        if dominant:
            en = f"{self.names[home]} have a dominant move in our simulator: {label[dominant].en} [{cell0}]."
            es = f"{self.names[home]} tienen una opción dominante en nuestro simulador: {label[dominant].es} [{cell0}]."
        else:
            en = (f"{self.names[home]}'s best move depends on {self.names[away]} [{cell0}]. The safe pick is "
                  f"{label[r.safe_pick].en} [{cell0}].")
            es = (f"La mejor opción de {self.names[home]} depende de {self.names[away]} [{cell0}]. La opción segura "
                  f"es {label[r.safe_pick].es} [{cell0}].")
        self.cue("q-045-matrix", "45:00", "duel_matrix", 1, 30, home, en, es,
                 [c.claim_id for row in m.cells for c in row if c.claim_id])

    # ------------------------------------------------------------------ final
    def final(self, home: str, away: str, plans: dict[str, Plan], last: Snapshot, b: DuelBroadcast | None,
              options: dict[str, list[Option]]) -> None:
        for team, plan in plans.items():
            ks = [k for k in last.kpis if k.team == team]
            on = sum(k.status == "on_track" for k in ks)
            cid = f"c_fin_{team}_kpis"
            self.add_claim(Claim(claim_id=cid, type="kpi_status", team=team, metric="kpis_on_track", value=on,
                                 n=len(ks), minute=90, evidence=[k.claim_id for k in ks if k.claim_id]))
            self.cue(f"q-090-score-{team}", "90:00", "plan_scorecard", 1, 20, team,
                     f"{self.names[team]} · {plan.name.en}: {{{cid}.value}} of {{{cid}.n}} KPIs on track at full time.",
                     f"{self.names[team]} · {plan.name.es}: {{{cid}.value}} de {{{cid}.n}} KPIs en camino al final.",
                     [cid])
        if b is None:
            return
        label = {o.option_id: o.label for team in options for o in options[team]}
        m = b.true_matrix
        for team, rg in b.regret.items():
            cid = rg.claim_id
            if rg.regret_xpts <= 1e-9:
                self.cue(f"q-090-regret-{team}", "90:00", "bench_regret", 1, 20, team,
                         f"{self.names[team]} read it right: no better answer existed in our simulator [{cid}].",
                         f"{self.names[team]} acertaron: no había mejor respuesta en nuestro simulador [{cid}].", [cid])
                continue
            self.cue(f"q-090-regret-{team}", "90:00", "bench_regret", 1, 20, team,
                     f"{self.names[team]}'s call left {{{cid}.value}} xPts on the table: "
                     f"{label[rg.best_response].en} was the best answer to what the other bench did.",
                     f"La decisión de {self.names[team]} dejó {{{cid}.value}} xPts sobre la mesa: "
                     f"{label[rg.best_response].es} era la mejor respuesta a lo que hizo el otro banquillo.", [cid])
            persp_home = team == home
            i = (m.rows if persp_home else m.cols).index(rg.best_response)
            j = (m.cols if persp_home else m.rows).index(rg.opponent_chosen)
            cell = m.cells[i][j] if persp_home else m.cells[j][i]
            self.cue(f"q-090-nottaken-{team}", "90:00", "option_not_taken", 2, 20, team,
                     f"The option not taken: {label[rg.best_response].en} [{cell.claim_id}].",
                     f"La opción no elegida: {label[rg.best_response].es} [{cell.claim_id}].", [cell.claim_id],
                     mode=("analyst",))
