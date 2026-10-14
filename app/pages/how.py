"""Page 4: how it works, in one screen."""
import streamlit as st

st.page_link("pages/bill.py", label="← Back to all changes")
st.markdown("### How it works")
st.markdown("**The AI reads and writes. The code does the math. The person signs off.**")

st.divider()
steps = [
    ("1 · Read", "PDF price lists are read by a document extractor on Evolus, running on an open model on AMD servers. Spreadsheets are read by plain code: they are already tables."),
    ("2 · Check the reading", "Code reads the text of the PDF on its own and checks every extracted price against its row. If a price is wrong or a row is missing, it tries again, then refuses the price list."),
    ("3 · Compare", "Old price list against new one, product by product. A changed pack size is never called a lower price."),
    ("4 · Calculate", "Cost per unit in EUR, margin before and after, cost per month. Sales come from the last 12 months; how customers react to price is estimated from past price changes."),
    ("5 · Review", "Before a number reaches the screen, code goes back to the row it cites: the unit cost must come out of a price printed there, with that row's pack size and currency, and the margins and the monthly cost must agree with it."),
    ("6 · You decide", "Three moves with their numbers. Nothing is sent or changed until you say so."),
]
for title, text in steps:
    st.markdown(f"**{title}**  \n{text}")

st.divider()
st.markdown("##### What it does not catch")
st.write(
    "The check covers prices and missing rows. It does not cover pack size or minimum order, "
    "and it cannot work on scanned documents. In those cases you decide, looking at the original row."
)
st.caption("Demo data: the shop, the suppliers and the prices are made up. The method is real.")
