// 2D pitch (105 x 68 m) drawn from the bundle's visual layer. Positions are illustrative, never analysed.
import type { MatchBundle } from "../contracts/bundle";
import { positionsAt } from "../lib/match";

interface Props {
  bundle: MatchBundle;
  time: number;
  colors: Record<string, string>;
  highlight?: string | null; // player_id to emphasise (e.g. a press target)
}

export function Pitch2D({ bundle, time, colors, highlight }: Props) {
  const pos = positionsAt(bundle.render_frames, time);
  return (
    <svg className="pitch" viewBox="-3 -3 111 74" role="img" aria-label="Match pitch">
      <rect x={-3} y={-3} width={111} height={74} className="pitch-bg" />
      <g className="lines" fill="none">
        <rect x={0} y={0} width={105} height={68} />
        <line x1={52.5} y1={0} x2={52.5} y2={68} />
        <circle cx={52.5} cy={34} r={9.15} />
        <rect x={0} y={13.84} width={16.5} height={40.32} />
        <rect x={88.5} y={13.84} width={16.5} height={40.32} />
        <rect x={0} y={24.84} width={5.5} height={18.32} />
        <rect x={99.5} y={24.84} width={5.5} height={18.32} />
        <rect x={-2} y={30.34} width={2} height={7.32} />
        <rect x={105} y={30.34} width={2} height={7.32} />
      </g>
      {pos &&
        Object.entries(pos.players).map(([id, [x, y]]) => {
          const team = id.split("-")[0];
          return (
            <g key={id} transform={`translate(${x} ${y})`} data-player={id}>
              <circle r={highlight === id ? 1.9 : 1.4} fill={colors[team] ?? "#ccc"}
                      className={highlight === id ? "player target" : "player"} />
              <text y={0.55} className="shirt">{id.split("-")[1]}</text>
            </g>
          );
        })}
      {pos && <circle cx={pos.ball[0]} cy={pos.ball[1]} r={0.8} className="ball" data-testid="ball" />}
    </svg>
  );
}
