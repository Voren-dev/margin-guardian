"""Page 4: how it works, in one screen."""
import streamlit as st

st.page_link("pages/home.py", label="← Back to the start")
st.markdown("### How it works")
st.markdown("**The AI reads and writes. The code does the math. The person signs off.**")

st.divider()
steps = [
    ("1 · Read", "PDF price lists are read by a document extractor on Evolus, running on Gemma, Google's open model, on AMD servers. Spreadsheets are read by plain code: they are already tables. A photo of a printed price list (in the app or the Telegram bot) is read by Gemma directly, twice: a row counts only if both readings agree. If Gemma does not answer, Qwen reads it, on the same AMD servers."),
    ("2 · Check the reading", "Code reads the text of the PDF on its own and checks every extracted price and pack size against its row. If a price or a pack size is wrong, or a row is missing, the price list is refused."),
    ("3 · Compare", "Old price list against new one, product by product. A changed pack size is never called a lower price."),
    ("4 · Calculate", "Cost per unit in EUR, margin before and after, cost per month. Sales come from the last 12 months; how customers react to price is estimated from 24 months of past price changes."),
    ("5 · Review", "Before a number reaches the screen, code goes back to the row it cites: the unit cost must come out of a price printed there, with that row's pack size and currency, and the margins and the monthly cost must agree with it."),
    ("6 · You decide", "Three moves with their numbers. Nothing is sent or changed until you say so."),
]
for title, text in steps:
    st.markdown(f"**{title}**  \n{text}")

st.divider()
st.markdown("##### What it does not catch")
st.write(
    "In a PDF the check covers prices, pack sizes and missing rows. It does not cover the minimum order. "
    "On a photo there is no text to check against, so two readings must agree instead: two readings "
    "wrong in the same way would pass. In those cases you decide, looking at the original row."
)
st.markdown("**Evolus workspace: Voren** · the extractor \"Supplier price lists\" and the email tool.")
st.caption("Demo data: the shop, the suppliers and the prices are made up. The method is real.")
