"""Reader for PDF price lists.

The reading is done by an Evolus document extractor that runs on our model on AMD.
This file sends the PDF, checks the answer against the PDF itself, saves it and
turns it into PriceLine and DocumentNote.

Three rules:
  - The model only copies what is printed. Nothing here calculates a price.
  - The answer is not trusted: plain code reads the text of the PDF on its own and
    checks that every extracted price is printed on its row, that the pack size is
    the one printed under the pack column (or 1 if there is no such column), and that
    no priced row was left out. If the check fails the extraction is tried again,
    then refused.
  - A number read from a footnote (a surcharge, a date) is kept only if it is
    literally written in that footnote. Otherwise it is dropped.

A saved answer is reused as long as the PDF has not changed (same SHA-256),
because one extraction takes one or two minutes.
"""
import fcntl
import hashlib
import json
import math
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
LIVE_TIMEOUT_SECONDS = 180  # the live reading on the app: on 15/10 the Evolus extractor took 78-170 seconds
MAX_ATTEMPTS = 3  # how many times one PDF is sent before giving up

# A printed price: digits, a dot or a comma, two decimals. Dates like 01.10.2026 do not match.
PRICE_PATTERN = re.compile(r"(?<![\d.,/])\d+[.,]\d{2}(?![\d.,/])")

# Header of the pack size column, compared without case, "*", brackets and dots (see pack_header).
# "Min. ord." is NOT one of them: it is the minimum order (5 pz = order at least five), not how many
# pieces are in a pack. "qty", "stk" and "unit" stay out too: they can mean something else.
PACK_HEADERS = {
    "ve", "vpe", "verpackungseinheit", "packung", "inhalt",
    "pack", "pack size", "pack qty", "units/pack", "qty/pack", "pcs/pack", "per pack",
    "conf", "confezione", "pz/conf",
}
# Header of the code or description column: a header row without a pack column (a second table, a
# services section) says that the rows under it have no pack column. Compared like PACK_HEADERS.
CODE_HEADERS = {
    "code", "product code", "codice", "articolo", "art-nr", "artnr", "art nr", "artikelnummer",
    "artikel", "description", "descrizione", "bezeichnung",
}
# A cell that names the price column: a header row has three cells or more, or one of these.
PRICE_HEADER_WORD = re.compile(r"\b(?:price|prezzo|preis|netto|net|eur|gbp|chf|usd)\b", re.IGNORECASE)
# A pack written on the row itself, in a list without a pack column: "pack of 4", "conf. da 6".
PACK_ON_ROW = re.compile(r"(?:pack of|box of|conf\.? da|confezione da)\s*(\d+)", re.IGNORECASE)
# The cells of a row in the PDF text: pieces of text separated by two or more spaces.
CELL_PATTERN = re.compile(r"\S+(?: \S+)*")

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
    return price_list_from(load_or_extract(path), path)


def read_pdf_price_list_live(path: Path) -> tuple[list[PriceLine], list[DocumentNote]]:
    """Reads the PDF again right now (see read_live), footnotes included, without touching the saved answer."""
    data = read_live(path)
    for note in data["notes"]:
        note.update(read_note(note["text"]))
    return price_list_from(data, path)


def price_list_from(data: dict, path: Path) -> tuple[list[PriceLine], list[DocumentNote]]:
    """The extracted data of one PDF as PriceLine and DocumentNote."""
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
                    document=path.name, page=item["page"], row=item["row"], raw_text=item["raw_text"],
                    currency=data["currency"], pack_size=int(item["pack_size"]),
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
        "extracted_by": f"Evolus document extractor, model {extractor_model()}",
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
    used = int(counter.read_text().strip() or 0) if counter.exists() else 0
    return max(0, config.LIVE_READS_PER_DAY - used)


def read_live(path: Path) -> dict:
    """Reads a PDF again right now, ignoring the saved answer. Counts against the daily limit.

    Returns the extracted data, checked against the PDF like every other reading.
    """
    counter = config.LIVE_COUNTER_DIR / f"{date.today().isoformat()}.count"
    counter.parent.mkdir(parents=True, exist_ok=True)
    with open(counter, "a+") as f:  # locked: two visitors at the same moment count as two
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        used = int(f.read().strip() or 0)
        if used >= config.LIVE_READS_PER_DAY:
            raise ExtractionError("the daily limit of live readings has been reached: try again tomorrow")
        f.seek(0)
        f.truncate()
        f.write(str(used + 1))
    # one try only and a shorter wait: a visitor should not wait for retries
    return extract_and_check(path, attempts=1, timeout=LIVE_TIMEOUT_SECONDS)


