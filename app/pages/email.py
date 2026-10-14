"""Page 3: the email to a supplier. Prepared, never sent from here."""
from urllib.parse import quote

import streamlit as st

from pipeline import report_email, supplier_email

st.page_link("pages/change.py", label="← Back to the change")
supplier = st.session_state.get("supplier")
if supplier is None:
    st.info("Open a change and press 'Write the email'.")
    st.stop()

# the reading made on the start page (a photo, a live reading), if there is one for this supplier
report = next((r for r in st.session_state.get("readings", {}).values() if r.supplier == supplier), None)
try:
    draft = report_email(report) if report else supplier_email(supplier)
except Exception:  # the checks refused the text, or Evolus could not be reached: no details to the visitor
    st.error("The email could not be prepared right now. The numbers are unchanged.")
    st.stop()

st.markdown(f"### Email to {supplier}")
st.caption("Nothing has been sent. Read it, change what you want, and send it from your own mailbox.")

st.markdown(f"**To:** {draft.to}  \n**Subject:** {draft.subject}")
st.text_area("Text", draft.body, height=520, label_visibility="collapsed")

link = f"mailto:{draft.to}?subject={quote(draft.subject)}&body={quote(draft.body)}"
st.link_button("Open in my email app", link, type="primary")

st.divider()
st.caption(
    f"The sentences were written by the Evolus email tool, which is not allowed to write numbers. "
    f"The {draft.numbers_checked} numbers in this email were put in by code, from the calculations, "
    f"and each one was checked against them."
)
st.caption("Demo: the supplier address ends in .example, a reserved domain that reaches nobody.")
