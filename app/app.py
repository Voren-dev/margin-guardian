"""Margin Guardian: the app. Run with:  streamlit run app/app.py"""
import streamlit as st

st.set_page_config(page_title="Margin Guardian", page_icon="🛡️", layout="centered")

pages = [
    st.Page("pages/bill.py", title="The bill", default=True),
    st.Page("pages/change.py", title="One change"),
    st.Page("pages/email.py", title="The email"),
    st.Page("pages/how.py", title="How it works"),
]
st.navigation(pages, position="hidden").run()
