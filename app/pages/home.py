"""Start page: drop a supplier's new price list (PDF, spreadsheet or photo), or pick one from the demo.

The steps shown while it works are the real steps of the chain, run one by one.
A demo card uses the saved, checked reading of its PDF. A file dropped here is read
again live; if the model on AMD cannot be reached, the page says so, says which
service failed, and falls back to the saved reading.
"""
import time

import streamlit as st

from live_view import live_model, read_by, read_on
from pipeline import SUPPLIERS_DIR
from mg import llm  # after pipeline, which puts the project on the path
from mg.extract import extract_price_list
from mg.extract.pdf import ExtractionError, keys_are_set, live_reads_left, read_pdf_price_list_live
from mg.extract.photo import PHOTO_MODELS, PhotoError, explain, read_photo
from mg.report import DEMO_SUPPLIERS, identify, run_supplier, supplier_of

PAUSE = 0.35  # seconds between steps, so a person can follow them
IMAGE_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}


def what_failed(error: Exception) -> str:
    """One sentence on what failed, so the person on stage knows whom it depends on."""
    if "daily limit of live readings" in str(error):  # not a 429 of Token Factory
        return "Today's limit of live readings on this demo is used up."
    if "refused after" in str(error):  # not "Connection refused": that is Evolus down
        return "The live reading did not pass the check against the PDF, so it was not used."
    if isinstance(error, llm.LLMError):
        return "AMD Token Factory did not answer: Gemma could not read the footnotes."
    return f"The Evolus extractor did not answer. It runs on {live_model()}, so one of the two is down."


def read_uploaded_pdf(key: str):
    """The new price list read live, or the saved reading with the reason it was used. Returns (lines, notes)."""
    path = SUPPLIERS_DIR / "new" / DEMO_SUPPLIERS[key][2]
    if keys_are_set() and live_reads_left() > 0:
        started = time.time()
        try:
            with st.spinner(f"The Evolus extractor is reading the PDF with {live_model()}, one to three minutes..."):
                lines, notes = read_pdf_price_list_live(path)
        except (ExtractionError, llm.LLMError, OSError) as error:
            note = f"⚠️ {what_failed(error)} Using the reading of this file saved on {read_on(path)}, checked the same way."
            st.warning(note)
            st.session_state.setdefault("reading_notes", {})[key] = note
        else:
            st.write(f"✓ Read **just now** by the Evolus extractor with {live_model()} ({time.time() - started:.0f} s): "
                     f"**{len(lines)} rows**, every price found on its row in the PDF")
            return lines, notes
    else:
        st.write(f"Live reading is not available on this copy right now: using the reading saved on {read_on(path)}.")
    lines, notes = extract_price_list(path)
    st.write(f"✓ Read **{len(lines)} rows** (saved reading)")
    return lines, notes


