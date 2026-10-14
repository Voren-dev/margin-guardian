"""Lets the visitor ask for a live reading of a demo PDF, to see the model on AMD at work."""
import time
from pathlib import Path

import streamlit as st

from mg.extract.pdf import ExtractionError, keys_are_set, live_reads_left, read_live


def show_live_reading(path: Path, source):
    """A button that reads the PDF again right now and compares the result with the row on screen."""
    with st.expander("Not convinced? Read this price list again, live"):
        st.write(
            "What you see above was read on 14 October 2026. Press the button and Gemma, Google's open "
            "model, reads the PDF again now on AMD servers, through the Evolus extractor. "
            "Then code checks every price against the PDF. It takes about half a minute."
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
        with st.spinner("The model on AMD is reading the PDF... this takes about half a minute."):
            try:
                data = read_live(path)
            except ExtractionError as error:
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