def extract_and_check(path: Path, attempts: int = MAX_ATTEMPTS, timeout: int = TIMEOUT_SECONDS) -> dict:
    """Asks Evolus for the data until the answer agrees with the PDF, at most `attempts` times."""
    text_rows = pdf_text_rows(path)
    problems, call_error = [], None
    for _ in range(attempts):
        try:
            data = call_evolus(path, timeout)
        except ExtractionError as error:
            call_error = error
            continue
        call_error = None
        problems = check_against_pdf(data, text_rows)
        if not problems:
            return data
    if call_error is not None:  # Evolus did not answer: that is not a reading refused by the check
        raise call_error
    raise ExtractionError(f"{path.name} refused after {attempts} attempt(s): " + "; ".join(problems))


def pdf_text_rows(path: Path) -> list[tuple[int, int, str]]:
    """The text of the PDF, read by plain code: (page, row on the page, text) for every non-empty row.

    The spaces are kept as printed, because the pack check needs to know which column a number is in.
    """
    rows = []
    for page_number, page in enumerate(PdfReader(path).pages, start=1):
        text = page.extract_text(extraction_mode="layout")
        for row_number, row in enumerate(text.splitlines(), start=1):
            if row.strip():
                rows.append((page_number, row_number, row.rstrip()))
    return rows


def compact(text: str) -> str:
    """A row of the PDF with every run of spaces made two spaces: what is saved as raw_text."""
    return re.sub(r"\s{2,}", "  ", text).strip()


def cells(text: str) -> list[tuple[float, str]]:
    """The cells of a row as (centre on the row, text)."""
    return [((m.start() + m.end()) / 2, m.group()) for m in CELL_PATTERN.finditer(text)]


def header_name(cell: str) -> str:
    """A header cell without case, "*", brackets and dots: "VE (Stk.)" -> "ve", "Art.-Nr." -> "art-nr"."""
    return re.sub(r"\s*\(.*\)|[*.]", "", cell.lower()).strip()


def pack_header(cell: str) -> bool:
    """True if the cell is the header of a pack column: "VE", "VE (Stk.)", "Conf.", "VPE*" ..."""
    return header_name(cell) in PACK_HEADERS


def has_pack_column(header_cells: list[tuple[float, str]]) -> bool:
    return any(pack_header(cell) for _, cell in header_cells)


def table_headers(text_rows: list[tuple[int, int, str]]) -> dict[tuple[int, int], list[tuple[float, str]]]:
    """The header rows of the tables, by (page, row): their cells.

    A header row has no price, has three cells or more (or one that names the price, "EUR", "Netto")
    and one of its cells is a pack header (PACK_HEADERS) or a code header (CODE_HEADERS). The cell
    count keeps out a section title like "Zubehör  VE"; the code header lets a second table
    without a pack column end the pack column of the table above. A row without a pack column right
    under one that has it (two rows at most) is the second row of the same header, often its
    translation ("Code  Description  Qty  Net EUR"), and does not end the pack column.
    """
    headers = {}
    last = None
    for page, row_number, text in text_rows:
        if PRICE_PATTERN.search(text):
            continue
        row_cells = cells(text)
        if len(row_cells) < 3 and not any(PRICE_HEADER_WORD.search(cell) for _, cell in row_cells):
            continue
        if any(pack_header(cell) or header_name(cell) in CODE_HEADERS for _, cell in row_cells):
            if (last and last[0] == page and row_number - last[1] <= 2
                    and has_pack_column(headers[last]) and not has_pack_column(row_cells)):
                continue
            headers[(page, row_number)] = row_cells
            last = (page, row_number)
    return headers


def printed_pack(text: str, header_cells: list[tuple[float, str]]) -> int | None:
    """The number printed under the pack column of this row, None if there is none.

    Every cell of the row goes to the header whose centre is nearest; the pack column must get one number.
    Only cells made of digits count: a description that ends up nearer to the pack column (a header on
    two rows, a long text) does not hide the number, while two numbers under it are still a problem.
    An empty pack cell is not taken as 1: a pack printed with its unit ("12 pz") can land in another
    column, and 1 would let it through. The row is refused instead.
    """
    pack_centre = next(centre for centre, cell in header_cells if pack_header(cell))
    under_pack = []
    for centre, cell in cells(text):
        nearest = min(header_cells, key=lambda header: abs(header[0] - centre))
        if nearest[0] == pack_centre and re.fullmatch(r"\d+", cell):
            under_pack.append(cell)
    if len(under_pack) != 1:
        return None
    return int(under_pack[0])


