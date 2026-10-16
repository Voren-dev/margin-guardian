"""One price list received: the numbers on top, then tabs for changes, moves, the email and the document."""
import time
from urllib.parse import quote

import streamlit as st

from live_view import show_live_reading
from pipeline import HIDDEN_KINDS, OTHER_KINDS, SUPPLIERS_DIR, euro, label, report_email, supplier_report
from mg.config import FX_TO_EUR  # after pipeline, which puts the project on the path
from mg.export import new_prices_csv
from mg.report import DEMO_SUPPLIERS
from source_view import pdf_row_image, sheet_rows

SYMBOLS = {"EUR": "€", "GBP": "£"}
COUNT_STEPS = 24  # frames of the count-up on the first view
COUNT_PAUSE = 0.04  # seconds between frames: about one second in all
REVEAL_PAUSE = 0.6  # seconds before each hidden change appears
MOVE_CARD_HEIGHT = 340  # pixels: the three moves side by side, same height

key = st.session_state.get("supplier_key")
if key not in DEMO_SUPPLIERS:
    st.switch_page("pages/home.py")

# the reading made on the start page (a file read live, a photo), or else the saved one
report = st.session_state.get("readings", {}).get(key) or supplier_report(key)
photo = st.session_state.get("photos", {}).get(key)
supplier, old_name, new_name = DEMO_SUPPLIERS[key]
findings, products = report.findings, report.products
increases = report.increases()


def open_change(finding_id: str):
    st.session_state["finding_id"] = finding_id
    st.session_state["back_to"] = "pages/supplier.py"
    st.switch_page("pages/change.py")


def listed_price(cost_eur: float, source) -> str:
    """The price as the supplier lists it: per pack, in its currency, e.g. '£9.60'."""
    price = cost_eur / FX_TO_EUR[source.currency] * source.pack_size
    return f"{SYMBOLS.get(source.currency, source.currency + ' ')}{price:.2f}"


st.caption(f"PRICE LIST · {report.new_file} · compared with {old_name}")
st.markdown(f"## {supplier}")
if st.session_state.get("reading_notes", {}).get(key):
    st.warning(st.session_state["reading_notes"][key])

def short(amount: float) -> str:
    """-2799.4 -> '−€2,799'"""
    return ("−" if amount < 0 else "+") + f"€{abs(amount):,.0f}"


best = max(("negotiate", "reprice"), key=report.total)
# The first time a price list is opened, the numbers count up and the hidden changes appear one by one.
counted = st.session_state.setdefault("counted", set())
first_view = key not in counted
counted.add(key)

tiles = [tile.empty() for tile in st.columns(4)]
for step in range(1, COUNT_STEPS + 1) if first_view else [COUNT_STEPS]:
    share = step / COUNT_STEPS
    tiles[0].metric("Changes", round(len(findings) * share))
    tiles[1].metric("Easy to miss", round(len(report.hidden()) * share))
    tiles[2].metric("Per year, as it is", short(report.total("absorb") * share))
    tiles[3].metric(f"Per year, if you {best}", short(report.total(best) * share))
    if step < COUNT_STEPS:
        time.sleep(COUNT_PAUSE)

# What nobody would notice, first.
for finding in report.hidden():
    product = products[finding.sku]
    if first_view:
        time.sleep(REVEAL_PAUSE)
    with st.container(border=True):
        if finding.kind == "pack_change":
            old_src, new_src = finding.sources
            st.markdown(
                f"⚠️ **{product.name}**: {listed_price(finding.old_unit_cost_eur, old_src)} → "
                f"{listed_price(finding.new_unit_cost_eur, new_src)}. Cheaper? **No.** The pack went from "
                f"{old_src.pack_size} to {new_src.pack_size}: :orange[**{finding.pct_change:+.1f}% per piece**]."
            )
        else:
            st.markdown(f"⚠️ **{product.name}**: same listed price, but a footnote adds :orange[**{finding.pct_change:+g}%**].")
        if st.button("Show me", key=f"hidden-{finding.id}", type="primary"):
            open_change(finding.id)
    if len(report.hidden()) > 2:
        st.caption(f"…and {len(report.hidden()) - 1} more products under the same footnote, in the list below.")
        break

changes_tab, moves_tab, email_tab, document_tab = st.tabs(["What changed", "What to do", "Email to the supplier", "The price list"])

with changes_tab:
    head = st.columns([3.1, 2.7, 0.9, 1.3, 1.2])
    for column, title in zip(head, ("Product", "What changed", "Price", "Costs you", "")):
        column.caption(title.upper())
    for finding in findings:
        product = products[finding.sku]
        name, tag, change, cost, button = st.columns([3.1, 2.7, 0.9, 1.3, 1.2], vertical_alignment="center")
        name.markdown(f"**{product.name}**  \n:gray[code {product.sku}]")
        tag.markdown(f":orange[**{label(finding)}**]" if finding.kind in HIDDEN_KINDS else label(finding))
        change.markdown(f"{finding.pct_change:+.1f}%")
        cost.markdown(f"{euro(finding.monthly_impact_eur, sign=True)} a month".replace("+", "&#43;"))
        if button.button("Details", key=finding.id, width="stretch"):
            open_change(finding.id)
    others = report.other_changes()
    if others:
        noticed = []
        for change in others:
            text = f"{(change.new or change.old).supplier_code} {OTHER_KINDS[change.kind]}"
            if change.kind == "moq_change":
                text += f" ({change.old.min_order_qty} → {change.new.min_order_qty})"
            noticed.append(text)
        st.caption("Also noticed, no cost today: " + " · ".join(noticed) + ".")
    if report.held_back:
        st.warning(f"{len(report.held_back)} result(s) held back by the reviewer: the numbers did not trace back to their source.")