def process(key: str, source: str = "demo", photo: tuple[bytes, str] | None = None):
    """Runs the chain on one supplier, showing each step, then opens its page.

    source: "demo" (a demo card: saved reading), "upload" (a file dropped here: read live) or "photo".
    """
    supplier, old_name, new_name = DEMO_SUPPLIERS[key]
    st.session_state.setdefault("reading_notes", {}).pop(key, None)
    with st.status(f"Working on {'the photo' if photo else new_name}", expanded=True) as status:
        if photo:
            lines, notes = photo[1]
            st.write(photo[0])
            if photo[0].startswith("⚠️"):
                st.session_state["reading_notes"][key] = photo[0].split("  \n")[0]
        elif source == "upload" and new_name.lower().endswith(".pdf"):
            lines, notes = read_uploaded_pdf(key)
        else:
            lines, notes = extract_price_list(SUPPLIERS_DIR / "new" / new_name)
            path = SUPPLIERS_DIR / "new" / new_name
            how = f"saved reading, {read_by(path)}, every price checked against the PDF" if path.suffix == ".pdf" else "plain code, it is already a table"
            st.write(f"✓ Read **{len(lines)} rows** from {supplier} ({how})")
        time.sleep(PAUSE)

        # the whole chain runs once; the steps below are read from its result
        report = run_supplier(key, lines, notes, "photo of the price list" if photo else new_name, complete=not photo)
        st.write(f"✓ Found the previous price list: {old_name}")
        time.sleep(PAUSE)
        priced = [change for change in report.changes if change.kind in ("price_up", "price_down", "pack_change")]
        others = len(report.changes) - len(priced)
        st.write(f"✓ Compared line by line: **{len(priced)} price changes**" + (f", {others} other change{'s' if others > 1 else ''}" if others else ""))
        time.sleep(PAUSE)
        # a surcharge in a footnote leaves the listed prices alone, so the comparison above does not count it
        noted = [finding for finding in report.findings + report.held_back if finding.kind == "surcharge_note"]
        if noted:
            st.write(f"✓ Read the footnotes: +{noted[0].pct_change:g}% on **{len(noted)} marked rows**")
            time.sleep(PAUSE)
        st.write(f"✓ Linked {sum(1 for change in report.changes if change.sku)} of them to your catalog")
        time.sleep(PAUSE)
        checked = len(report.findings) + len(report.held_back)
        st.write(f"✓ Calculated unit cost in EUR, margin and monthly cost for {checked} products")
        time.sleep(PAUSE)
        st.write(f"✓ Reviewer: {len(report.findings)} of {checked} trace back to their source row")
        time.sleep(PAUSE)
        st.write(f"✓ Prepared the three moves for {len(report.increases())} increases: absorb, raise your prices, negotiate")
        time.sleep(PAUSE)
        status.update(label=f"{'Photo' if photo else new_name}: done", state="complete")

    # the supplier page shows this reading, not the saved one
    st.session_state.setdefault("readings", {})[key] = report
    st.session_state.setdefault("photos", {}).pop(key, None)
    st.session_state.setdefault("photo_lines", {}).pop(key, None)
    if photo:
        st.session_state["photos"][key] = photo[2]
        st.session_state["photo_lines"][key] = photo[1][0]  # the rows read, shown under the photo
    st.session_state["supplier_key"] = key
    st.session_state.setdefault("opened", set()).add(key)
    time.sleep(1.5 if source != "demo" else 0)  # a moment to read the first line before the page changes
    st.switch_page("pages/supplier.py")


def process_photo(content: bytes, mime: str):
    """Reads a photo (Gemma, or Qwen if Gemma is down), finds the supplier, then runs the chain."""
    started = time.time()
    with st.spinner("Reading the photo on AMD, twice, to check every number (Gemma first, Qwen if Gemma does not answer). One or two minutes..."):
        try:
            _, lines, notes, dropped, model = read_photo(content, mime)
        except (PhotoError, llm.LLMError) as error:
            st.error("⚠️ " + explain(error))
            return
    key = supplier_of(lines)
    if key is None:
        st.warning("The photo was read, but it is not a price list of one of the three demo suppliers.")
        return
    first = (f"✓ Read the photo **just now** with {model} on AMD ({time.time() - started:.0f} s), twice: "
             f"**{len(lines)} rows** on which both readings agree" + (f", {dropped} left out" if dropped else ""))
    if model != PHOTO_MODELS[0]:
        first = f"⚠️ Gemma on AMD Token Factory did not answer, so {model} read the photo instead.  \n" + first
    process(key, "photo", (first, (lines, notes), content))


st.markdown("## Upload a price list")
st.write("Drop the price list a supplier just sent you, or a photo of it. Margin Guardian reads it, compares it with "
         "the last one, and tells you what changed, what it costs you, and what to do.")

uploaded = st.file_uploader("PDF, Excel or photo of a price list", type=["pdf", "xlsx", *IMAGE_TYPES], label_visibility="collapsed")
if uploaded is not None and st.session_state.get("done_upload") != uploaded.file_id:
    st.session_state["done_upload"] = uploaded.file_id  # read each dropped file once, not on every rerun
    extension = uploaded.name.rsplit(".", 1)[-1].lower()
    if extension in IMAGE_TYPES:
        process_photo(uploaded.getvalue(), IMAGE_TYPES[extension])
    else:
        key = identify(uploaded.getvalue())
        if key is None:
            st.warning(
                "This demo knows only the three suppliers of its invented shop, so it can compare "
                "only their price lists. Try one of them below."
            )
        else:
            process(key, "upload")

st.write("")
st.markdown("##### Or try one from the demo")
for column, (key, (supplier, _, new_name)) in zip(st.columns(3), DEMO_SUPPLIERS.items()):
    with column, st.container(border=True):
        st.markdown(f"**{supplier}**")
        # the kind of file, not its long name: one line, so the three buttons stay level
        st.caption("Excel price list" if new_name.lower().endswith(".xlsx") else "PDF price list", help=new_name)
        if st.button("Check this price list", key=f"demo-{key}", width="stretch", type="primary"):
            st.session_state["run"] = key

if st.session_state.get("run"):
    process(st.session_state.pop("run"))
