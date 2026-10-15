"""Reader for a photo of a printed price list.

The Evolus extractor reads only the text of a PDF, so a photo goes to Gemma directly,
on AMD Token Factory: Gemma reads images. If Gemma cannot be reached, Qwen reads it.

Same rules as for the PDFs, with one change. A photo has no text to check the answer
against, so the photo is read twice, at the same time, and a row is kept only if the
two readings agree on its code, price, pack size and marker. A surcharge is kept only
if its percentage is written in the footnote in both readings.
"""
import base64
import io
import json
import re
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from datetime import date

from PIL import Image, ImageOps

from mg import llm
from mg.extract.pdf import keep_what_is_written, read_note
from mg.schemas import DocumentNote, PriceLine, SourceRef

PHOTO_NAME = "photo of the price list"
# Gemma first. If Token Factory cannot serve it, the photo goes to the next model that reads images.
PHOTO_MODELS = ("Gemma-4-31B-IT", "Qwen3.8-Flash-Next")
MAX_TOKENS = 3000
MAX_SIDE = 1600  # pixels: enough for the small print of a footnote
TIMEOUT_SECONDS = 150  # one reading of a photo takes 50-150 seconds, depending on how busy Token Factory is

SYSTEM = (
    "You copy supplier price lists from photos. Copy only what is printed, never calculate "
    "or invent a value. Reply with a single JSON object and nothing else."
)
QUESTION = (
    "Copy every product row of this price list and every note printed outside the table. JSON:\n"
    '{"supplier": "company name as printed", "currency": "EUR or GBP", '
    '"lines": [{"code": "article code", "description": "...", "price": number as printed, '
    '"pack": pieces per pack (1 if not printed), "moq": minimum order (1 if not printed), '
    '"marker": "a symbol like * printed next to the row, or empty"}], '
    '"notes": [{"text": "the note as printed", "marker": "the symbol it refers to, or empty"}]}'
)
CURRENCIES = {"€": "EUR", "EUR": "EUR", "EURO": "EUR", "£": "GBP", "GBP": "GBP"}


class PhotoError(Exception):
    """The photo could not be read, or the two readings did not agree on anything."""


def read_photo(content: bytes, mime: str = "image/jpeg") -> tuple[str, list[PriceLine], list[DocumentNote], int, str]:
    """A photo -> (supplier as printed, price lines, notes, rows dropped because the readings disagreed, model used)."""
    content, mime = shrink(content, mime)
    for model in PHOTO_MODELS:
        try:
            first, second = read_twice(content, mime, model)
            notes = photo_notes(first, second, model)
            break
        except (llm.LLMError, PhotoError) as error:
            # the backup model is on the same AMD servers: if they cannot be reached at all, it would only add
            # another wait. A timeout is different: Gemma may be busy while Qwen is free, so Qwen still tries.
            unreachable = "network error" in str(error) and "timed out" not in str(error)
            if model == PHOTO_MODELS[-1] or unreachable:
                raise PhotoError(f"no model could read the photo: {error}") from error
    agreed, dropped = agreed_rows(first, second)
    if not agreed:
        raise PhotoError("the two readings of the photo did not agree on any row")

    currency = CURRENCIES.get(str(first.get("currency", "")).strip().upper())
    if currency is None:
        raise PhotoError(f"unknown currency on the photo: {first.get('currency')}")
    supplier = str(first.get("supplier", "")).strip()

    lines = [
        PriceLine(
            supplier=supplier,
            supplier_code=row["code"],
            description=row["description"],
            price=row["price"],
            currency=currency,
            pack_size=row["pack"],
            min_order_qty=row["moq"],
            markers=[row["marker"]] if row["marker"] else [],
            source=SourceRef(document=PHOTO_NAME, row=number, raw_text=row_as_read(row), currency=currency, pack_size=row["pack"]),
        )
        for number, row in enumerate(agreed, start=1)
    ]
    return supplier, lines, notes, dropped, model


def shrink(content: bytes, mime: str) -> tuple[bytes, str]:
    """A phone photo made smaller (longest side MAX_SIDE, JPEG): faster to send and to read, as legible."""
    try:
        image = Image.open(io.BytesIO(content))
        image = ImageOps.exif_transpose(image).convert("RGB")  # phones store the rotation apart
    except (OSError, ValueError):
        return content, mime  # not an image Pillow knows: send it as it is
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=88)
    return out.getvalue(), "image/jpeg"


