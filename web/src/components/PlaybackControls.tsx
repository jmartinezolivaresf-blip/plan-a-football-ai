import { SPEEDS } from "../lib/clock";
import { minuteLabel } from "../lib/match";

interface Props {
  time: number;
  end: number;
  playing: boolean;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (t: number) => void;
  onSpeed: (s: number) => void;
}

export function PlaybackControls({ time, end, playing, speed, onPlay, onPause, onSeek, onSpeed }: Props) {
  return (
    <div className="controls">
      <button type="button" onClick={playing ? onPause : onPlay} aria-label={playing ? "Pause" : "Play"}>
        {playing ? "❚❚" : "▶"}
      </button>
      <input type="range" min={0} max={end} step={1} value={Math.round(time)} aria-label="Match time"
             onChange={(e) => onSeek(Number(e.target.value))} />
      <span className="ctl-time">{minuteLabel(time)}</span>
      <select value={speed} onChange={(e) => onSpeed(Number(e.target.value))} aria-label="Playback speed">
        {SPEEDS.map((s) => (
          <option key={s} value={s}>{s}×</option>
        ))}
      </select>
    </div>
  );
}
