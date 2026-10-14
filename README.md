# Margin Guardian

**The purchasing manager a small shop cannot afford.**

Built for the AMD Developer Hackathon: ACT III (lablab.ai), Evolus Business Agents track.
Live demo: **https://margin.voren.dev**

## The problem

A supplier sends a new price list. Brake pads: 9.60 last quarter, 5.10 now. Good news?
No. The pack went from four pads to two, so every pad costs 6% more.

A small online shop gets dozens of these lists, in PDF and Excel, in different languages and
currencies. Nobody has time to check every line, so the increases nobody notices eat the margin.

## What it does

1. **Reads** the new price lists (PDF and Excel) and the previous ones.
2. **Finds what changed**: price increases, smaller packs, surcharges written only in a footnote.
3. **Calculates the cost**: unit cost in EUR, margin before and after, cost per month and per year.
4. **Proposes three moves** for every increase, each with its numbers:
   - *absorb* it (what you lose in a year);
   - *reprice* (the price that restores the margin, capped by the cheapest competitor, with the
     sales you lose estimated from 24 months of history);
   - *negotiate* (where you land if the supplier gives up half the increase).
5. **Prepares the move**: the email to the supplier, or a CSV of new prices to import into the shop.
   Nothing is sent and nothing is changed: a person reads it and decides.

On the demo data it finds **19 changes in 3 price lists, 7 of them hidden**, worth about
**9,150 EUR a year** if nobody reacts.

## On Telegram

[@MarginGuardianbot](https://t.me/MarginGuardianbot): forward one of the demo price lists (or pick a
supplier) and get what changed, the cost in a year and three buttons: absorb, reprice (the CSV
arrives in the chat) or negotiate (the supplier email, not sent). Run it with
`.venv/bin/python bot/telegram_bot.py`.

## How it stays honest

**The AI reads and writes. The code does the math. The person signs off.**

- **No math in the model.** Costs, margins, euros and percentages are computed in Python
  (`mg/analyze.py`, `mg/moves.py`). Every number on screen comes with its calculation.
- **Every reading is checked against the PDF.** Code extracts the text of the PDF on its own and
  checks every price the model read against its row. A wrong price or a missing row means a new
  reading, and after three failures the price list is refused (`mg/extract/pdf.py`).
- **A reviewer written in code, not a second model.** Before a result reaches the screen,
  `mg/review.py` goes back to the rows it cites and redoes the math. If it does not match, the
  result is held back.
- **Numbers are pasted, not written.** In the supplier email the model writes the sentences; the
  figures are inserted by code from the calculated table, then checked again (`mg/negotiate.py`).
- **Click any number** and the source opens: the PDF page with that row highlighted, or the Excel row.

What it does not catch: a scanned PDF, and a pack size or minimum order read wrong (the check
covers prices and missing rows). For those, the person looks at the highlighted source row.

## Built on

| Piece | What runs there |
|---|---|
| **Gemma 4 31B on AMD Token Factory** | Reads the PDF price lists (through the Evolus extractor) and their footnotes. Open model, served on AMD GPUs |
| **Evolus** | Document extractor for the PDF price lists; AI tool `email` for the supplier email |
| **Python** | Comparison, unit costs, margins, sales forecast and price elasticity (numpy), the three moves, the reviewer |
| **Streamlit** | The app |

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/app.py
```

The app works without any key: it uses the saved readings of the demo price lists in
`data/demo/results/extract/`. With the keys in `.env` (copy `.env.example`), it can also read a
price list again live and write the supplier email.

Tests: `.venv/bin/pytest`. They include every trap listed in `data/demo/ANSWER_KEY.md`.

## Environment variables

| Name | What it is |
|---|---|
| `AMD_TOKENFACTORY_API_KEY` | Team API key from AMD Token Factory |
| `AMD_TOKENFACTORY_BASE_URL` | OpenAI-compatible base URL: `https://developer.amd.com.cn/radeon/api/v1` |
| `AMD_MODEL` | Model on AMD GPUs, `Gemma-4-31B-IT` |
| `EVOLUS_API_KEY` | API key of the Evolus workspace |
| `EVOLUS_APPLICATION_ID` | Evolus space ID, sent as `X-Application-Id` |
| `TELEGRAM_BOT_TOKEN` | Only for the Telegram bot, from BotFather |

## Project structure

```
mg/extract/     reading: pdf.py (Evolus extractor + check against the PDF), xlsx.py (plain code)
mg/match.py     old vs new price list, link to the shop catalog
mg/analyze.py   unit cost in EUR, margin, monthly impact
mg/forecast.py  monthly sales and price elasticity from the sales history
mg/moves.py     absorb, reprice, negotiate
mg/review.py    the reviewer
mg/negotiate.py the supplier email
mg/export.py    new prices as CSV
mg/report.py    the whole chain for one supplier, used by the bot
bot/            the Telegram bot
app/            the Streamlit app
data/demo/      invented shop, suppliers, prices and sales
tests/          one file per step
```

## Demo data

Everything in `data/demo/` is invented: the shop, the suppliers, the prices and the sales. See
`data/demo/README.md`. The method is real.

## What comes next

- Send the email from the shop's own mailbox, still one click to approve.
- OCR for scanned price lists, so the check compares two independent readings.
- Write the new prices straight into the shop's catalog, without a file in between.

## License

MIT, see `LICENSE`.
