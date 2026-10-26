"""Build the presentation video from the real app, plus its script and timing sheet (single source of truth).

    cd web && npm run build && cd ..
    uv run --no-project --with playwright --with pillow --with imageio-ffmpeg --with numpy \\
        python scripts/make_presentation.py [--guide-voice]

Drives the system Chrome with Playwright on 127.0.0.1 (no browser download), captures the app at the moments of the
story (and clicks "Reveal" like a viewer would), then renders 1920x1080 scenes with title cards, captions, zooms and
highlights from those captures. Writes:
  docs/media/plan_a_demo_v2.mp4               silent, ready for a recorded narration (timings in the sheet)
  docs/media/plan_a_demo_v2_guide_voice.mp4   same video + a SYNTHETIC macOS voice, only to check timing (--guide-voice)
  docs/VIDEO_SCRIPT.md                        narration, shots and exact times (generated from SCENES below)
Every number in the narration is checked against the bundle and the results by tests/test_demo_consistency.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"
OUT_DIR = ROOT / "docs" / "media"
W, H, FPS, FADE = 1920, 1080, 30, 0.35
NATURAL_WPM = 150  # a relaxed narration pace (words per minute) for the timing check and the guide voice
LEAD, TAIL = 0.25, 0.25  # each line starts LEAD s into its scene and must end TAIL s before the cut
PORT = 4183
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"
YELLOW, WHITE, MUTED, BG = (251, 191, 36), (240, 244, 250), (148, 163, 184), (8, 13, 24)

# ------------------------------------------------------------------------------------------------ the storyboard
# kind "card": a title card. kind "shot": a capture (state) with a zoom from `start` to `end` (box names, or None for
# the full frame) and optional highlighted boxes. kind "live": a sequence of captures played in order.
SCENES: list[dict] = [
    {"kind": "card", "seconds": 7.0, "title": "Two AI coaching staffs.\nTwo hidden strategies.\nOne tactical duel.",
     "sub": "Plan A · The Battle of the Benches",
     "speaker": "Javier", "vo": "Hi, I'm Javier. Plan A: two AI coaching staffs, one tactical duel."},
    {"kind": "shot", "seconds": 12.0, "state": "desk", "start": None, "end": "desk_report",
     "highlight": ["desk_report"], "phase": "1 · Each bench prepares in private",
     "caption": "An analyst agent studies the opponent. A manager agent turns the evidence into a plan.",
     "speaker": "Javier", "vo": "Each club gets an AI staff: an analyst who scouts the opponent's last eight matches, "
            "and a manager who turns that evidence into a game plan."},
    {"kind": "shot", "seconds": 7.5, "state": "kickoff", "start": None, "end": "kick_cards",
     "highlight": ["kick_seal_home", "kick_seal_away"], "phase": "Locked before kick-off",
     "caption": "Kestrel: a measured approach. Harbourside: exploit their weaknesses. Both plans are sealed.",
     "speaker": "Javier", "vo": "Both plans are sealed before kick-off, and neither bench can see the other's."},
    {"kind": "live", "seconds": 16.0, "state": "live", "box": "live_pitch", "phase": "2 · The match",
     "caption": "Kestrel's backup plan switches to long balls at 25'. The live detector spots it at 31'.",
     "speaker": "Javier", "vo": "The match plays out live, with a tracker on each plan. At minute 25, Kestrel's backup "
            "plan switches them to long balls, and the live detector spots it: from 6% to 45%."},
    {"kind": "shot", "seconds": 10.0, "state": "ht_closed", "start": None, "end": "ht_rooms",
     "highlight": ["ht_score"], "phase": "3 · Half-time: the duel",
     "caption": "1-1 at half-time. Both benches choose at the same time, blind to each other.",
     "speaker": "Javier", "vo": "Half-time, one-all. Now the duel: both benches pick from three options at the same "
            "moment, blind, and lock in."},
    {"kind": "shot", "seconds": 6.0, "state": "ht_revealed", "start": "ht_rooms", "end": "ht_rooms",
     "highlight": ["chosen_home", "chosen_away"], "phase": "The reveal",
     "caption": "Kestrel: Stay the course. Harbourside: Back to short passing.",
     "speaker": "Javier", "vo": "The reveal: Kestrel stay, Harbourside go back to short passing."},
    {"kind": "shot", "seconds": 10.0, "state": "ht_revealed", "start": "m_believed", "end": "m_believed",
     "highlight": ["believed_row"], "phase": "What Harbourside believed",
     "caption": "They expected Kestrel to go back to short too. On their numbers, short passing was the answer.",
     "speaker": "Bernardo", "vo": "And I'm Bernardo. Harbourside expected Kestrel to switch back to short passing, so "
            "matching it looked like the best answer."},
    {"kind": "shot", "seconds": 12.0, "state": "ht_revealed", "start": "m_true", "end": "m_true",
     "highlight": ["cell_happened", "cell_best"], "phase": "What was really true",
     "caption": "Kestrel stayed. Against that, dropping into a mid block was Harbourside's best answer.",
     "speaker": "Bernardo", "vo": "But Kestrel stayed. The simulator replays the second half hundreds of times for "
            "every pair of choices: against that, a mid block was better."},
    {"kind": "shot", "seconds": 9.5, "state": "ht_revealed", "start": "m_true", "end": "m_true",
     "highlight": ["cell_happened", "cell_best"], "phase": "The cost of the call",
     "caption": "About 0.12 expected points left on the table (likely range 0.01 to 0.23).",
     "speaker": "Bernardo", "vo": "Harbourside's call cost about 0.12 expected points, and the whole likely range is "
            "above zero."},
    {"kind": "shot", "seconds": 10.0, "state": "final", "start": None, "end": ["final_head", "recap"],
     "highlight": ["goal_line"], "phase": "4 · Full time",
     "caption": "Harbourside win 3-1 anyway. The call is judged against every alternative, not the score.",
     "speaker": "Bernardo", "vo": "Yet Harbourside win three-one. One match proves nothing, so every call is judged "
            "against the alternatives, not the score."},
    {"kind": "shot", "seconds": 13.0, "state": "desk_trace", "start": ["trace_r1", "trace_r16"],
     "end": ["trace_r1", "trace_r8"],
     "highlight": [], "phase": "5 · Under the hood",
     "caption": "Microsoft Agent Framework agents, each bench with its own MCP tools. Every figure points to "
                "recorded data.",
     "speaker": "Bernardo", "vo": "Each bench runs Microsoft Agent Framework agents with their own MCP tools. We also "
            "ran them on a real model in Microsoft Foundry, and every call is recorded."},
    {"kind": "card", "seconds": 5.0, "title": "Plan A\nThe Battle of the Benches",
     "sub": "Microsoft Agent Framework agents · MCP tools · the agents also ran on Microsoft Foundry "
            "(gpt-4.1-mini); this demo replays the offline run · synthetic data, fictional clubs",
     "speaker": "Bernardo", "vo": "Plan A. The Battle of the Benches."},
]

# what to capture: (state, url query, action, {box name: CSS selector})
STATES = [
    ("desk", "tab=desk&t=0:00&mode=analyst", None,
     {"desk_report": ".desk-grid > section:nth-of-type(1)", "desk_plan": ".desk-grid > section:nth-of-type(2)"}),
    ("kickoff", "t=0:00", None,
     {"kick_cards": ".stage", "kick_seal_home": ".plan-card.home .seal", "kick_seal_away": ".plan-card.away .seal"}),
    ("ht_closed", "t=45:00", None, {"ht_rooms": ".halftime", "ht_score": ".ht-head h2"}),
    # the duel through Harbourside's eyes: theirs is the call whose cost is above the simulator's noise
    ("ht_revealed", "t=45:00&club=HAR", "reveal",
     {"ht_rooms": ".rooms", "chosen_home": ".room:nth-of-type(1) li.chosen",
      "chosen_away": ".room:nth-of-type(2) li.chosen",
      "m_believed": ".duel-matrix.believed", "m_true": ".duel-matrix.true",
      "believed_row": ".duel-matrix.believed tbody tr:nth-of-type(3)", "cell_happened": ".duel-matrix.true td.happened",
      "cell_best": ".duel-matrix.true td.best-answer", "verdict": ".halftime .verdict"}),
    ("final", "t=90:00", None, {"final_stage": ".final", "goal_line": ".goal-line", "final_head": ".final .ht-head",
                                "recap": ".final .recap"}),
    ("desk_trace", "tab=desk&t=50:00&mode=analyst&section=trace", None,
     {"trace": "#desk-trace", "trace_r1": "#desk-trace thead", "trace_r8": "#desk-trace tbody tr:nth-of-type(8)",
      "trace_r16": "#desk-trace tbody tr:nth-of-type(16)"}),
]


def _cue_seconds(bundle: dict, template: str) -> int:
    t = next(c["t_match"] for c in bundle["cues"] if c["template"] == template)
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def capture(tmp: Path) -> tuple[dict, dict]:
    """Screenshots and element boxes for every state, plus the live sequence."""
    from playwright.sync_api import sync_playwright

    bundle = json.loads((DIST / "match_bundle.json").read_text())
    images, boxes = {}, {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for name, query, action, selectors in STATES:
            page.goto(f"http://127.0.0.1:{PORT}/?{query}")
            page.wait_for_selector(".app .topbar")
            page.wait_for_timeout(600)
            if action == "reveal":
                page.click("button.primary.big")
                page.wait_for_timeout(900)
            path = tmp / f"{name}.png"
            page.screenshot(path=str(path))
            images[name] = [path]
            for key, sel in selectors.items():
                el = page.query_selector(sel)
                if el is None:
                    raise SystemExit(f"selector {sel!r} not found in state {name}")
                b = el.bounding_box()
                boxes[key] = (b["x"], b["y"], b["width"], b["height"])
        start = _cue_seconds(bundle, "plan_b_fired") - 30
        end = _cue_seconds(bundle, "adaptation_detected") + 25
        frames = []
        for k, s in enumerate(range(start, end + 1, 15)):
            page.goto(f"http://127.0.0.1:{PORT}/?t={s // 60}:{s % 60:02d}")
            page.wait_for_selector(".pitch")
            page.wait_for_timeout(250)
            path = tmp / f"live_{k:03d}.png"
            page.screenshot(path=str(path))
            frames.append(path)
        for key, sel in (("live_stage", ".stage"), ("live_pitch", ".pitch-wrap")):
            box = page.query_selector(sel).bounding_box()
            boxes[key] = (box["x"], box["y"], box["width"], box["height"])
        images["live"] = frames + [frames[-1]] * max(1, len(frames) // 4)  # hold on the detector's cue
        browser.close()
    return images, boxes


# ------------------------------------------------------------------------------------------------ rendering
def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def _union(boxes: dict, keys):
    """None (full frame), one box name, or the union of several."""
    if keys is None:
        return None
    keys = [keys] if isinstance(keys, str) else keys
    xs = [boxes[k] for k in keys]
    x0, y0 = min(b[0] for b in xs), min(b[1] for b in xs)
    x1, y1 = max(b[0] + b[2] for b in xs), max(b[1] + b[3] for b in xs)
    return x0, y0, x1 - x0, y1 - y0


def _fit(box, pad: float = 40.0, below: float = 0.2) -> tuple[float, float, float, float]:
    """A 16:9 crop around a box (with padding), kept inside the frame, leaving the bottom `below` of the crop for
    the caption so the caption never covers what the scene is about."""
    if box is None:
        return 0.0, 0.0, float(W), float(H)
    x, y, w, h = box
    x, y, w, h = x - pad, y - pad, w + 2 * pad, h + 2 * pad
    h = h / (1 - below)
    if w / h > W / H:
        nh = w * H / W
        y, h = y - (nh - h) / 2, nh
    else:
        nw = h * W / H
        x, w = x - (nw - w) / 2, nw
    w, h = min(w, W), min(h, H)
    return max(0.0, min(x, W - w)), max(0.0, min(y, H - h)), w, h


def _card(scene: dict):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    title_font, sub_font = _font(84, True), _font(30)
    lines = scene["title"].split("\n")
    y = H / 2 - len(lines) * 55 - 30
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=title_font)
        d.text(((W - tw) / 2, y), line, font=title_font, fill=YELLOW if i == len(lines) - 1 else WHITE)
        y += 110
    for line in _wrap(d, scene["sub"], sub_font, W - 400):
        tw = d.textlength(line, font=sub_font)
        d.text(((W - tw) / 2, y + 30), line, font=sub_font, fill=MUTED)
        y += 44
    return img


def _overlay(scene: dict):
    """Phase tag and caption as a lower third (RGBA)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cap_font, tag_font = _font(40, True), _font(26, True)
    lines = _wrap(d, scene["caption"], cap_font, W - 240)
    band = 70 + 52 * len(lines)
    d.rectangle([0, H - band - 40, W, H], fill=(6, 10, 20, 225))
    d.rectangle([0, H - band - 40, 14, H], fill=YELLOW + (255,))
    d.text((80, H - band - 18), scene["phase"].upper(), font=tag_font, fill=YELLOW + (255,))
    for i, line in enumerate(lines):
        d.text((80, H - band + 26 + 52 * i), line, font=cap_font, fill=WHITE + (255,))
    return img