with moves_tab:
    st.caption("Euros per year, compared with your profit on these products before the new price list.")
    left, middle, right = st.columns(3)
    with left, st.container(border=True, height=MOVE_CARD_HEIGHT):
        st.markdown("**Absorb it**")
        st.caption("Keep your prices, pay the increase.")
        st.markdown(f"### {euro(report.total('absorb'), sign=True)}")
    with middle, st.container(border=True, height=MOVE_CARD_HEIGHT):
        st.markdown("**Negotiate**")
        st.caption("Ask the supplier to take back half of each increase.")
        st.markdown(f"### {euro(report.total('negotiate'), sign=True)}")
        if st.button("Write the email", key="negotiate-email", type="primary", width="stretch"):
            st.session_state["supplier"] = supplier
            st.session_state["email_back"] = "pages/supplier.py"
            st.switch_page("pages/email.py")
    with right, st.container(border=True, height=MOVE_CARD_HEIGHT):
        st.markdown("**Raise your prices**")
        st.caption("Back to your old margin, never above the cheapest competitor.")
        st.markdown(f"### {euro(report.total('reprice'), sign=True)}")
        reprices = [by_kind["reprice"] for by_kind in report.moves.values() if "reprice" in by_kind]
        st.download_button(
            "Download the new prices",
            new_prices_csv(reprices, {f.id: f.sku for f in findings}, products),
            file_name=f"new-prices-{key}.csv",
            mime="text/csv",
            width="stretch",
        )
        st.caption("A spreadsheet to import into your shop.")

with email_tab:
    try:
        draft = report_email(report)
    except Exception:  # the checks refused the text, or Evolus could not be reached
        st.error("The email could not be prepared right now. The numbers above are unchanged.")
    else:
        st.markdown(f"**To:** {draft.to}  \n**Subject:** {draft.subject}")
        st.text_area("Text", draft.body, height=420, label_visibility="collapsed")
        link = f"mailto:{draft.to}?subject={quote(draft.subject)}&body={quote(draft.body)}"
        st.link_button("Open in my email app", link, type="primary")
        st.caption(
            f"Nothing has been sent. The sentences come from the Evolus email tool, which is not allowed to write "
            f"numbers; the {draft.numbers_checked} numbers were put in by code and checked. "
            "Demo: the address ends in .example, a reserved domain that reaches nobody."
        )

with document_tab:
    path = SUPPLIERS_DIR / "new" / new_name
    if photo:
        st.image(photo, width="stretch")
        st.caption("The photo these numbers were read from.")
        read = st.session_state.get("photo_lines", {}).get(key, [])
        if read:
            st.dataframe(
                [{"Code": line.supplier_code, "Article": line.description,
                  "Price": f"{SYMBOLS.get(line.currency, line.currency + ' ')}{line.price:.2f}",
                  "Pack": line.pack_size, "Min. order": line.min_order_qty, "Note": " ".join(line.markers)}
                 for line in read],
                hide_index=True, width="stretch",
            )
            st.caption("What the AI read from the photo: only the rows where both readings agree. "
                       "Check it against the photo above.")
    elif path.suffix.lower() == ".pdf":
        first = increases[0].sources[-1] if increases else None
        footnotes = [finding for finding in report.hidden() if finding.kind == "surcharge_note"]
        if footnotes:  # the story of this price list is the footnote, so that is what gets highlighted
            row, note = footnotes[0].sources[0], footnotes[0].sources[-1]
            st.image(pdf_row_image(path, row.page or 1, note.raw_text), width="stretch")
            st.caption(f"The footnote that raises {len(footnotes)} products, highlighted.")
        elif first is not None and first.page:
            st.image(pdf_row_image(path, first.page, first.raw_text), width="stretch")
            st.caption(f"The row of the biggest change, highlighted: {products[increases[0].sku].name}.")
        if first is not None and first.page:
            show_live_reading(path, first)
    else:
        st.caption("A spreadsheet: read by plain code, it is already a table.")
        if increases:
            st.dataframe(sheet_rows(path, int(increases[0].sources[-1].row)), hide_index=True, width="stretch")

# Another price list: back to the top of the page. Last on the page, so it runs once the page is filled.
if st.session_state.get("last_supplier") != key:
    st.session_state["last_supplier"] = key
    st.iframe(
        "<script>const main = window.parent.document.querySelector('[data-testid=\"stMain\"]');"
        "let n = 0; const t = setInterval(() => { main.scrollTo(0, 0); if (++n > 8) clearInterval(t); }, 120);</script>",
        height=1,
    )
