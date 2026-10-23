// Playback clock as a pure reducer (tested) plus a React hook that drives it with requestAnimationFrame.
import { useCallback, useEffect, useReducer, useRef } from "react";

export interface ClockState {
  time: number; // match seconds
  playing: boolean;
  speed: number; // match seconds per real second
  end: number;
}

export type ClockAction =
  | { type: "tick"; dt: number } // real seconds elapsed
  | { type: "play" }
  | { type: "pause" }
  | { type: "seek"; time: number }
  | { type: "speed"; speed: number };

export const SPEEDS = [10, 30, 60, 120];

export function initClock(end: number, speed = 30): ClockState {
  return { time: 0, playing: false, speed, end };
}

export function clockReducer(state: ClockState, action: ClockAction): ClockState {
  switch (action.type) {
    case "tick": {
      if (!state.playing) return state;
      const time = Math.min(state.end, state.time + action.dt * state.speed);
      return { ...state, time, playing: time < state.end };
    }
    case "play":
      return { ...state, playing: true, time: state.time >= state.end ? 0 : state.time };
    case "pause":
      return { ...state, playing: false };
    case "seek":
      return { ...state, time: Math.min(state.end, Math.max(0, action.time)) };
    case "speed":
      return { ...state, speed: action.speed };
  }
}

export function useMatchClock(end: number, start = 0) {
  const [state, dispatch] = useReducer(clockReducer, end, (e) => ({ ...initClock(e), time: Math.min(e, start) }));
  const last = useRef<number | null>(null);

  useEffect(() => {
    if (!state.playing) {
      last.current = null;
      return;
    }
    let raf = 0;
    const loop = (now: number) => {
      const dt = last.current === null ? 0 : (now - last.current) / 1000;
      last.current = now;
      dispatch({ type: "tick", dt });
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [state.playing]);

  const play = useCallback(() => dispatch({ type: "play" }), []);
  const pause = useCallback(() => dispatch({ type: "pause" }), []);
  const seek = useCallback((time: number) => dispatch({ type: "seek", time }), []);
  const setSpeed = useCallback((speed: number) => dispatch({ type: "speed", speed }), []);
  return { ...state, play, pause, seek, setSpeed };
}
