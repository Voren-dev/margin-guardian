"""Lets the visitor ask for a live reading of a demo PDF, to see the model on AMD at work."""
import json
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from mg import config
from mg.extract.pdf import ExtractionError, extractor_model, keys_are_set, live_reads_left, read_live


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def read_on(path: Path) -> str:
    """The day the saved reading of this PDF was made, e.g. '14 October 2026'."""
    saved = json.loads((config.EXTRACT_RESULTS_DIR / f"{path.name}.json").read_text())
    day = datetime.fromisoformat(saved["extracted_at"])
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"  # not strftime: the server locale may not be English


def read_by(path: Path) -> str:
    """Who made the saved reading of this PDF, as written when it was saved."""
    saved = json.loads((config.EXTRACT_RESULTS_DIR / f"{path.name}.json").read_text())
    return saved["extracted_by"]


@st.cache_data(ttl=3600, show_spinner=False)
def live_model() -> str:
    """The model the Evolus extractor is set to right now, e.g. 'Gemma 4 31B on AMD Token Factory'."""
    try:
        return extractor_model()
    except Exception:  # Evolus not reachable: say what the demo is built on
        return "Gemma on AMD Token Factory"


def show_live_reading(path: Path, source):
    """A button that reads the PDF again right now and compares the result with the row on screen."""
    with st.container(border=True):
        st.markdown("**Not convinced? Read this price list again, live**")
        st.write(
            f"What you see above was read on {read_on(path)}. Press the button and the Evolus extractor "
            f"reads the PDF again now, with {live_model()}. "
            "Then code checks every price against the PDF. It takes one to three minutes."
        )
        if not keys_are_set():
            st.caption("Live reading is switched off on this copy of the app (no API keys).")
            return
        if live_reads_left() == 0:
            st.caption("Today's limit of live readings has been reached. Try again tomorrow.")
            return
        if not st.button("Read it again now", key=f"live-{path.name}"):
            return

        started = time.time()
        with st.spinner("The model on AMD is reading the PDF... this takes one to three minutes."):
            try:
                data = read_live(path)
            except ExtractionError as error:
                if "refused after" not in str(error):  # Evolus did not answer: not the check's doing
                    st.error("The Evolus extractor did not answer this time. The prices above are unchanged; try again later.")
                    return
                st.error(f"The reading was refused by the check: {error}")
                return
            except Exception:  # Evolus down, timeout, an answer of an unexpected shape: no details to the visitor
                st.error("The live reading failed this time. The prices above are unchanged; try again later.")
                return
        seconds = time.time() - started

        row = next((line for line in data["lines"] if line["supplier_code"] in source.raw_text), None)
        st.success(f"Read in {seconds:.0f} seconds: {len(data['lines'])} rows, every price found on its row in the PDF.")
        if row:
            st.write(f"This product, read just now: **{row['supplier_code']}** at **{row['price']:.2f} {data['currency']}**.")
            st.caption(f"Its row in the PDF: {row['raw_text']}")
