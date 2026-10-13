"""Page 2: one change. Where it comes from, how it is calculated, what you can do."""
import streamlit as st

from pipeline import HIDDEN_KINDS, document_path, euro, label, load_demo
from source_view import show_source

demo = load_demo()
by_id = {finding.id: finding for finding in demo["findings"]}
finding = by_id.get(st.session_state.get("finding_id"))

st.page_link("pages/bill.py", label="← Back to all changes")
if finding is None:
    st.info("Pick a change from the list.")
    st.stop()

product = demo["products"][finding.sku]
st.markdown(f"### {product.name}")
tag = f":orange[**{label(finding)}**]" if finding.kind in HIDDEN_KINDS else label(finding)
st.markdown(f"{product.supplier} · {tag}")
st.write(finding.rationale)

st.divider()
st.markdown("##### Where it comes from")
captions = ("In the footnote", "The product row") if finding.kind == "surcharge_note" else ("New price list", "Old price list")
for source, caption in zip(reversed(finding.sources), captions):
    show_source(document_path(source.document), source, caption)

st.divider()
st.markdown("##### How it is calculated")
st.code(finding.calc_trace, language=None, wrap_lines=True)
verdict = demo["verdicts"][finding.id]
st.caption(f"✓ Checked by the reviewer: {verdict.reason}.")

st.divider()
moves = demo["moves"].get(finding.id)
if not moves:
    st.markdown("##### Nothing to do")
    st.write(f"This price went down: you save about {euro(-finding.monthly_impact_eur)} a month.")
    st.stop()

st.markdown("##### Your three moves")
st.caption("Each one compared with the yearly profit on this product before the new price list.")
titles = {"absorb": "Absorb", "negotiate": "Negotiate", "reprice": "Reprice"}
for column, kind in zip(st.columns(3), ("absorb", "negotiate", "reprice")):
    move = moves.get(kind)
    with column:
        if move is None:
            st.metric(titles[kind], "n/a")
            st.caption("Not enough past price changes to estimate how sales react.")
            continue
        st.metric(titles[kind], euro(move.yearly_impact_eur, sign=True), help="per year")
        if move.units_delta:
            st.caption(f"{move.units_delta:+.0f} units a year")
        st.caption(move.assumptions)
        with st.expander("How it is calculated"):
            st.code(move.calc_trace, language=None, wrap_lines=True)