def _highlighted(path: Path, keys: list[str], boxes: dict):
    from PIL import Image, ImageDraw
    img = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(img)
    for k in keys:
        x, y, w, h = boxes[k]
        d.rounded_rectangle([x - 8, y - 8, x + w + 8, y + h + 8], radius=12, outline=YELLOW, width=6)
    return img


def render(images: dict, boxes: dict, out: Path) -> list[tuple[float, float]]:
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image

    prepared = []
    for sc in SCENES:
        if sc["kind"] == "card":
            prepared.append({"frames": [_card(sc)], "crop": [None, None], "overlay": None})
        elif sc["kind"] == "live":
            frames = [Image.open(p).convert("RGB") for p in images["live"]]
            prepared.append({"frames": frames, "crop": [_fit(boxes[sc["box"]], 10), _fit(boxes[sc["box"]], 10)],
                             "overlay": _overlay(sc)})
        else:
            img = _highlighted(images[sc["state"]][0], sc.get("highlight", []), boxes)
            start = _fit(_union(boxes, sc["start"]))
            end = _fit(_union(boxes, sc["end"]))
            prepared.append({"frames": [img], "crop": [start, end], "overlay": _overlay(sc)})

    def frame_at(i: int, local: float):
        sc, pr = SCENES[i], prepared[i]
        u = min(1.0, max(0.0, local / sc["seconds"]))
        ease = u * u * (3 - 2 * u)
        src = pr["frames"][min(len(pr["frames"]) - 1, int(u * len(pr["frames"])))]
        if pr["crop"][0] is not None:
            a, b = pr["crop"]
            x, y, w, h = (a[k] + (b[k] - a[k]) * ease for k in range(4))
            src = src.crop((int(x), int(y), int(x + w), int(y + h))).resize((W, H), Image.BILINEAR)
        if pr["overlay"] is not None:
            src = Image.alpha_composite(src.convert("RGBA"), pr["overlay"]).convert("RGB")
        return src

    starts, t = [], 0.0
    for sc in SCENES:
        starts.append((t, t + sc["seconds"]))
        t += sc["seconds"]
    total = t
    writer = imageio_ffmpeg.write_frames(str(out), (W, H), fps=FPS, codec="libx264", quality=5, macro_block_size=1,
                                         pix_fmt_out="yuv420p", output_params=["-movflags", "+faststart"])
    writer.send(None)
    for n in range(int(total * FPS)):
        now = n / FPS
        i = next(k for k, (a, b) in enumerate(starts) if a <= now < b or k == len(starts) - 1)
        img = frame_at(i, now - starts[i][0])
        until_end = starts[i][1] - now
        if i + 1 < len(SCENES) and until_end < FADE:
            nxt = frame_at(i + 1, 0.0)
            img = Image.blend(img, nxt, 1 - until_end / FADE)
        writer.send(np.asarray(img, dtype=np.uint8).tobytes())
    writer.close()
    return starts


