"""Builds the demo video: slides as chapters, the recorded app with captions, the narration, music.

    python3 assemble.py            # rec/*.mp4 + rec/*.json + ../preview/*.png + build/voice/*.wav -> margin-guardian-demo.mp4
    MG_VIDEO_SHORT=1 python3 assemble.py   # about 1:40, for a short pitch slot -> margin-guardian-demo-short.mp4

The narration comes from voice.py (one line per segment, build/voice/<n>.wav): a segment lasts at
least as long as its line, with a breath before and after. Without build/voice, the video is silent
apart from the music, as before.

The cuts come from the moments record.py wrote next to each recording (rec/<scene>.json).

Each segment is rendered on its own (1920x1080, 30 fps, short fades), then they are joined
and the music goes under the whole thing. Captions are written to files and read by
drawtext, so no text needs escaping.
"""
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
SLIDES = HERE.parent / "preview"
CARDS = SLIDES / "cards"  # one big sentence before each piece of the app
CARD = 4.0  # seconds on screen (at least: a longer line stretches it)
MUSIC = Path(os.environ.get("MG_VIDEO_MUSIC", HERE / "music.mp3"))  # "LoFi Tech" by The_Mountain, Pixabay; not in the repo
FONT = Path.home() / ".local/share/fonts/inter/InterDisplay-SemiBold.otf"
WORK = HERE / "build"
SHORT = bool(os.environ.get("MG_VIDEO_SHORT"))
OUT = HERE / ("margin-guardian-demo-short.mp4" if SHORT else "margin-guardian-demo.mp4")
KEEP_SHORT = {0, 1, 2, 5, 6, 7, 8, 15, 16, 17}  # segments of the short cut: no Italian list, no UK pack, no photo
FADE = 0.4
VOICE = WORK / "voice"
LEAD, TAIL = 0.5, 0.8  # seconds of segment before and after its line
MUSIC_UNDER_VOICE = 0.09  # music volume when there is a narration (0.8 without)
SPEEDUP = 20  # the wait for the photo reading, shown this many times faster


