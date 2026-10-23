// Plan A broadcast + analyst desk. Reads match_bundle.json only; no backend required.
import { useEffect, useMemo, useState } from "react";
import { loadBundle } from "./bundle";
import { AnalystDesk } from "./components/AnalystDesk";
import { FinalPanel, HalftimeScreen } from "./components/Duel";
import { activeCues, CueStack, PlanTrackerLT, type Settings, SettingsBar } from "./components/Overlays";
import { PlanCard } from "./components/PlanCard";
import { Pitch2D } from "./components/Pitch2D";
import { PlaybackControls } from "./components/PlaybackControls";
import { Scorebug } from "./components/Scorebug";
import type { MatchBundle } from "./contracts/bundle";
import { indexClaims } from "./lib/claims";
import { useMatchClock } from "./lib/clock";
import { matchEnd, teams } from "./lib/match";

// Fictional clubs get fixed broadcast colours by home/away slot (no club branding).
export const SLOT_COLORS = ["#2dd4bf", "#f59e0b"];
const HALF_TIME = 45 * 60;

export function teamColors(bundle: MatchBundle): Record<string, string> {
  const [home, away] = teams(bundle);
  return { [home]: SLOT_COLORS[0], [away]: SLOT_COLORS[1] };
}

export function Broadcast({ bundle, initialTab = "broadcast" }: { bundle: MatchBundle; initialTab?: "broadcast" | "desk" }) {
  const clock = useMatchClock(matchEnd(bundle));
  const colors = teamColors(bundle);
  const [home, away] = teams(bundle);
  const claims = useMemo(() => indexClaims(bundle), [bundle]);
  const [settings, setSettings] = useState<Settings>({ mode: "casual", lang: "en", club: home });
  const [tab, setTab] = useState<"broadcast" | "desk">(initialTab);
  const [halftimeSeen, setHalftimeSeen] = useState(false);
  const atHalftime = !!bundle.duel && !halftimeSeen && clock.time >= HALF_TIME && clock.time < HALF_TIME + 60;
  const atFullTime = clock.time >= clock.end;
  const { playing, pause, seek, play } = clock;

  useEffect(() => {
    if (atHalftime && playing) {
      pause();
      seek(HALF_TIME);
    }
  }, [atHalftime, playing, pause, seek]);

  const minute = Math.min(90, Math.floor(clock.time / 60));
  const target = bundle.plans[home]?.levers.press_target ?? null;
  const cues = activeCues(bundle.cues, clock.time, settings.mode,
                          ["duel_rooms", "duel_sealed", "duel_reveal", "duel_matrix", "plan_scorecard", "bench_regret",
                           "option_not_taken"]);
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Plan A <span>· The Battle of the Benches</span></div>
        <nav role="tablist">
          <button type="button" role="tab" aria-selected={tab === "broadcast"} className={tab === "broadcast" ? "on" : ""}
                  onClick={() => setTab("broadcast")}>Broadcast</button>
          <button type="button" role="tab" aria-selected={tab === "desk"} className={tab === "desk" ? "on" : ""}
                  onClick={() => setTab("desk")}>Analyst desk</button>
        </nav>
        <SettingsBar bundle={bundle} settings={settings} onChange={setSettings} />
      </header>
      <p className="banner" role="note">
        {bundle.meta.precomputed ? "Precomputed demo" : "Live"} · {bundle.meta.competition}
        {bundle.illustrative ? " · illustrative fixture data, not simulated" : " · simulated with our synthetic engine"} ·
        fictional clubs and players · values are inside our simulator, not real-football predictions
      </p>
      {tab === "broadcast" ? (
        <div className="stage">
          {bundle.plans[home] && <PlanCard bundle={bundle} plan={bundle.plans[home]} color={colors[home]} side="home" lang={settings.lang} />}
          <div className="pitch-wrap">
            <Scorebug bundle={bundle} time={clock.time} colors={colors} />
            <CueStack cues={cues} claims={claims} lang={settings.lang} colors={colors} />
            <Pitch2D bundle={bundle} time={clock.time} colors={colors} highlight={target} />
            <PlanTrackerLT bundle={bundle} minute={minute} mode={settings.mode} lang={settings.lang} colors={colors} />
            <PlaybackControls time={clock.time} end={clock.end} playing={clock.playing} speed={clock.speed}
                              onPlay={clock.play} onPause={clock.pause} onSeek={clock.seek} onSpeed={clock.setSpeed} />
            {atHalftime && (
              <HalftimeScreen bundle={bundle} mode={settings.mode} lang={settings.lang} club={settings.club} claims={claims}
                              colors={colors} onContinue={() => {
                                setHalftimeSeen(true);
                                seek(HALF_TIME + 61);
                                play();
                              }} />
            )}
            {atFullTime && <FinalPanel bundle={bundle} lang={settings.lang} mode={settings.mode} claims={claims} colors={colors} />}
          </div>
          {bundle.plans[away] && <PlanCard bundle={bundle} plan={bundle.plans[away]} color={colors[away]} side="away" lang={settings.lang} />}
        </div>
      ) : (
        <AnalystDesk bundle={bundle} claims={claims} minute={minute} lang={settings.lang} colors={colors} />
      )}
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
