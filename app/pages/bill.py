"""Page 1: what the new price lists cost, and the list of changes."""
import streamlit as st

from pipeline import HIDDEN_KINDS, euro, label, load_demo

demo = load_demo()
findings, moves, products = demo["findings"], demo["moves"], demo["products"]

increases = [finding for finding in findings if finding.id in moves]
hidden = [finding for finding in findings if finding.kind in HIDDEN_KINDS]


def total(kind: str) -> float:
    return sum(moves[finding.id][kind].yearly_impact_eur for finding in increases if kind in moves[finding.id])


st.markdown("#### MARGIN GUARDIAN")
st.caption("The purchasing manager a small shop cannot afford.")

st.write("")
st.markdown("Your new price lists hide")
st.markdown(f"# {euro(-total('absorb'))} a year")
st.caption(f"{len(findings)} changes in 3 price lists · {len(hidden)} of them hidden")

st.write("")
left, middle, right = st.columns(3)
left.metric("If you absorb", euro(total("absorb"), sign=True))
middle.metric("If you negotiate", euro(total("negotiate"), sign=True))
right.metric("If you reprice", euro(total("reprice"), sign=True))

st.divider()
st.markdown("##### What changed")

for finding in findings:
    product = products[finding.sku]
    name, tag, change, cost, button = st.columns([3.1, 2.7, 0.9, 1.3, 1.2], vertical_alignment="center")
    name.markdown(f"**{product.name}**  \n:gray[{product.supplier}]")
    if finding.kind in HIDDEN_KINDS:
        tag.markdown(f":orange[**{label(finding)}**]")
    else:
        tag.markdown(label(finding))
    change.markdown(f"{finding.pct_change:+.1f}%")
    cost.markdown(f"{euro(finding.monthly_impact_eur, sign=True)}/m".replace("+", "&#43;"))
    if button.button("Details", key=finding.id, use_container_width=True):
        st.session_state["finding_id"] = finding.id
        st.switch_page("pages/change.py")

if demo["held_back"]:
    st.divider()
    st.warning(f"{len(demo['held_back'])} result(s) held back by the reviewer: the numbers did not trace back to their source.")

st.divider()
st.caption("Demo data: the shop, the suppliers and the prices are made up. The method is real.")
st.page_link("pages/how.py", label="How it works →")
