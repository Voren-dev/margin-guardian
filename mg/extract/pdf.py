"""Reader for PDF price lists.

The reading is done by an Evolus document extractor that runs on our model on AMD.
This file sends the PDF, checks the answer against the PDF itself, saves it and
turns it into PriceLine and DocumentNote.

Three rules:
  - The model only copies what is printed. Nothing here calculates a price.
  - The answer is not trusted: plain code reads the text of the PDF on its own and
    checks that every extracted price is printed on its row and that no priced row
    was left out. If the check fails the extraction is tried again, then refused.
  - A number read from a footnote (a surcharge, a date) is kept only if it is
    literally written in that footnote. Otherwise it is dropped.

A saved answer is reused as long as the PDF has not changed (same SHA-256),
because one extraction takes one or two minutes.
"""
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from mg import config, llm
from mg.schemas import DocumentNote, PriceLine, SourceRef

EVOLUS_API = "https://api.evolus.ai/api/v1"
TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 3  # how many times one PDF is sent before giving up

# A printed price: digits, a dot or a comma, two decimals. Dates like 01.10.2026 do not match.
PRICE_PATTERN = re.compile(r"(?<![\d.,/])\d+[.,]\d{2}(?![\d.,/])")

NOTE_SYSTEM = (
    "You read footnotes of supplier price lists. Answer with JSON only. "
    "Copy numbers and dates from the note, never invent them."
)
NOTE_QUESTION = (
    "Does this note announce a price surcharge in percent? "
    'Answer {"surcharge_pct": number or null, "valid_from": "YYYY-MM-DD" or null}.\n\nNote: '
)


class ExtractionError(Exception):
    """The Evolus extractor could not be called or returned something unusable."""


def read_pdf_price_list(path: Path) -> tuple[list[PriceLine], list[DocumentNote]]:
    data = load_or_extract(path)

    lines = []
    for item in data["lines"]:
        lines.append(
            PriceLine(
                supplier=data["supplier"],
                supplier_code=item["supplier_code"],
                description=item["description"],
                price=float(item["price"]),
                currency=data["currency"],
                pack_size=int(item["pack_size"]),
                min_order_qty=int(item["min_order_qty"]),
                markers=[item["marker"]] if item["marker"] else [],
                source=SourceRef(
                    document=path.name, page=item["page"], row=item["row"], raw_text=item["raw_text"]
                ),
            )
        )

    notes = []
    for number, item in enumerate(data["notes"], start=1):
        effect = {}
        if item.get("surcharge_pct") is not None:
            effect["surcharge_pct"] = item["surcharge_pct"]
        notes.append(
            DocumentNote(
                text=item["text"],
                applies_to_marker=item["applies_to_marker"] or None,
                effect=effect,
                valid_from=date.fromisoformat(item["valid_from"]) if item.get("valid_from") else None,
                source=SourceRef(document=path.name, row=f"note {number}", raw_text=item["text"]),
            )
        )
    return lines, notes


def load_or_extract(path: Path) -> dict:
    """The extracted data of one PDF: the saved answer if the file is unchanged, a new call otherwise."""
    saved_path = config.EXTRACT_RESULTS_DIR / f"{path.name}.json"
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    if saved_path.exists():
        saved = json.loads(saved_path.read_text())
        if saved["sha256"] == file_hash:
            return saved["data"]

    data = extract_and_check(path)
    for note in data["notes"]:
        note.update(read_note(note["text"]))

    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved = {
        "document": path.name,
        "sha256": file_hash,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extracted_by": "Evolus document extractor on AMD Token Factory",
        "data": data,
    }
    saved_path.write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n")
    return data


def keys_are_set() -> bool:
    """True if this machine can call Evolus (the two keys are in the environment or in .env)."""
    llm.load_env()
    return bool(os.environ.get("EVOLUS_API_KEY")) and bool(os.environ.get("EVOLUS_APPLICATION_ID"))


def live_reads_left() -> int:
    """How many live readings are still allowed today."""
    counter = config.LIVE_COUNTER_DIR / f"{date.today().isoformat()}.count"
    used = int(counter.read_text()) if counter.exists() else 0
    return max(0, config.LIVE_READS_PER_DAY - used)


def read_live(path: Path) -> dict:
    """Reads a PDF again right now, ignoring the saved answer. Counts against the daily limit.

    Returns the extracted data, checked against the PDF like every other reading.
    """
    if live_reads_left() == 0:
        raise ExtractionError("the daily limit of live readings has been reached: try again tomorrow")
    counter = config.LIVE_COUNTER_DIR / f"{date.today().isoformat()}.count"
    counter.parent.mkdir(parents=True, exist_ok=True)
    counter.write_text(str(config.LIVE_READS_PER_DAY - live_reads_left() + 1))
    return extract_and_check(path, attempts=1)  # one try only: a visitor should not wait for retries


