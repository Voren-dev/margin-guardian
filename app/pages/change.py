"""Page 2: one change. Where it comes from, how it is calculated, what you can do."""
import streamlit as st

from pipeline import HIDDEN_KINDS, document_path, euro, label, load_demo
from source_view import show_source
from live_view import show_live_reading
from trace_view import show_trace

demo = load_demo()
by_id = {finding.id: finding for finding in demo["findings"]}
finding = by_id.get(st.session_state.get("finding_id"))

back = st.session_state.get("back_to", "pages/overview.py")
st.page_link(back, label="← Back to the price list" if back.endswith("supplier.py") else "← Back to the overview")
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

newest = finding.sources[-1] if finding.kind != "surcharge_note" else finding.sources[0]
if newest.document.lower().endswith(".pdf"):
    show_live_reading(document_path(newest.document), newest)

st.divider()
st.markdown("##### How it is calculated")
show_trace(finding.calc_trace)
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
kinds = [kind for kind in ("absorb", "negotiate", "reprice") if kind in moves]

for column, kind in zip(st.columns(3), ("absorb", "negotiate", "reprice")):
    move = moves.get(kind)
    with column:
        if move is None:
            st.metric(titles[kind], "n/a")
            st.caption("Not enough past price changes to estimate how sales react.")
            continue
        st.metric(f"{titles[kind]} · per year", euro(move.yearly_impact_eur, sign=True))
        if move.units_delta:
            st.caption(f"{move.units_delta:+.0f} units a year")

st.write("")
if st.button(f"Write the email to {product.supplier}", type="primary"):
    st.session_state["supplier"] = product.supplier
    st.switch_page("pages/email.py")
st.caption("It prepares the text. Nothing is sent: you send it yourself.")

st.write("")
st.markdown("##### How each move is calculated")
for tab, kind in zip(st.tabs([titles[kind] for kind in kinds]), kinds):
    with tab:
        st.write(moves[kind].assumptions)
        show_trace(moves[kind].calc_trace)
