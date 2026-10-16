"""Margin Guardian: the app. Run with:  streamlit run app/app.py

The sidebar is the same on every page: a new price list, the price lists received,
the overview of all of them, and how it works.
"""
import streamlit as st

st.set_page_config(page_title="Margin Guardian", page_icon="🛡️", layout="wide")

from pipeline import SUPPLIER_KEYS, supplier_report  # noqa: E402  (after set_page_config)

pages = [
    st.Page("pages/home.py", title="New price list", default=True),
    st.Page("pages/supplier.py", title="Price list"),
    st.Page("pages/overview.py", title="Overview"),
    st.Page("pages/change.py", title="One change"),
    st.Page("pages/email.py", title="The email"),
    st.Page("pages/how.py", title="How it works"),
]
current = st.navigation(pages, position="hidden")

# Easy to read for someone who is not at ease with computers: bigger text, grey notes that are still
# readable on the dark background, tabs that look like buttons. Smaller numbers in the metric tiles,
# so euro amounts fit on a laptop screen. The top-right menu goes: its light/dark switch does nothing,
# the colours are fixed in config.toml.
st.markdown(
    "<style>"
    "html{font-size:18px}"
    "[data-testid='stCaptionContainer'],[data-testid='stCaptionContainer'] p{color:#C9C3B5 !important;font-size:0.95rem}"
    "[data-testid='stMetricValue']{font-size:1.7rem}"
    "[data-testid='stMainMenu']{display:none}"
    "[data-testid='stTabs'] [role='tablist']{gap:0.5rem;border:none;box-shadow:none}"
    "[data-testid='stTab']{border:1px solid #3A4D47;border-radius:8px;padding:0.45rem 1rem;background:#1F2E2A}"
    "[data-testid='stTab'] p{font-size:1.05rem !important;font-weight:600}"
    "[data-testid='stTab'][aria-selected='true']{border-color:#FFB84D;background:#2A3A35}"
    "[data-testid='stSidebar'] button p{font-size:0.82rem;white-space:nowrap}"
    "</style>",
    unsafe_allow_html=True,
)

opened = st.session_state.setdefault("opened", set())

with st.sidebar:
    # the name goes home too, as on most sites; "Home" is spelled out for whoever looks for it
    st.page_link("pages/home.py", label="Home", icon="🏠")  # where a new price list is uploaded
    st.caption("Demo shop: Rideline Cycles, invented")

    st.write("")
    st.caption("DEMO PRICE LISTS, ALREADY LOADED")
    for key in SUPPLIER_KEYS:
        report = st.session_state.get("readings", {}).get(key) or supplier_report(key)
        selected = current.title == "Price list" and st.session_state.get("supplier_key") == key
        mark = "● " if key not in opened else ""
        if st.button(
            f"{mark}{report.supplier} · {len(report.findings)} changes",
            key=f"side-{key}",
            width="stretch",
            type="primary" if selected else "secondary",
        ):
            st.session_state["supplier_key"] = key
            opened.add(key)
            st.switch_page("pages/supplier.py")
    st.caption("Three invented suppliers, ready to open. In a real shop they would arrive by email. ● = not opened yet.")

    st.write("")
    st.page_link("pages/overview.py", label="Overview of all price lists", icon="📊")
    st.page_link("pages/how.py", label="How it works", icon="⚙️")
    st.divider()
    st.caption("Demo data: the shop, the suppliers and the prices are made up. The method is real.")

# The name of the app on every page, also when the sidebar is closed.
st.markdown(
    "<div style='text-align:center;font-size:2.1rem;font-weight:800;color:#FFB84D;letter-spacing:0.02em;"
    "margin:-1.5rem 0 1.5rem 0;padding-bottom:0.8rem;border-bottom:1px solid #3A4D47'>🛡️ Margin Guardian</div>",
    unsafe_allow_html=True,
)
current.run()
