"""Record a silent walkthrough of the real app (frames from headless Chrome deep links) and key screenshots.

    cd web && npm run build && cd ..
    uv run --no-project --with imageio-ffmpeg python scripts/record_walkthrough.py [--out docs/media]

Serves web/dist on 127.0.0.1 only, captures 1920x1080 frames of the app at the moments of docs/VIDEO_SCRIPT.md and
encodes them with the ffmpeg binary bundled in imageio-ffmpeg (nothing installed system-wide). It is a reproducible
storyboard for the final video (record the narration over it, or screen-record the same deep links live).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PORT = 4179
W, H = 1920, 1080


def shots() -> list[tuple[str, float, str | None]]:
    """(query, seconds on screen, screenshot name or None), in the order of the video script."""
    out: list[tuple[str, float, str | None]] = [("t=0:00&mode=analyst", 4.0, "01-plans-sealed"),
                                                ("tab=desk&mode=analyst", 5.0, "02-scouting-and-plan")]
    for s in range(24 * 60, 29 * 60 + 31, 15):  # the Plan B and the live detector, at 15 match-seconds a frame
        out.append((f"t={s // 60}:{s % 60:02d}&mode=analyst", 0.25, "03-live-detector" if s == 29 * 60 else None))
    out += [("t=45:00&mode=analyst", 3.0, "04-duel-rooms"),
            ("t=45:00&reveal=1&mode=analyst", 6.0, "05-duel-true-matrix"),
            ("t=45:00&reveal=1&mode=analyst&matrix=believed", 5.0, "06-duel-believed-matrix"),
            ("t=90:00&mode=analyst", 6.0, "07-full-time"),
            ("tab=desk&t=50:00&mode=analyst&section=trace", 5.0, "08-agent-trace"),
            ("tab=desk&t=90:00&mode=analyst&section=validation", 6.0, "09-validation-panel")]
    return out


def capture(url: str, path: Path, profile: Path) -> None:
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                    f"--user-data-dir={profile}", "--hide-scrollbars", f"--window-size={W},{H}",
                    "--virtual-time-budget=5000", f"--screenshot={path}", url],
                   check=True, capture_output=True, timeout=60)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "media"))
    args = ap.parse_args(argv)
    import imageio_ffmpeg

    dist = ROOT / "web" / "dist"
    if not (dist / "index.html").exists():
        sys.exit("build the web app first: cd web && npm run build")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1",
                               "--directory", str(dist)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with tempfile.TemporaryDirectory() as tmp:
            frames, concat = Path(tmp), []
            profile = frames / "profile"
            for k, (query, seconds, name) in enumerate(shots()):
                png = frames / f"{k:03d}.png"
                capture(f"http://127.0.0.1:{PORT}/?{query}", png, profile)
                concat += [f"file '{png}'", f"duration {seconds}"]
                if name:
                    shutil.copy(png, out / f"{name}.png")
                print(f"frame {k:3d} {query}", flush=True)
            concat.append(f"file '{frames / f'{len(shots()) - 1:03d}.png'}'")  # ffmpeg needs the last frame twice
            (frames / "list.txt").write_text("\n".join(concat) + "\n")
            video = out / "walkthrough.mp4"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                            "-i", str(frames / "list.txt"), "-vf", f"fps=30,scale={W}:{H},format=yuv420p",
                            "-c:v", "libx264", "-crf", "23", "-movflags", "+faststart", str(video)], check=True)
            print(f"wrote {video} ({video.stat().st_size / 1e6:.1f} MB) and screenshots in {out}")
    finally:
        server.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
