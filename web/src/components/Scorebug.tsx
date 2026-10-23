// Broadcast scorebug: short names, score at the current time, match clock and possession dot.
import type { MatchBundle } from "../contracts/bundle";
import { minuteLabel, possessionAt, scoreAt, teams } from "../lib/match";

interface Props {
  bundle: MatchBundle;
  time: number;
  colors: Record<string, string>;
}

export function Scorebug({ bundle, time, colors }: Props) {
  const codes = teams(bundle);
  const score = scoreAt(bundle.events, time, codes);
  const poss = possessionAt(bundle.events, time);
  const half = time < 45 * 60 ? "1H" : "2H";
  return (
    <div className="scorebug" aria-label="Scorebug">
      {codes.map((code, i) => (
        <div key={code} className={`sb-team ${i === 0 ? "home" : "away"}`}>
          <span className="sb-swatch" style={{ background: colors[code] }} />
          <span className="sb-name">{bundle.squads.teams[code].short_name}</span>
          <span className="sb-score" data-testid={`score-${code}`}>{score[code]}</span>
          <span className={`sb-poss ${poss === code ? "on" : ""}`} aria-label={poss === code ? "in possession" : ""} />
        </div>
      ))}
      <div className="sb-clock" data-testid="clock">
        <span>{minuteLabel(time)}</span>
        <small>{half}</small>
      </div>
    </div>
  );
}
