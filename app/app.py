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

# Smaller numbers in the metric tiles, so euro amounts fit on a laptop screen.
st.markdown("<style>[data-testid='stMetricValue']{font-size:1.7rem}</style>", unsafe_allow_html=True)

opened = st.session_state.setdefault("opened", set())

with st.sidebar:
    st.markdown("### 🛡️ Margin Guardian")
    st.caption("Rideline Cycles · demo shop")
    if st.button("＋ New price list", use_container_width=True, type="primary"):
        st.switch_page("pages/home.py")

    st.write("")
    st.caption("PRICE LISTS RECEIVED")
    for key in SUPPLIER_KEYS:
        report = supplier_report(key)
        selected = current.title == "Price list" and st.session_state.get("supplier_key") == key
        mark = "● " if key not in opened else ""
        if st.button(
            f"{mark}{report.supplier} · {len(report.findings)} changes",
            key=f"side-{key}",
            use_container_width=True,
            type="primary" if selected else "secondary",
        ):
            st.session_state["supplier_key"] = key
            opened.add(key)
            st.switch_page("pages/supplier.py")
    st.caption("● not opened yet")

    st.write("")
    st.page_link("pages/overview.py", label="Overview of all price lists", icon="📊")
    st.page_link("pages/how.py", label="How it works", icon="⚙️")
    st.divider()
    st.caption("Demo data: the shop, the suppliers and the prices are made up. The method is real.")

current.run()