def read_twice(content: bytes, mime: str, model: str) -> tuple[dict, dict]:
    """Two readings at the same time. If one fails, the other is not waited for: the next model can start."""
    pool = ThreadPoolExecutor(max_workers=2)
    futures = [pool.submit(ask_model, content, mime, model) for _ in range(2)]
    try:
        done, _ = wait(futures, return_when=FIRST_EXCEPTION)
        for future in done:
            if future.exception() is not None:
                raise future.exception()
        first, second = (future.result() for future in futures)
        return first, second
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def explain(error: Exception) -> str:
    """What went wrong with a photo, in one sentence for the person in front of the screen."""
    text = str(error)
    if "did not agree" in text and "no model could read" not in text:
        return "The two readings of the photo did not agree. Try again with the whole page flat and in focus."
    return "AMD Token Factory did not answer: neither Gemma nor the backup model could read the photo right now."


def ask_model(content: bytes, mime: str, model: str) -> dict:
    image = "data:" + mime + ";base64," + base64.b64encode(content).decode()
    payload = llm.build_payload(
        [{"type": "text", "text": QUESTION}, {"type": "image_url", "image_url": {"url": image}}],
        system=SYSTEM, model=model, max_tokens=MAX_TOKENS, json_mode=True,
    )
    text = llm.complete(payload, TIMEOUT_SECONDS)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise PhotoError(f"{model} did not answer with JSON")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise PhotoError(f"{model} answered with invalid JSON") from error


def clean_row(row: dict) -> dict | None:
    """The fields of one row in a fixed form, or None if a field cannot be read as it should."""
    try:
        price = float(str(row["price"]).replace(",", "."))
        pack = int(row.get("pack") or 1)
        moq = int(row.get("moq") or 1)
    except (KeyError, TypeError, ValueError):
        return None
    code = str(row.get("code", "")).strip().upper()
    if not code or price <= 0 or pack <= 0:
        return None
    return {
        "code": code, "description": str(row.get("description", "")).strip(), "price": price, "pack": pack,
        "moq": moq, "marker": str(row.get("marker") or "").strip(),
    }


def row_as_read(row: dict) -> str:
    """The row as the two readings agreed on it: a photo has no printed text to quote."""
    pack = f"  pack {row['pack']}" if row["pack"] > 1 else ""
    return f"{row['code']}  {row['description']} {row['marker']}  {row['price']:.2f}{pack}"


def agreed_rows(first: dict, second: dict) -> tuple[list[dict], int]:
    """The rows on which the two readings agree, in the order of the first; and how many were dropped."""
    def by_code(reading):
        rows = [clean_row(row) for row in reading.get("lines", []) if isinstance(row, dict)]
        return {row["code"]: row for row in rows if row}

    one, two = by_code(first), by_code(second)
    same = ("price", "pack", "marker")
    agreed = [row for code, row in one.items() if code in two and all(row[f] == two[code][f] for f in same)]
    return agreed, len(set(one) | set(two)) - len(agreed)


def photo_notes(first: dict, second: dict, model: str | None = None) -> list[DocumentNote]:
    """The notes of the first reading. A surcharge counts only if both readings print it.

    The footnote is read by the same model that read the photo. If it cannot be read, the
    whole photo fails: a surcharge left out in silence would hide an increase.
    """
    other_text = " ".join(str(note.get("text", "")) for note in second.get("notes", []) if isinstance(note, dict))
    notes = []
    for number, note in enumerate((n for n in first.get("notes", []) if isinstance(n, dict)), start=1):
        text = str(note.get("text", "")).strip()
        if not text:
            continue
        effect, valid_from = {}, None
        if re.search(r"\d\s*%", text):
            answer = read_note(text, model)
            if answer["surcharge_pct"] is not None and keep_what_is_written(answer, other_text)["surcharge_pct"] is not None:
                effect["surcharge_pct"] = answer["surcharge_pct"]
                valid_from = date.fromisoformat(answer["valid_from"]) if answer["valid_from"] else None
        notes.append(
            DocumentNote(
                text=text, applies_to_marker=note_marker(note, text), effect=effect,
                valid_from=valid_from, source=SourceRef(document=PHOTO_NAME, row=f"note {number}", raw_text=text),
            )
        )
    return notes


def note_marker(note: dict, text: str) -> str | None:
    """The symbol a note refers to: the one Gemma gave, or a * written in the note itself."""
    marker = str(note.get("marker") or "").strip()
    if marker:
        return marker
    return "*" if "*" in text else None
