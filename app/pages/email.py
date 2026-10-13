"""Page 3: the email to a supplier. Prepared, never sent from here."""
from urllib.parse import quote

import streamlit as st

from pipeline import supplier_email

st.page_link("pages/change.py", label="← Back to the change")
supplier = st.session_state.get("supplier")
if supplier is None:
    st.info("Open a change and press 'Write the email'.")
    st.stop()

try:
    draft = supplier_email(supplier)
except Exception as error:  # the checks refused the text, or Evolus could not be reached
    st.error(f"The email could not be prepared: {error}")
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
