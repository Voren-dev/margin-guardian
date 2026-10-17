# Margin Guardian

**Catch every hidden price increase.**

[![Demo](https://img.shields.io/badge/demo-margin.voren.dev-0A2A21)](https://margin.voren.dev)
[![Bot](https://img.shields.io/badge/telegram-@MarginGuardianbot-0A2A21)](https://t.me/MarginGuardianbot)
[![Pitch](https://img.shields.io/badge/pitch-PDF-FFB84D)](pitch/margin-guardian-pitch.pdf)

Built for the AMD Developer Hackathon: ACT III
(lablab.ai), Evolus Business Agents track. Evolus workspace: **Voren**.

**AMD calls in the code**: every request to the AMD Token Factory endpoint goes through `send()` in
[`mg/llm.py`](mg/llm.py) (`/chat/completions`, Gemma 4 31B). PDFs are read by the Evolus extractor
on the same Gemma model, called in [`mg/extract/pdf.py`](mg/extract/pdf.py).

```
 new price list (PDF, Excel or a photo)        old price list
              |                                       |
              v                                       v
   READ     Gemma 4 on AMD Token Factory (PDF via Evolus, photo read twice), Excel by code
              |   guard: every price and pack size checked against the document
              v
   COMPARE   old vs new, link to the shop catalog .............. code
              v
   CALCULATE unit cost in EUR, margins, cost per month ......... code
              v
   REVIEW    every number traced back to its source row ........ code
              v
   MOVES     absorb / reprice / negotiate, each with its numbers  code
              v
   PREPARE   supplier email (sentences: Evolus, numbers: code) or a CSV of new prices
              v
   a person reads it and decides. Nothing is sent, nothing is changed.
```

| Step | What happens | Where it runs |
|---|---|---|
| Read a PDF | Codes, prices, packs, markers and footnotes copied from the page | Evolus extractor on **Gemma 4 31B, AMD Token Factory** |
| Read a footnote | "Does this note announce a surcharge?" | **Gemma 4 31B, AMD Token Factory** |
| Read a photo | Two readings at the same time, only matching rows are kept | **Gemma 4 31B, AMD Token Factory** (Qwen as backup) |
| Read an Excel file | Rows and columns | Local code |
| Compare and calculate | Changes, unit cost in EUR, margins, monthly and yearly cost | Local code (Python, numpy) |
| Review | Every number checked against the rows it cites | Local code |
| Three moves | Absorb, reprice (capped by competitors, sales lost from 24 months of history), negotiate | Local code |
| Supplier email | Sentences written with gaps, numbers pasted in by code | Evolus email tool, then local code |

## The problem

A supplier sends a new price list. Brake pads: 9.60 last quarter, 5.10 now. Good news?
No. The pack went from four pads to two, so every pad costs 6% more.

A small online shop gets dozens of these lists, in PDF and Excel, in different languages and
currencies. Nobody has time to check every line, so the increases nobody notices eat the margin.

## What it does

1. **Reads** the new price lists (PDF, Excel, or a photo of a printed one) and the previous ones,
   in the supplier's own language and currency: the demo has a German/English list in euros, an
   Italian one in euros and an English one in pounds.
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
**9,155 EUR a year** if nobody reacts.

## Guardrails in code, not in the prompt

**The AI reads and writes. The code does the math. The person signs off.** No cost, margin or
percentage is ever computed by a model: they come from `mg/analyze.py` and `mg/moves.py`, and every
number on screen comes with its calculation. On top of that, five guards, all plain code:

1. **Every PDF reading is checked against the PDF** (`mg/extract/pdf.py`). Code extracts the text of
   the PDF on its own: every price the model read must be printed on its row, the pack size must be
   the number under the pack column (if the list has no pack column, 1 or the pack written on the
   row, "pack of 2"; an empty pack cell is refused; "Min. ord." is a minimum order, not a pack), no priced row may be left out, no code may be invented. A failed check means a new reading; after three failures the
   price list is refused. During development the model once read 24.90 where the list said 9.90:
   this check stopped it, and a test replays that case (`tests/test_extract.py`).
2. **A footnote number is kept only if it is written in the footnote** (`mg/extract/pdf.py`,
   `keep_what_is_written`). A surcharge or a date the note does not literally contain is dropped.
3. **A photo is read twice** (`mg/extract/photo.py`). There is no text in a photo to check against,
   so two readings run at the same time and a row counts only if both agree on code, price, pack and
   marker.
4. **A reviewer written in code, not a second model** (`mg/review.py`). Before a result reaches the
   screen it goes back to the rows it cites: each unit cost must come out of a price printed there,
   with that row's pack size and currency, and the change, the two margins and the monthly impact
   must agree with the costs. If anything does not match, the result is held back.
5. **Numbers are pasted, not written** (`mg/negotiate.py`). In the supplier email the model writes
   sentences with gaps and may not write a single digit; the figures are inserted by code from the
   calculated table, then every number in the finished email is checked against it.

When AMD does not answer, the app says which service failed and falls back to the saved reading.
Open any change and its source opens next to the numbers: the PDF page with that row highlighted,
or the Excel row.

## Measured, not claimed

Measured on **15 October 2026, 12:27 to 12:40 UTC**, with `scripts/measure.py`. Raw numbers:
`data/measurements/2026-10-15T1227.json`.

**Against a plain chatbot.** The same model (Gemma 4 31B on Token Factory) without the pipeline gets
the old and the new price list of each demo supplier as plain text and is asked which products cost
more, and by how much. Both answers are scored against `data/demo/ANSWER_KEY.md`: 18 increases,
7 of them hidden (a smaller pack, a surcharge written in a footnote).

| | Increases found | Right size (within 0.5 points) | Hidden found | Invented |
|---|---|---|---|---|
| Margin Guardian | 18/18 | 18 | 7/7 | 0 |
| Gemma alone, run 1 | 17/18 | 17 | 6/7 | 0 |
| Gemma alone, run 2 | 17/18 | 17 | 6/7 | 0 |
| Gemma alone, run 3 | 17/18 | 17 | 6/7 | 0 |

What this says, honestly: on clean text the plain chatbot finds almost everything, the footnote
surcharge included. It missed the pack trap (brake pads, 4 to 2 per pack) in all three runs. And it
only answers the question: no unit cost in EUR, no margin, no source row, no move, and nothing
stops it when it reads a price wrong. It was also given text our code had already pulled out of the
PDF. Margin Guardian is scored on the saved demo readings; the live readings are below.

**Timings** (one afternoon; Token Factory speed changes a lot during the day):

| Call | Where it runs | Time |
|---|---|---|
| Footnote: is there a surcharge? | Gemma, AMD Token Factory | 2.6, 11.1 and 68.4 s (3 calls) |
| Whole price list, plain chatbot | Gemma, AMD Token Factory | 4.6 to 45.6 s (9 calls) |
| PDF price list, 15 or 20 rows | Evolus extractor on Gemma | 78 to 170 s (4 PDFs) |
| Supplier email sentences | Evolus email tool | 3.5 to 5.2 s (3 calls) |

**The PDF guard.** 4 live readings, 70 rows read out of 70 priced rows, every price found on its
row: 0 readings stopped today. The guard did stop wrong readings during development (13 October:
rows left out, and 24.90 read where the list said 9.90); that case is replayed in the tests, not in
this run.

## Honest limits

- **The minimum order is not checked against the document**, and on a photo neither is the pack
  size. In a PDF the guard checks prices, missing rows and the pack size (the number under the pack
  column, or 1 if the list has none, or the pack written on the row). The person sees the highlighted
  source row.
- **The pack column is recognised by its name** (`VE`, `VPE`, `Pack`, `Pack Qty`, `Conf.` and a few
  more, in `mg/extract/pdf.py`). With a name not on that list the guard sees no pack column and
  expects 1: if the model reads the real packs the list is refused, if it reads 1 instead of 10
  there is nothing to compare with and the reading passes.
- **On a photo, two readings wrong in the same way would pass.** Agreement is not proof.
- **A scan with no text layer has nothing to compare with**: the PDF guard needs the text of the PDF.
- The exchange rate is a fixed demo rate (1 GBP = 1.17 EUR), and the "negotiate" move assumes the
  supplier gives up half of the increase. Both are declared in `mg/config.py`.

## Why AMD

Gemma is an open model: Google publishes it, but anyone can run it on their own hardware. In this
demo it runs on AMD's shared endpoint, Token Factory. A shop that does not want its prices and
margins to leave the house can run the same model on its own AMD GPU, without changing the code.
With a closed model, that is not possible.

## On Telegram

[@MarginGuardianbot](https://t.me/MarginGuardianbot): forward one of the demo price lists, send a photo
of one printed on paper, or pick a supplier, and get what changed, the cost in a year and three
buttons: absorb, reprice (the CSV arrives in the chat) or negotiate (the supplier email, not sent).
Run it with `.venv/bin/python bot/telegram_bot.py`.

## Reproduce

With Docker (the app on http://localhost:8501; keys optional, copy `.env.example` to `.env`):

```bash
docker compose up --build
```

Without Docker:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/app.py         # the app, no key needed
.venv/bin/python -m pytest -q              # the tests, no key needed
.venv/bin/python scripts/measure.py        # the measurements above, needs the keys in .env
```

The app works without any key: it uses the saved readings of the demo price lists in
`data/demo/results/extract/`, and the saved supplier emails in `data/demo/results/email/`. With the
keys in `.env` (copy `.env.example`), it can also read a price list again live, and write the email
for a supplier that has no saved text yet. The tests include every trap listed in
`data/demo/ANSWER_KEY.md`.

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
mg/extract/     reading: pdf.py (Evolus extractor + check against the PDF), xlsx.py (plain code),
                photo.py (Gemma reads a photo twice, Qwen as backup)
mg/match.py     old vs new price list, link to the shop catalog
mg/analyze.py   unit cost in EUR, margin, monthly impact
mg/forecast.py  monthly sales and price elasticity from the sales history
mg/moves.py     absorb, reprice, negotiate
mg/review.py    the reviewer
mg/negotiate.py the supplier email
mg/export.py    new prices as CSV
mg/report.py    the whole chain for one supplier, used by the app and the bot
bot/            the Telegram bot
app/            the Streamlit app
scripts/        measure.py (the measurements), checks of the AMD and Evolus keys
data/demo/      invented shop, suppliers, prices and sales
data/measurements/  dated results of scripts/measure.py
tests/          one file per step
```

## Synthetic data

Everything in `data/demo/` is synthetic and labelled so: the shop, the suppliers, the prices and
the sales are invented, and no real company or customer data is used. See `data/demo/README.md`.
The method is real.

## Who pays

The owner of a small online shop: **49 EUR a month, the first price list free**, so the shop sees
what it is losing before it pays. On the demo shop that is about 760 EUR a month, so the
subscription pays for itself about fifteen times. The subscription keeps the reader, the checks
and the models up to date. The price is our plan, not yet tested with a customer.

## What comes next

- Send the email from the shop's own mailbox, still one click to approve.
- Read price lists straight from the inbox, as they arrive.
- Write the new prices straight into the shop's catalog, without a file in between.

## License

MIT, see `LICENSE`.
