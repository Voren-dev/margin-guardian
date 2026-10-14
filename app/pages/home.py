"""Start page: drop a supplier's new price list, or pick one from the demo.

The steps shown while it works are the real steps of the chain, run one by one.
The demo PDFs are not read again here: their saved, checked readings are used.
"""
import time

import streamlit as st

from pipeline import CATALOG_PATH, SUPPLIERS_DIR, supplier_report
from mg.analyze import analyze  # after pipeline, which puts the project on the path
from mg.extract import extract_price_list
from mg.match import diff_price_lists, match_to_catalog
from mg.moves import build_moves
from mg.report import DEMO_SUPPLIERS, identify
from mg.review import audit

PAUSE = 0.35  # seconds between steps, so a person can follow them


def process(key: str):
    """Runs the chain on one demo supplier, showing each step, then opens its page."""
    supplier, old_name, new_name = DEMO_SUPPLIERS[key]
    is_pdf = new_name.lower().endswith(".pdf")
    with st.status(f"Working on {new_name}", expanded=True) as status:
        new_lines, notes = extract_price_list(SUPPLIERS_DIR / "new" / new_name)
        how = "Gemma on AMD through the Evolus extractor, every price checked against the PDF" if is_pdf else "plain code, it is already a table"
        st.write(f"✓ Read **{len(new_lines)} rows** from {supplier} ({how})")
        time.sleep(PAUSE)

        old_lines, _ = extract_price_list(SUPPLIERS_DIR / "old" / old_name)
        st.write(f"✓ Found the previous price list: {old_name}")
        time.sleep(PAUSE)

        changes = diff_price_lists(old_lines, new_lines)
        st.write(f"✓ Compared line by line: **{len(changes)} changes**")
        time.sleep(PAUSE)

        matched = match_to_catalog(changes, CATALOG_PATH)
        linked = sum(1 for change in matched if change.sku)
        st.write(f"✓ Linked {linked} of them to your catalog")
        time.sleep(PAUSE)

        findings = analyze(matched, notes, new_lines)
        st.write(f"✓ Calculated unit cost in EUR, margin and monthly cost for {len(findings)} products")
        time.sleep(PAUSE)

        passed = [finding for finding in findings if audit(finding).passed]
        st.write(f"✓ Reviewer: {len(passed)} of {len(findings)} trace back to their source row")
        time.sleep(PAUSE)

        moves = build_moves(passed)
        st.write(f"✓ Prepared {len(moves)} moves: absorb, reprice, negotiate")
        time.sleep(PAUSE)
        status.update(label=f"{new_name}: done", state="complete")

    supplier_report(key)  # warm the cache for the next page
    st.session_state["supplier_key"] = key
    st.session_state.setdefault("opened", set()).add(key)
    st.switch_page("pages/supplier.py")


st.markdown("## New price list")
st.write("Drop the price list a supplier just sent you. Margin Guardian reads it, compares it with the last one, "
         "and tells you what changed, what it costs you, and what to do.")

uploaded = st.file_uploader("PDF or Excel price list", type=["pdf", "xlsx"], label_visibility="collapsed")
if uploaded is not None:
    key = identify(uploaded.getvalue())
    if key is None:
        st.warning(
            "This demo knows only the three suppliers of its invented shop, so it can compare "
            "only their price lists. Try one of them below."
        )
    else:
        process(key)

st.write("")
st.markdown("##### Or try one from the demo")
for column, (key, (supplier, _, new_name)) in zip(st.columns(3), DEMO_SUPPLIERS.items()):
    with column, st.container(border=True):
        st.markdown(f"**{supplier}**")
        st.caption(new_name)
        if st.button("Check this price list", key=f"demo-{key}", use_container_width=True):
            st.session_state["run"] = key

if st.session_state.get("run"):
    process(st.session_state.pop("run"))
