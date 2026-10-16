"""The narration: Margin Guardian presents itself, one line per segment of the video.

    MG_TTS_DIR=~/prove/tts ~/prove/tts/.venv/bin/python voice.py   # -> build/voice/<n>.wav

Kokoro (open model, runs on the CPU) reads each line. "|" marks a short breath inside a sentence:
every piece is read on its own and joined with a pause, so the voice does not run words together.
assemble.py places line n on segment n and makes the segment long enough for it.
"""
import os
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
OUT = HERE / "build" / "voice"
VOICE, SPEED, RATE = "am_michael", 1.08, 24000
BREATH, SENTENCE = 0.15, 0.22  # seconds of silence after a piece and after a sentence

# one entry per segment, in the order of assemble.py
LINES = [
    ["Hi.", "I'm Margin Guardian.", "Aris built me alone, | so there's no team to present me.", "I'll do it myself.",
     "I catch every hidden price increase, | for small shops | that can't hire a full-time buyer."],
    ["A supplier | sends a new price list.", "Brake pads | go from nine sixty | to five ten.", "Cheaper?", "No.",
     "The pack | went from four pads to two.", "So each pad | now costs six percent more."],
    ["In one demo shop, | three suppliers | sent new lists.", "Nineteen changes.", "Seven of them | easy to miss.",
     "About nine thousand euros a year, | if nobody reacts."],
    ["Let me show you.", "Everything here | runs for real."],
    ["This supplier is Italian, | and so is the price list.", "I read it anyway.",
     "I compare it with the last one, | line by line, | and link every product | to the shop's catalog."],
    ["Now, | the trap."],
    ["A note at the bottom | adds four percent | on six products.", "It's not in the prices.", "I find it, | and turn it into euros."],
    ["Then, | what to do about it."],
    ["For every increase, | three moves.", "Absorb it, | raise your price, | or negotiate.",
     "For the negotiation, | I write the email.", "Nothing is sent | until you press the button."],
    ["Now, | the smaller pack."],
    ["A UK supplier, | in pounds.", "The price went down, | but the pack is smaller.", "I compare the cost per pad, | in euros.",
     "Six percent more.", "And every number has a source.", "Click it, | and you see its row | in the document."],
    ["And now, | a photo of a paper list."],
    ["A phone photo, | sent to the bot."],
    ["Gemma, on AMD, | reads it twice."],
    ["Only the rows | where both readings agree | are kept.", "Same supplier, | same trap, | found again, | from a photo."],
    ["Why trust me?", "The AI reads.", "The code calculates.", "You sign.", "No number comes from the model.",
     "Every number | goes back to its row."],
    ["I run on Gemma, | on AMD Token Factory.", "Evolus reads the documents | and writes the emails.",
     "If a service doesn't answer, | I tell you which one, | and I keep working."],
    ["Try me now, | at margin dot voren dot dev, | or on Telegram.", "I'm Margin Guardian."],
]


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def trimmed(audio: np.ndarray) -> np.ndarray:
    """Cut the silence the model leaves around each piece, so the pauses are only ours."""
    loud = np.where(np.abs(audio) > 0.01)[0]
    return audio[max(loud[0] - 480, 0):loud[-1] + 960]


def main():
    tts_dir = Path(os.path.expanduser(os.environ.get("MG_TTS_DIR", ".")))
    kokoro = Kokoro(str(tts_dir / "kokoro-v1.0.onnx"), str(tts_dir / "voices-v1.0.bin"))
    OUT.mkdir(parents=True, exist_ok=True)
    for number, sentences in enumerate(LINES):
        parts = []
        for sentence in sentences:
            for piece in sentence.split("|"):
                audio, _ = kokoro.create(piece.strip(), voice=VOICE, speed=SPEED, lang="en-us")
                parts += [trimmed(audio.astype(np.float32)), silence(BREATH)]
            parts.append(silence(SENTENCE))
        line = np.concatenate(parts[:-2])  # no pause after the last piece
        sf.write(OUT / f"{number}.wav", line, RATE)
        print(number, f"{len(line) / RATE:.1f} s")


if __name__ == "__main__":
    main()
