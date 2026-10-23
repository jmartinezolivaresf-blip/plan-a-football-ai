// H1 broadcast view: pitch with scorebug, both sealed plans, playback. Reads match_bundle.json; no backend.
import { useEffect, useState } from "react";
import { loadBundle } from "./bundle";
import { PlanCard } from "./components/PlanCard";
import { Pitch2D } from "./components/Pitch2D";
import { PlaybackControls } from "./components/PlaybackControls";
import { Scorebug } from "./components/Scorebug";
import type { MatchBundle } from "./contracts/bundle";
import { useMatchClock } from "./lib/clock";
import { matchEnd, teams } from "./lib/match";

// Fictional clubs get fixed broadcast colours by home/away slot (no club branding).
export const SLOT_COLORS = ["#2dd4bf", "#f59e0b"];

export function teamColors(bundle: MatchBundle): Record<string, string> {
  const [home, away] = teams(bundle);
  return { [home]: SLOT_COLORS[0], [away]: SLOT_COLORS[1] };
}

export function Broadcast({ bundle }: { bundle: MatchBundle }) {
  const clock = useMatchClock(matchEnd(bundle));
  const colors = teamColors(bundle);
  const [home, away] = teams(bundle);
  const target = bundle.plans[home]?.levers.press_target ?? null;
  return (
    <div className="app">
      <p className="banner" role="note">
        {bundle.meta.precomputed ? "Precomputed demo" : "Live"} · {bundle.meta.competition}
        {bundle.illustrative ? " · illustrative fixture data, not simulated" : ""} · fictional clubs and players
      </p>
      <div className="stage">
        {bundle.plans[home] && <PlanCard bundle={bundle} plan={bundle.plans[home]} color={colors[home]} side="home" />}
        <div className="pitch-wrap">
          <Scorebug bundle={bundle} time={clock.time} colors={colors} />
          <Pitch2D bundle={bundle} time={clock.time} colors={colors} highlight={target} />
          <PlaybackControls time={clock.time} end={clock.end} playing={clock.playing} speed={clock.speed}
                            onPlay={clock.play} onPause={clock.pause} onSeek={clock.seek} onSpeed={clock.setSpeed} />
        </div>
        {bundle.plans[away] && <PlanCard bundle={bundle} plan={bundle.plans[away]} color={colors[away]} side="away" />}
      </div>
    </div>
  );
}

export function App() {
  const [bundle, setBundle] = useState<MatchBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadBundle().then(setBundle, (e: Error) => setError(e.message));
  }, []);
  if (error) return <p role="alert" className="app">{error}</p>;
  if (!bundle) return <p className="app">Loading match…</p>;
  return <Broadcast bundle={bundle} />;
}