def extract_and_check(path: Path, attempts: int = MAX_ATTEMPTS) -> dict:
    """Asks Evolus for the data until the answer agrees with the PDF, at most `attempts` times."""
    text_rows = pdf_text_rows(path)
    problems = []
    for _ in range(attempts):
        try:
            data = call_evolus(path)
        except ExtractionError as error:
            problems = [str(error)]
            continue
        problems = check_against_pdf(data, text_rows)
        if not problems:
            return data
    raise ExtractionError(f"{path.name} refused after {attempts} attempt(s): " + "; ".join(problems))


def pdf_text_rows(path: Path) -> list[tuple[int, int, str]]:
    """The text of the PDF, read by plain code: (page, row on the page, text) for every non-empty row."""
    rows = []
    for page_number, page in enumerate(PdfReader(path).pages, start=1):
        text = page.extract_text(extraction_mode="layout")
        for row_number, row in enumerate(text.splitlines(), start=1):
            row = re.sub(r"\s{2,}", "  ", row).strip()
            if row:
                rows.append((page_number, row_number, row))
    return rows


def check_against_pdf(data: dict, text_rows: list[tuple[int, int, str]]) -> list[str]:
    """Compares the extracted lines with the text of the PDF. Returns the problems found (empty = fine).

    For every extracted line it also writes where the row is in the PDF: page, row, raw_text.
    """
    problems = []
    used_rows = set()

    for item in data["lines"]:
        code = item["supplier_code"]
        found = [row for row in text_rows if code in row[2].split()]
        if not found:
            problems.append(f"{code} is not in the document")
            continue
        page, row_number, text = found[0]
        used_rows.add((page, row_number))
        item["page"], item["row"], item["raw_text"] = page, row_number, text

        printed_prices = [float(price.replace(",", ".")) for price in PRICE_PATTERN.findall(text)]
        if float(item["price"]) not in printed_prices:
            problems.append(f"{code}: price {item['price']} is not printed on its row ({text})")

    for page, row_number, text in text_rows:
        if PRICE_PATTERN.search(text) and (page, row_number) not in used_rows:
            problems.append(f"a row with a price was not extracted: {text}")
    return problems


def call_evolus(path: Path) -> dict:
    """Sends one PDF to the Evolus extractor and returns the data in our format."""
    llm.load_env()
    key = os.environ.get("EVOLUS_API_KEY", "")
    application_id = os.environ.get("EVOLUS_APPLICATION_ID", "")
    if not key or not application_id:
        raise ExtractionError("EVOLUS_API_KEY or EVOLUS_APPLICATION_ID is missing in .env")

    url = (
        f"{EVOLUS_API}/agents/{config.EVOLUS_EXTRACTOR_ID}"
        f"/json/{config.EVOLUS_PRICE_LIST_FORMAT_ID}/ask-file?useWebhook=false"
    )
    body, content_type = file_upload_body(path)
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"X-ApiKey": key, "X-Application-Id": application_id, "Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise ExtractionError(f"Evolus answered HTTP {error.code} for {path.name}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ExtractionError(f"Evolus call failed for {path.name}: {error}") from error

    if not data.get("lines"):
        raise ExtractionError(f"Evolus found no product lines in {path.name}")
    return data


def file_upload_body(path: Path) -> tuple[bytes, str]:
    """The request body that uploads one file in the form field 'file' (multipart/form-data)."""
    boundary = uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    return head + path.read_bytes() + tail, f"multipart/form-data; boundary={boundary}"


def read_note(text: str) -> dict:
    """Asks the model whether a footnote announces a surcharge, then checks its answer against the text."""
    # Gemma is the product model; the development model is used while its endpoint is unstable.
    answer = llm.ask_json(NOTE_QUESTION + text, system=NOTE_SYSTEM, model=llm.DEV_MODEL, max_tokens=200)
    return keep_what_is_written(answer, text)


def keep_what_is_written(answer: dict, text: str) -> dict:
    """Keeps the surcharge and the date only if they are literally written in the note."""
    surcharge = answer.get("surcharge_pct")
    valid_from = answer.get("valid_from")

    if surcharge is not None:
        number = f"{float(surcharge):g}"  # 4.0 -> "4", 4.5 -> "4.5"
        written = re.search(rf"(?<![\d.,]){re.escape(number)}\s*%", text.replace(",", "."))
        if not written:
            surcharge = None
        else:
            surcharge = float(surcharge)

    if valid_from is not None:
        try:
            day = date.fromisoformat(valid_from)
        except (TypeError, ValueError):
            day = None
        numbers_in_text = re.findall(r"\d+", text)
        if day is None or str(day.year) not in numbers_in_text or str(day.day) not in [n.lstrip("0") for n in numbers_in_text]:
            valid_from = None

    # A date without a surcharge says nothing about prices.
    if surcharge is None:
        valid_from = None
    return {"surcharge_pct": surcharge, "valid_from": valid_from}