# ------------------------------------------------------------------------------------------------ voice + docs
def read_time(text: str, out: Path) -> float:
    """Seconds the macOS voice takes to read `text` at NATURAL_WPM (writes a WAV to `out`)."""
    subprocess.run(["say", "-v", "Daniel", "-r", str(NATURAL_WPM), "-o", str(out), "--file-format=WAVE",
                    "--data-format=LEI16@22050", text], check=True)
    with wave.open(str(out)) as w:
        return w.getnframes() / w.getframerate()


def scene_starts() -> list[tuple[float, float]]:
    """Scene start and end times: the video is the scenes back to back (render() uses the same sums)."""
    out, t = [], 0.0
    for sc in SCENES:
        out.append((t, t + sc["seconds"]))
        t += sc["seconds"]
    return out


def guide_voice(starts: list[tuple[float, float]], video: Path, out: Path, tmp: Path) -> list[float]:
    """A SYNTHETIC voice (macOS `say`) laid on the scene starts, only to check that the narration fits."""
    import imageio_ffmpeg
    import numpy as np
    rate, lengths, track = 22050, [], None
    total = starts[-1][1]
    track = np.zeros(int(total * rate) + rate, dtype=np.int16)
    for k, sc in enumerate(SCENES):
        clip = tmp / f"vo_{k:02d}.wav"
        read_time(sc["vo"], clip)
        with wave.open(str(clip)) as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        lengths.append(len(data) / rate)
        at = int((starts[k][0] + LEAD) * rate)
        end = min(len(track), at + len(data))
        track[at:end] = data[: end - at]
    audio = tmp / "guide.wav"
    with wave.open(str(audio), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(track.tobytes())
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio),
                    "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)], check=True)
    return lengths