def run(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def captions(name: str, items: list[tuple[float, float, str]]) -> str:
    """drawtext filters for (start, end, text): a cream line on a dark green band, low on the screen."""
    filters = []
    for number, (start, end, text) in enumerate(items):
        textfile = WORK / f"{name}-{number}.txt"
        textfile.write_text(text)
        filters.append(
            f"drawtext=fontfile={FONT}:textfile={textfile}:expansion=none:fontsize=44:fontcolor=0xF1EBDD:"
            f"box=1:boxcolor=0x0A2A21@0.92:boxborderw=26:x=(w-text_w)/2:y=h-150:"
            f"enable='between(t,{start},{end})'"
        )
    return ",".join(filters)


def fades(length: float) -> str:
    return f"fade=t=in:st=0:d={FADE},fade=t=out:st={length - FADE:.2f}:d={FADE}"


def line(n: int) -> float:
    """Length of narration line n, 0 if there is none."""
    path = VOICE / f"{n}.wav"
    return duration(path) if path.exists() else 0.0


def fit(seconds: float, n: int) -> float:
    """A segment long enough for its line."""
    spoken = line(n)
    return max(seconds, LEAD + spoken + TAIL) if spoken else seconds


def slide(number: int, seconds: float, folder: Path = SLIDES, n: int = -1) -> Path:
    out = WORK / f"{folder.name}-{number}.mp4"
    seconds = fit(seconds, n)
    # one input frame: zoompan makes all the frames of the slide from it
    run("-i", str(folder / f"{number}.png"),
        "-vf", f"scale=1920:1080,zoompan=z='min(zoom+0.0004,1.04)':d={int(seconds * 30)}:s=1920x1080:fps=30,{fades(seconds)},format=yuv420p",
        "-r", "30", "-c:v", "libx264", "-crf", "16", "-an", str(out))
    return out


def clip(name: str, start: float, end: float, items, n: int = -1) -> Path:
    """A piece of a recording, with its captions (times relative to the piece).
    If its line is longer, the last frame is held."""
    out = WORK / f"{name}-{start:g}.mp4"
    hold = fit(end - start, n) - (end - start)
    length = end - start + hold
    vf = ",".join(f for f in (f"tpad=stop_mode=clone:stop_duration={hold:.2f}" if hold else "",
                              captions(f"{name}{start:g}", items), fades(length), "format=yuv420p") if f)
    run("-ss", str(start), "-to", str(end), "-i", str(HERE / "rec" / f"{name}.mp4"),
        "-vf", f"fps=30,{vf}", "-c:v", "libx264", "-crf", "16", "-an", str(out))
    return out


def sped_up(name: str, start: float, end: float, text: str, n: int = -1) -> Path:
    """The wait, played faster (SPEEDUP times, less if its line needs the time), with a caption that says so."""
    out = WORK / f"{name}-fast.mp4"
    speed = min(SPEEDUP, (end - start) / fit((end - start) / SPEEDUP, n))
    length = (end - start) / speed
    text = text.replace("{speed}", f"{speed:.0f}")
    vf = f"setpts=PTS/{speed},fps=30,{captions(name + 'fast', [(0, length, text)])},{fades(length)},format=yuv420p"
    run("-ss", str(start), "-to", str(end), "-i", str(HERE / "rec" / f"{name}.mp4"),
        "-vf", vf, "-c:v", "libx264", "-crf", "16", "-an", str(out))
    return out


def marks(name: str) -> dict:
    return json.loads((HERE / "rec" / f"{name}.json").read_text())


def main():
    WORK.mkdir(exist_ok=True)
    c, t, ph = marks("ciclo"), marks("trailgear"), marks("photo")
    # the n of each segment is its narration line in voice.py
    segments = [
        slide(1, 7, n=0), slide(2, 11, n=1), slide(3, 10, n=2),
        slide(1, CARD, CARDS, n=3), clip("ciclo", c["start"] - 1, c["footnote"], [], n=4),
        slide(2, CARD, CARDS, n=5), clip("ciclo", c["footnote"], c["moves"], [], n=6),
        slide(3, CARD, CARDS, n=7), clip("ciclo", c["moves"], c["end"] - 0.3, [], n=8),
        slide(4, CARD, CARDS, n=9), clip("trailgear", t["start"] - 1, t["end"] - 0.3, [], n=10),
        slide(5, CARD, CARDS, n=11), clip("photo", ph["start"] - 1, ph["reading"] + 2, [], n=12),
        sped_up("photo", ph["reading"] + 2, ph["read"] - 1, "Reading the photo twice  ·  shown {speed}x faster", n=13),
        clip("photo", ph["read"] - 1, ph["end"] - 0.3, [], n=14),
        slide(6, 11, n=15), slide(7, 12, n=16), slide(9, 9, n=17),
    ]
    parts = [(n, part) for n, part in enumerate(segments) if not SHORT or n in KEEP_SHORT]
    joined = WORK / "joined.mp4"
    (WORK / "list.txt").write_text("".join(f"file '{part}'\n" for _, part in parts))
    run("-f", "concat", "-safe", "0", "-i", str(WORK / "list.txt"), "-c", "copy", str(joined))
    length = duration(joined)
    music = f"[1:a]atrim=0:{length},afade=t=in:d=1,afade=t=out:st={length - 3:.2f}:d=3"
    if VOICE.exists():
        narration = voice_track(parts)
        run("-i", str(joined), "-stream_loop", "-1", "-i", str(MUSIC), "-i", str(narration),
            "-filter_complex", f"{music},volume={MUSIC_UNDER_VOICE}[m];[2:a]volume=1.0[v];[m][v]amix=inputs=2:duration=first:normalize=0[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(OUT))
    else:
        run("-i", str(joined), "-stream_loop", "-1", "-i", str(MUSIC), "-filter_complex", f"{music},volume=0.8[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(OUT))
    print(f"{OUT.name}: {duration(OUT):.1f} s, {OUT.stat().st_size / 1e6:.1f} MB")


def voice_track(parts: list[tuple[int, Path]]) -> Path:
    """One audio track as long as the video: line n starts LEAD seconds into segment n."""
    pieces = []
    for n, part in parts:
        piece, length = WORK / f"voice-{n}.wav", duration(part)
        if (VOICE / f"{n}.wav").exists():
            run("-i", str(VOICE / f"{n}.wav"), "-af", f"adelay={int(LEAD * 1000)}:all=1,apad=whole_dur={length:.3f}",
                "-t", f"{length:.3f}", "-ar", "48000", "-ac", "2", str(piece))
        else:
            run("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{length:.3f}", str(piece))
        pieces.append(piece)
    (WORK / "voice-list.txt").write_text("".join(f"file '{p}'\n" for p in pieces))
    track = WORK / "voice.wav"
    run("-f", "concat", "-safe", "0", "-i", str(WORK / "voice-list.txt"), "-c", "copy", str(track))
    return track


if __name__ == "__main__":
    main()
