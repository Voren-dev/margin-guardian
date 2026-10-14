"""Builds the demo video: slides as chapters, the recorded app with captions, music.

    python3 assemble.py            # rec/*.mp4 + rec/*.json + ../preview/*.png -> margin-guardian-demo.mp4

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
CARD = 5.5  # seconds on screen
MUSIC = Path(os.environ.get("MG_VIDEO_MUSIC", HERE / "music.mp3"))  # "LoFi Tech" by The_Mountain, Pixabay; not in the repo
FONT = Path.home() / ".local/share/fonts/inter/InterDisplay-SemiBold.otf"
WORK = HERE / "build"
OUT = HERE / "margin-guardian-demo.mp4"
FADE = 0.4
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


def slide(number: int, seconds: float, folder: Path = SLIDES) -> Path:
    out = WORK / f"{folder.name}-{number}.mp4"
    # one input frame: zoompan makes all the frames of the slide from it
    run("-i", str(folder / f"{number}.png"),
        "-vf", f"scale=1920:1080,zoompan=z='min(zoom+0.0004,1.04)':d={int(seconds * 30)}:s=1920x1080:fps=30,{fades(seconds)},format=yuv420p",
        "-r", "30", "-c:v", "libx264", "-crf", "16", "-an", str(out))
    return out


def clip(name: str, start: float, end: float, items) -> Path:
    """A piece of a recording, with its captions (times relative to the piece)."""
    out = WORK / f"{name}-{start:g}.mp4"
    length = end - start
    vf = ",".join(f for f in (captions(f"{name}{start:g}", items), fades(length), "format=yuv420p") if f)
    run("-ss", str(start), "-to", str(end), "-i", str(HERE / "rec" / f"{name}.mp4"),
        "-vf", f"fps=30,{vf}", "-c:v", "libx264", "-crf", "16", "-an", str(out))
    return out


def sped_up(name: str, start: float, end: float, text: str) -> Path:
    """The wait, played SPEEDUP times faster, with a caption that says so."""
    out = WORK / f"{name}-fast.mp4"
    length = (end - start) / SPEEDUP
    vf = f"setpts=PTS/{SPEEDUP},fps=30,{captions(name + 'fast', [(0, length, text)])},{fades(length)},format=yuv420p"
    run("-ss", str(start), "-to", str(end), "-i", str(HERE / "rec" / f"{name}.mp4"),
        "-vf", vf, "-c:v", "libx264", "-crf", "16", "-an", str(out))
    return out


def marks(name: str) -> dict:
    return json.loads((HERE / "rec" / f"{name}.json").read_text())


def main():
    WORK.mkdir(exist_ok=True)
    c, t, ph = marks("ciclo"), marks("trailgear"), marks("photo")
    parts = [
        slide(1, 7), slide(2, 11), slide(3, 10),
        slide(1, CARD, CARDS), clip("ciclo", c["start"] - 1, c["footnote"], []),
        slide(2, CARD, CARDS), clip("ciclo", c["footnote"], c["moves"], []),
        slide(3, CARD, CARDS), clip("ciclo", c["moves"], c["end"] - 0.3, []),
        slide(4, CARD, CARDS), clip("trailgear", t["start"] - 1, t["end"] - 0.3, []),
        slide(5, CARD, CARDS), clip("photo", ph["start"] - 1, ph["reading"] + 2, []),
        sped_up("photo", ph["reading"] + 2, ph["read"] - 1, f"Reading the photo twice  ·  shown {SPEEDUP}x faster"),
        clip("photo", ph["read"] - 1, ph["end"] - 0.3, []),
        slide(6, 11), slide(7, 12), slide(9, 9),
    ]
    joined = WORK / "joined.mp4"
    (WORK / "list.txt").write_text("".join(f"file '{part}'\n" for part in parts))
    run("-f", "concat", "-safe", "0", "-i", str(WORK / "list.txt"), "-c", "copy", str(joined))
    length = duration(joined)
    run("-i", str(joined), "-i", str(MUSIC),
        "-filter_complex", f"[1:a]atrim=0:{length},afade=t=in:d=1,afade=t=out:st={length - 3:.2f}:d=3,volume=0.8[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(OUT))
    print(f"{OUT.name}: {duration(OUT):.1f} s, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