def check_pack(item: dict, page: int, row_number: int, text: str, headers: dict) -> str | None:
    """Checks the pack size of one extracted line against its row. Returns the problem, None if fine.

    If the nearest table header above the row (on this page, else on an earlier page) has a pack
    column, the pack size must be the number printed under it.
    Without one it must be 1, unless the row itself says "pack of N" or similar: then it must be N.
    """
    code = item["supplier_code"]
    try:
        pack = float(item.get("pack_size"))
    except (TypeError, ValueError):
        return f"{code}: pack size {item.get('pack_size')!r} is not a number"
    if not math.isfinite(pack) or pack != int(pack) or pack < 1:
        return f"{code}: pack size {item.get('pack_size')!r} is not a whole number of pieces"
    item["pack_size"] = int(pack)

    above = [key for key in headers if key < (page, row_number)]
    if above and has_pack_column(headers[max(above)]):
        printed = printed_pack(text, headers[max(above)])
        if printed is None:
            return f"{code}: no pack size printed under the pack column ({compact(text)})"
        if printed != item["pack_size"]:
            return f"{code}: pack size {item['pack_size']} but {printed} is printed under the pack column ({compact(text)})"
        return None

    written = PACK_ON_ROW.search(text)
    expected = int(written.group(1)) if written else 1
    if item["pack_size"] != expected:
        where = f'"{written.group()}" on the row' if written else "the list has no pack column"
        return f"{code}: pack size {item['pack_size']} but {where} ({compact(text)})"
    return None


def check_against_pdf(data: dict, text_rows: list[tuple[int, int, str]]) -> list[str]:
    """Compares the extracted lines with the text of the PDF. Returns the problems found (empty = fine).

    For every extracted line it also writes where the row is in the PDF: page, row, raw_text.
    """
    problems = []
    used_rows = set()
    headers = table_headers(text_rows)

    for item in data.get("lines") or []:
        code = item.get("supplier_code") if isinstance(item, dict) else None
        if not isinstance(code, str) or not code.strip():
            problems.append(f"a line without a readable code: {item}")
            continue
        try:
            price = float(item.get("price"))
        except (TypeError, ValueError):
            problems.append(f"{code}: price {item.get('price')!r} is not a number")
            continue
        found = [row for row in text_rows if code in row[2].split()]
        if not found:
            problems.append(f"{code} is not in the document")
            continue
        page, row_number, text = found[0]
        if (page, row_number) in used_rows:
            problems.append(f"{code} was extracted twice")
            continue
        used_rows.add((page, row_number))
        item["page"], item["row"], item["raw_text"] = page, row_number, compact(text)

        printed_prices = [float(price.replace(",", ".")) for price in PRICE_PATTERN.findall(text)]
        item["price"] = price
        if price not in printed_prices:
            problems.append(f"{code}: price {item['price']} is not printed on its row ({compact(text)})")

        pack_problem = check_pack(item, page, row_number, text, headers)
        if pack_problem:
            problems.append(pack_problem)

    for page, row_number, text in text_rows:
        if PRICE_PATTERN.search(text) and (page, row_number) not in used_rows:
            problems.append(f"a row with a price was not extracted: {compact(text)}")
    return problems


def call_evolus(path: Path, timeout: int = TIMEOUT_SECONDS) -> dict:
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise ExtractionError(f"Evolus answered HTTP {error.code} for {path.name}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ExtractionError(f"Evolus call failed for {path.name}: {error}") from error

    if not data.get("lines"):
        raise ExtractionError(f"Evolus found no product lines in {path.name}")
    return data


def extractor_model() -> str:
    """The model the Evolus extractor is set to, read from Evolus (it is chosen there, not here)."""
    llm.load_env()
    request = urllib.request.Request(
        f"{EVOLUS_API}/agents/{config.EVOLUS_EXTRACTOR_ID}",
        headers={"X-ApiKey": os.environ.get("EVOLUS_API_KEY", ""), "X-Application-Id": os.environ.get("EVOLUS_APPLICATION_ID", "")},
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # a short question: if Evolus is slow, do not hold the page
        agent = json.loads(response.read())
    name = agent.get("modelDisplayName") or agent.get("modelKey") or "unknown"
    # "own/..." is a model connected by us: here, AMD Token Factory
    return f"{name} on AMD Token Factory" if str(agent.get("modelKey", "")).startswith("own/") else name


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


def read_note(text: str, model: str | None = None) -> dict:
    """Asks the model whether a footnote announces a surcharge, then checks its answer against the text."""
    answer = llm.ask_json(NOTE_QUESTION + text, system=NOTE_SYSTEM, model=model, max_tokens=200)
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
