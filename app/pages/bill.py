"""Page 1: what happened, what it costs, what you can do, and the list of changes.

Read top to bottom like the pitch: what arrived, the trap nobody sees, the number,
the three moves in words, then the details.
"""
import streamlit as st

from pipeline import HIDDEN_KINDS, OTHER_KINDS, euro, label, load_demo
from mg.config import FX_TO_EUR  # after pipeline, which puts the project on the path
from mg.export import new_prices_csv

SYMBOLS = {"EUR": "€", "GBP": "£"}

demo = load_demo()
findings, moves, products = demo["findings"], demo["moves"], demo["products"]

increases = [finding for finding in findings if finding.id in moves]
hidden = [finding for finding in findings if finding.kind in HIDDEN_KINDS]


def total(kind: str) -> float:
    return sum(moves[finding.id][kind].yearly_impact_eur for finding in increases if kind in moves[finding.id])


def open_change(finding_id: str):
    st.session_state["finding_id"] = finding_id
    st.switch_page("pages/change.py")


def listed_price(cost_eur: float, source) -> str:
    """The price as the supplier lists it: per pack, in its currency, e.g. '£9.60'."""
    price = cost_eur / FX_TO_EUR[source.currency] * source.pack_size
    return f"{SYMBOLS.get(source.currency, source.currency + ' ')}{price:.2f}"


st.markdown("#### MARGIN GUARDIAN")
st.caption("The purchasing manager a small shop cannot afford.")
st.write("3 suppliers sent new price lists. Every line was read, compared with the old list and checked.")

# The trap nobody sees: a pack that got smaller, so the listed price went down.
pack = next((finding for finding in findings if finding.kind == "pack_change"), None)
if pack:
    old_src, new_src = pack.sources
    with st.container(border=True):
        st.caption(f"{products[pack.sku].name} · {products[pack.sku].supplier}")
        st.markdown(f"### {listed_price(pack.old_unit_cost_eur, old_src)} → {listed_price(pack.new_unit_cost_eur, new_src)}")
        st.markdown(
            f"Cheaper? **No.** The pack went from {old_src.pack_size} to {new_src.pack_size}: "
            f":orange[**{pack.pct_change:+.1f}% per piece**]."
        )
        if st.button("Show me the rows in the price list", key="hook"):
            open_change(pack.id)

st.write("")
st.markdown("Hidden in these price lists, if you do nothing:")
st.markdown(f"# {euro(-total('absorb'))} a year")
st.caption(f"{len(findings)} changes · {len(hidden)} of them easy to miss: a smaller pack, a surcharge in a footnote")

st.write("")
st.markdown("##### What you can do")
left, middle, right = st.columns(3)
with left:
    st.markdown("**Absorb it**")
    st.caption("Keep your prices, pay the increase.")
    st.markdown(f"#### {euro(total('absorb'), sign=True)}")
with middle:
    st.markdown("**Negotiate**")
    st.caption("Ask each supplier to take back half. The email is ready in each change.")
    st.markdown(f"#### {euro(total('negotiate'), sign=True)}")
with right:
    st.markdown("**Reprice**")
    st.caption("Raise your prices back to your old margin, never above the cheapest competitor.")
    st.markdown(f"#### {euro(total('reprice'), sign=True)}")
    st.download_button(
        "New prices (CSV)",
        new_prices_csv(
            [move for by_kind in moves.values() for move in by_kind.values()],
            {finding.id: finding.sku for finding in findings},
            products,
        ),
        file_name="margin-guardian-new-prices.csv",
        mime="text/csv",
        help="The prices of the reprice move, ready to import into your shop.",
    )
st.caption("Euros per year, compared with your profit before the new price lists.")

st.divider()
st.markdown("##### What changed")
st.caption("Open a change to see its row in the price list, how every number is calculated, and the email to the supplier.")

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
        open_change(finding.id)

if demo["other_changes"]:
    noticed = []
    for change in demo["other_changes"]:
        line = change.new or change.old
        text = f"{line.supplier_code} {OTHER_KINDS[change.kind]}"
        if change.kind == "moq_change":
            text += f" ({change.old.min_order_qty} → {change.new.min_order_qty})"
        noticed.append(text)
    st.caption("Also noticed, no cost today: " + " · ".join(noticed) + ".")

if demo["held_back"]:
    st.divider()
    st.warning(f"{len(demo['held_back'])} result(s) held back by the reviewer: the numbers did not trace back to their source.")

st.divider()
st.caption("Demo data: the shop, the suppliers and the prices are made up. The method is real.")
st.page_link("pages/how.py", label="How it works →")
