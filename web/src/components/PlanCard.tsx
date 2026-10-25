// A team's sealed game plan: name, levers (changed ones highlighted), KPIs and a one-line objective.
import type { Levers, MatchBundle, Plan } from "../contracts/bundle";
import { changedLevers, kpiLabel, kpiTarget, LEVER_LABEL, leverValue, objective } from "../lib/levers";
import { playerName } from "../lib/match";
import { SealBadge } from "./SealBadge";

interface Props {
  bundle: MatchBundle;
  plan: Plan;
  color: string;
  side: "home" | "away";
  lang?: "en" | "es";
  /** Levers in force now (Plan B, half-time choice); shown next to the sealed value when they differ. */
  active?: Levers;
}

export function PlanCard({ bundle, plan, color, side, lang = "en", active }: Props) {
  const nameOf = (id: string) => playerName(bundle, id);
  const changed = new Set(changedLevers(plan.levers));
  const squad = bundle.squads.teams[plan.team];
  return (
    <section className={`plan-card ${side}`} style={{ borderColor: color }} aria-label={`${squad.name} plan`}>
      <header>
        <span className="pc-team" style={{ color }}>{squad.name}</span>
        <h2>{plan.name[lang]}</h2>
        <p className="pc-es" lang={lang === "en" ? "es" : "en"}>{plan.name[lang === "en" ? "es" : "en"]}</p>
      </header>
      <p className="pc-objective">{objective(plan.levers, nameOf)}</p>
      <ul className="pc-levers">
        {(Object.keys(LEVER_LABEL) as (keyof Levers)[]).map((k) => (
          <li key={k} className={changed.has(k) ? "changed" : ""}>
            <span>{LEVER_LABEL[k]}</span>
            <strong>
              {leverValue(k, plan.levers[k] as string | null, nameOf)}
              {active && active[k] !== plan.levers[k] && (
                <em className="pc-now" data-testid={`now-${plan.team}-${k}`}>
                  {" → "}{leverValue(k, active[k] as string | null, nameOf)}{lang === "en" ? " now" : " ahora"}
                </em>
              )}
            </strong>
          </li>
        ))}
      </ul>
      <h3>KPIs</h3>
      <ul className="pc-kpis">
        {plan.kpis.map((k) => (
          <li key={k.id}>
            <span>{kpiLabel(k)}</span>
            <strong>{kpiTarget(k)}</strong>
          </li>
        ))}
      </ul>
      {plan.plan_b.length > 0 && <p className="pc-planb">Plan B ready ({plan.plan_b.length === 1 ? "one trigger" : `${plan.plan_b.length} triggers`})</p>}
      <SealBadge plan={plan} />
    </section>
  );
}