def write_script(starts: list[tuple[float, float]], lengths: list[float] | None) -> Path:
    def ts(sec: float) -> str:
        return f"{int(sec // 60)}:{sec % 60:04.1f}"

    rows = []
    for k, (sc, (a, b)) in enumerate(zip(SCENES, starts, strict=True)):
        on_screen = sc.get("caption") or sc["title"].replace("\n", " ")
        fit = "" if lengths is None else f"{lengths[k]:.1f} s"
        rows.append(f"| {ts(a)}-{ts(b)} | {sc['speaker']} | {sc.get('phase', 'Title')} | {on_screen} | "
                    f"\"{sc['vo']}\" | {fit} |")
    total = starts[-1][1]
    build = json.loads((ROOT / "web" / "public" / "match_bundle.json").read_text())["eval"]["build"]
    season, seed = build["season_seed"], build["match_seed"]
    parts, speakers = [], list(dict.fromkeys(sc["speaker"] for sc in SCENES))
    for who in speakers:
        ks = [k for k, sc in enumerate(SCENES) if sc["speaker"] == who]
        a, b = starts[ks[0]][0], starts[ks[-1]][1]
        words = sum(len(SCENES[k]["vo"].split()) for k in ks)
        read = "" if lengths is None else f", read in {sum(lengths[k] for k in ks):.0f} s at {NATURAL_WPM} wpm"
        lines = "\n".join(f"> **{ts(starts[k][0] + LEAD)}** {SCENES[k]['vo']}" for k in ks)
        parts.append(f"### {who}: {ts(a)} to {ts(b)} ({b - a:.1f} s, {words} words{read})\n\n{lines}")
    handover = next(starts[k][0] for k, sc in enumerate(SCENES) if sc["speaker"] != SCENES[0]["speaker"])
    after = next(sc.get("phase", "") for sc in SCENES if sc["speaker"] != SCENES[0]["speaker"])
    text = f"""# Video script (generated by scripts/make_presentation.py; edit SCENES there, not here)

**Two AI coaching staffs. Two hidden strategies. One tactical duel.** Total {total:.0f} s (limit 120 s), two
presenters, one turn each. The handover is at **{ts(handover)}**, on the cut to "{after}".

Files: `docs/media/plan_a_demo_v2.mp4` (silent, 1920x1080, to record the narration over),
`docs/media/plan_a_demo_v2_guide_voice.mp4` (a synthetic macOS voice, ONLY to check timing; record human voices for
the submission). The earlier `docs/media/walkthrough.mp4` is kept as a reference.

Every number below comes from the frozen demo bundle (season {season}, match seed {seed}) and is checked by
`tests/test_demo_consistency.py`. What the narration must not claim: that this single match proves anything (it is one
replay), that the AI beats random choices at half-time (E8 does not show that), or that this video's match was played
by Microsoft Foundry models (the demo replays the offline rules run; the same agents ran separately on Foundry,
`docs/FOUNDRY_EVIDENCE.md`).

## The script in two parts, ready to read

Times are when each line starts in the video. Read at a relaxed pace; every line fits its shot at {NATURAL_WPM}
words per minute.

""" + "\n\n".join(parts) + """

## Shot by shot

| Time | Speaker | Phase | On screen | Narration | Read at """ + str(NATURAL_WPM) + """ wpm |
|---|---|---|---|---|---|
""" + "\n".join(rows) + """

## Recording notes

- Each line starts 0.25 s into its shot; one turn each, no alternation. If a line runs long, cut words rather than
  speeding up.
- The cut at the handover changes shot and caption, so the second voice comes in on a visual change.
- Foundry: say only that the agents also ran on a real model in Microsoft Foundry and that every call is recorded
  (docs/FOUNDRY_EVIDENCE.md, D-056). **The closing card of the current `plan_a_demo_v2.mp4` still says the Foundry
  integration is "prepared, not yet verified"**; the generator already has the corrected card, so re-render the video
  (`scripts/make_presentation.py`) before recording so picture and voice agree.
- If the bundle is rebuilt, re-run the generator and the tests before recording.
"""
    path = ROOT / "docs" / "VIDEO_SCRIPT.md"
    path.write_text(text)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--guide-voice", action="store_true")
    ap.add_argument("--script-only", action="store_true",
                    help="write docs/VIDEO_SCRIPT.md (times from the scene list, lines measured at a natural pace) "
                         "without capturing or rendering any video")
    args = ap.parse_args(argv)
    if args.script_only:
        starts = scene_starts()
        with tempfile.TemporaryDirectory() as t:
            lengths = [read_time(sc["vo"], Path(t) / f"vo_{k:02d}.wav") for k, sc in enumerate(SCENES)]
        too_long = [(k, n, sc["seconds"]) for k, (sc, n) in enumerate(zip(SCENES, lengths, strict=True))
                    if n > sc["seconds"] - LEAD - TAIL]
        for k, n, sec in too_long:
            print(f"WARNING scene {k} narration {n:.1f} s does not fit in {sec} s at {NATURAL_WPM} wpm")
        print(f"wrote {write_script(starts, lengths)} ({starts[-1][1]:.0f} s, no video changed)")
        return 1 if too_long else 0
    if not (DIST / "index.html").exists():
        sys.exit("build the web app first: cd web && npm run build")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "--directory",
                               str(DIST)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            images, boxes = capture(tmp)
            video = OUT_DIR / "plan_a_demo_v2.mp4"
            starts = render(images, boxes, video)
            lengths = None
            if args.guide_voice:
                lengths = guide_voice(starts, video, OUT_DIR / "plan_a_demo_v2_guide_voice.mp4", tmp)
                for k, (sc, n) in enumerate(zip(SCENES, lengths, strict=True)):
                    if n > sc["seconds"] - LEAD - TAIL:
                        print(f"WARNING scene {k} narration {n:.1f} s does not fit in {sc['seconds']} s")
            script = write_script(starts, lengths)
            print(f"wrote {video} ({starts[-1][1]:.0f} s) and {script}")
    finally:
        server.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
