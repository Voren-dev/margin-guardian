"""Telegram bot: forward a demo price list (or a photo of one), get what changed, what it costs, and three moves.

Plain long polling on the Telegram Bot API, no framework. Run from the project folder:
    .venv/bin/python bot/telegram_bot.py
Needs TELEGRAM_BOT_TOKEN in the environment or in .env. The supplier email also needs the
Evolus keys, unless its text is already saved in data/demo/results/email.
"""
import html
import io
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mg import llm  # noqa: E402  (load_env puts .env into the environment)
from mg.export import new_prices_csv  # noqa: E402
from mg.analyze import expected_monthly_units  # noqa: E402
from mg.forecast import load_sales  # noqa: E402
from mg.negotiate import draft_email  # noqa: E402
from mg.extract.photo import PhotoError, explain, read_photo  # noqa: E402
from mg.report import DEMO_SUPPLIERS, HIDDEN_KINDS, SupplierReport, identify, run_supplier, supplier_of  # noqa: E402


log = logging.getLogger("margin-guardian-bot")

MAX_FILE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = ("image/jpeg", "image/png")

# the last photo read in each chat, so the buttons under its summary use that reading
photo_reports: dict[int, SupplierReport] = {}
SITE = "https://margin.voren.dev"

WELCOME = (
    "<b>Margin Guardian</b>\n"
    "The purchasing manager a small shop cannot afford.\n\n"
    "Forward a supplier's price list and I tell you what changed, what it costs you in a year, "
    "and three moves: absorb, reprice or negotiate.\n\n"
    "This is a demo: it knows the three suppliers of an invented bike shop. "
    "Pick one below, forward one of their price lists, or send a photo of one printed on paper.\n\n"
    f"Full app: {SITE}"
)


class Telegram:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.file_base = f"https://api.telegram.org/file/bot{token}"

    def call(self, method: str, data: dict | None = None, timeout: int = 40) -> dict:
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(f"{self.base}/{method}", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)["result"]

    def send(self, chat_id: int, text: str, buttons: list[list[tuple[str, str]]] | None = None):
        data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if buttons:
            data["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": c} for t, c in row] for row in buttons]}
        return self.call("sendMessage", data)

    def send_file(self, chat_id: int, name: str, content: bytes, caption: str):
        boundary = uuid.uuid4().hex
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{name}"\r\n'
            "Content-Type: text/csv\r\n\r\n".encode() + content + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        req = urllib.request.Request(
            f"{self.base}/sendDocument", data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)

    def download(self, file_id: str) -> bytes:
        path = self.call("getFile", {"file_id": file_id})["file_path"]
        with urllib.request.urlopen(f"{self.file_base}/{path}", timeout=40) as response:
            return response.read()


def euro(amount: float) -> str:
    """-9154.6 -> '−€9,155'"""
    return ("−" if amount < 0 else "+") + f"€{abs(amount):,.0f}"


def supplier_buttons() -> list[list[tuple[str, str]]]:
    return [[(f"{name} ({new.rsplit('.', 1)[1].upper()})", f"s:{key}")] for key, (name, _, new) in DEMO_SUPPLIERS.items()]


def move_buttons(key: str) -> list[list[tuple[str, str]]]:
    """key is a demo supplier, or "photo" for the last photo read in the chat."""
    return [[("Absorb", f"a:{key}"), ("Reprice", f"r:{key}"), ("Negotiate", f"n:{key}")]]


def summary(report: SupplierReport) -> str:
    lines = [
        f"<b>{html.escape(report.supplier)}</b> · {html.escape(report.new_file)}",
        f"{len(report.findings)} changes, {len(report.hidden())} of them hidden",
        f"If you do nothing: <b>{euro(report.total('absorb'))} a year</b>",
        "",
        "What changed:",
    ]
    # the hidden ones first (at most 3): they are the ones nobody would notice
    increases = report.increases()
    hidden = [finding for finding in increases if finding.kind in HIDDEN_KINDS][:3]
    shown = hidden + [finding for finding in increases if finding not in hidden][: 5 - len(hidden)]
    for finding in shown:
        name = html.escape(report.products[finding.sku].name)
        tag = " (hidden: smaller pack)" if finding.kind == "pack_change" else " (hidden: footnote)" if finding.kind == "surcharge_note" else ""
        lines.append(f"• {name}: {finding.pct_change:+.1f}%{tag}, {euro(finding.monthly_impact_eur * -1)}/month")
    if report.held_back:
        lines.append(f"\n{len(report.held_back)} result(s) held back: the numbers did not trace back to the source.")
    lines.append("\nWhat do you want to do?")
    return "\n".join(lines)


def absorb_text(report: SupplierReport) -> str:
    lines = [f"<b>Absorb</b> · {html.escape(report.supplier)}", "You keep your prices and pay the higher cost.", ""]
    for finding in report.increases():
        move = report.moves[finding.id]["absorb"]
        lines.append(f"• {html.escape(report.products[finding.sku].name)}: {euro(move.yearly_impact_eur)} a year")
    lines.append(f"\nTotal: <b>{euro(report.total('absorb'))} a year</b>")
    return "\n".join(lines)


def reprice(tg: Telegram, chat_id: int, report: SupplierReport):
    moves = [by_kind["reprice"] for by_kind in report.moves.values() if "reprice" in by_kind]
    units = sum(move.units_delta for move in moves)
    tg.send(
        chat_id,
        f"<b>Reprice</b> · {html.escape(report.supplier)}\n"
        "New prices that bring the margin back, never above the cheapest competitor. "
        "A higher price sells a bit less: estimated from 24 months of sales.\n\n"
        f"Compared with before the new price list: <b>{euro(report.total('reprice'))} a year</b>, "
        f"{units:+.0f} pieces a year.\nThe file below imports into your shop.",
    )
    csv_text = new_prices_csv(moves, {f.id: f.sku for f in report.findings}, report.products)
    tg.send_file(chat_id, f"new-prices-{report.key}.csv", csv_text.encode(), "New retail prices (CSV)")


