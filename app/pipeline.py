"""Runs the whole chain on the demo price lists and hands the result to the pages.

The PDF price lists are not read again here: the saved extractor answers in
data/demo/results/extract are used, as long as the PDFs are unchanged.
Everything after the reading (comparison, maths, moves, review) runs live.
"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mg.analyze import analyze, expected_monthly_units  # noqa: E402
from mg.catalog import load_catalog  # noqa: E402
from mg.config import CATALOG_PATH  # noqa: E402
from mg.extract import extract_price_list  # noqa: E402
from mg.match import diff_price_lists, match_to_catalog  # noqa: E402
from mg.forecast import load_sales  # noqa: E402
from mg.moves import build_moves  # noqa: E402
from mg.negotiate import draft_email  # noqa: E402
from mg.review import audit  # noqa: E402

SUPPLIERS_DIR = ROOT / "data" / "demo" / "suppliers"

# old and new price list of each supplier
PRICE_LISTS = [
    ("veloparts_Q3-2026.pdf", "veloparts_Q4-2026.pdf"),
    ("ciclo-componenti_listino_2026-06.pdf", "ciclo-componenti_listino_2026-10.pdf"),
    ("trailgear_summer-2026.xlsx", "trailgear_autumn-2026.xlsx"),
]

HIDDEN_KINDS = ("pack_change", "surcharge_note")


@st.cache_data(show_spinner="Reading the price lists...")
def load_demo():
    """Findings, their moves and the reviewer's verdicts, for the three demo suppliers."""
    findings = []
    for old_name, new_name in PRICE_LISTS:
        old_lines, _ = extract_price_list(SUPPLIERS_DIR / "old" / old_name)
        new_lines, notes = extract_price_list(SUPPLIERS_DIR / "new" / new_name)
        matched = match_to_catalog(diff_price_lists(old_lines, new_lines), CATALOG_PATH)
        findings += analyze(matched, notes, new_lines)

    verdicts = {finding.id: audit(finding) for finding in findings}
    passed = [finding for finding in findings if verdicts[finding.id].passed]
    held_back = [finding for finding in findings if not verdicts[finding.id].passed]
    passed.sort(key=lambda finding: finding.monthly_impact_eur, reverse=True)

    moves = {}
    for move in build_moves(passed):
        moves.setdefault(move.finding_id, {})[move.kind] = move

    products = {product.sku: product for product in load_catalog(CATALOG_PATH)}
    return {"findings": passed, "held_back": held_back, "verdicts": verdicts, "moves": moves, "products": products}


def document_path(name: str) -> Path:
    """Where a cited document is on disk."""
    for folder in ("new", "old"):
        if (SUPPLIERS_DIR / folder / name).exists():
            return SUPPLIERS_DIR / folder / name
    raise FileNotFoundError(name)


def euro(amount: float, sign: bool = False) -> str:
    """9154.6 -> '€ 9,155'; with sign=True, -9154.6 -> '− € 9,155'."""
    text = f"€ {abs(amount):,.0f}"
    if not sign:
        return text
    return ("− " if amount < 0 else "+ ") + text


def label(finding) -> str:
    """The short tag shown next to a change."""
    if finding.kind == "pack_change":
        return "HIDDEN · pack size changed"
    if finding.kind == "surcharge_note":
        return f"HIDDEN · footnote +{finding.pct_change:g}%"
    return "price up" if finding.kind == "price_up" else "price down"


@st.cache_data(show_spinner="Writing the email...")
def supplier_email(supplier: str):
    """The email to one supplier about all its increases."""
    demo = load_demo()
    products = demo["products"]
    increases = [f for f in demo["findings"] if f.id in demo["moves"] and products[f.sku].supplier == supplier]
    sales = load_sales()
    units = {finding.sku: expected_monthly_units(products[finding.sku], sales) for finding in increases}
    return draft_email(supplier, increases, products, units)