def negotiate_text(report: SupplierReport) -> str:
    increases = report.increases()
    sales = load_sales()
    units = {finding.sku: expected_monthly_units(report.products[finding.sku], sales) for finding in increases}
    draft = draft_email(report.supplier, increases, report.products, units)
    return (
        f"<b>Negotiate</b> · {html.escape(report.supplier)}\n"
        f"If the supplier gives up half the increase: <b>{euro(report.total('negotiate'))} a year</b>.\n\n"
        f"<b>To:</b> {html.escape(draft.to)}\n<b>Subject:</b> {html.escape(draft.subject)}\n\n"
        f"{html.escape(draft.body)}\n\n"
        f"<i>Nothing was sent. The sentences come from the Evolus email tool; the {draft.numbers_checked} "
        "numbers were put in by code and checked.</i>"
    )[:4096]


def handle_message(tg: Telegram, message: dict):
    chat_id = message["chat"]["id"]
    document = message.get("document")
    photo = message["photo"][-1] if message.get("photo") else None  # the largest size
    if document and document.get("mime_type") in IMAGE_TYPES:
        photo = document
    if photo:
        if photo.get("file_size", 0) > MAX_FILE_BYTES:
            tg.send(chat_id, "That photo is too big for this demo.")
            return
        content = tg.download(photo["file_id"])
        # a photo takes one or two minutes: read it on its own thread, so the bot keeps answering
        threading.Thread(target=safe_photo, args=(tg, chat_id, content, photo.get("mime_type", "image/jpeg")), daemon=True).start()
        return
    if document:
        if document.get("file_size", 0) > MAX_FILE_BYTES:
            tg.send(chat_id, "That file is too big for this demo.")
            return
        key = identify(tg.download(document["file_id"]))
        if key is None:
            tg.send(chat_id, "This demo knows only the new price lists of its three suppliers. Pick one:", supplier_buttons())
            return
        tg.send(chat_id, summary(run_supplier(key)), move_buttons(key))
        return
    tg.send(chat_id, WELCOME, supplier_buttons())  # /start, /demo or any text


def safe_photo(tg: Telegram, chat_id: int, content: bytes, mime: str):
    """handle_photo on its own thread: an error is logged and told to the person, never lost."""
    try:
        handle_photo(tg, chat_id, content, mime)
    except Exception:
        log.exception("photo for chat %s failed", chat_id)
        try:
            tg.send(chat_id, "Something went wrong on my side. Try again, or use the app: " + SITE)
        except Exception:
            pass


def handle_photo(tg: Telegram, chat_id: int, content: bytes, mime: str):
    """Gemma reads the photo twice; the rows both readings agree on go through the same chain as a file."""
    tg.send(chat_id, "Reading the photo with Gemma on AMD, twice, to check every number. One or two minutes...")
    try:
        _, lines, notes, dropped, model = read_photo(content, mime)
    except (PhotoError, llm.LLMError) as error:
        log.warning("photo not read: %s", error)
        tg.send(chat_id, explain(error))
        return
    key = supplier_of(lines)
    if key is None:
        tg.send(chat_id, "I read the photo, but it is not a price list of one of the three demo suppliers. Pick one:", supplier_buttons())
        return
    report = run_supplier(key, lines, notes, "photo of the price list")
    photo_reports[chat_id] = report
    text = summary(report)
    text += f"\n\n<i>Photo read twice by {html.escape(model)} on AMD; a row counts only if both readings agree."
    text += f" {dropped} row(s) left out.</i>" if dropped else "</i>"
    tg.send(chat_id, text, move_buttons("photo"))


def handle_callback(tg: Telegram, callback: dict):
    tg.call("answerCallbackQuery", {"callback_query_id": callback["id"]})
    chat_id = callback["message"]["chat"]["id"]
    action, _, key = callback.get("data", "").partition(":")
    if key == "photo":
        report = photo_reports.get(chat_id)
        if report is None:  # the bot restarted since the photo was read
            tg.send(chat_id, "Send the photo again, please.")
            return
    elif key in DEMO_SUPPLIERS:
        report = run_supplier(key)
    else:
        return
    if action == "s":
        tg.send(chat_id, summary(report), move_buttons(key))
    elif action == "a":
        tg.send(chat_id, absorb_text(report), move_buttons(key))
    elif action == "r":
        reprice(tg, chat_id, report)
    elif action == "n":
        tg.send(chat_id, "Writing the email...")
        tg.send(chat_id, negotiate_text(report), move_buttons(key))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    llm.load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN is missing")
    tg = Telegram(token)
    offset = 0
    log.info("bot started")
    while True:
        try:
            updates = tg.call("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]})
        except (urllib.error.URLError, TimeoutError) as error:
            log.warning("getUpdates failed: %s", error)
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                if "callback_query" in update:
                    handle_callback(tg, update["callback_query"])
                elif "message" in update:
                    handle_message(tg, update["message"])
            except Exception:  # one bad update must not stop the bot
                log.exception("update %s failed", update["update_id"])
                chat = (update.get("message") or update.get("callback_query", {}).get("message") or {}).get("chat", {})
                if chat.get("id"):
                    try:
                        tg.send(chat["id"], "Something went wrong on my side. Try again, or use the app: " + SITE)
                    except Exception:
                        pass


if __name__ == "__main__":
    main()
