"""Shared paths and helpers for the tests.

The expected values in the tests come from data/demo/ANSWER_KEY.md.
That file is for testing only: the product code never reads it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO = ROOT / "data" / "demo"
OLD = DEMO / "suppliers" / "old"
NEW = DEMO / "suppliers" / "new"
CATALOG = DEMO / "catalog.csv"

# old and new price list of each supplier
PRICE_LISTS = {
    "veloparts": (OLD / "veloparts_Q3-2026.pdf", NEW / "veloparts_Q4-2026.pdf"),
    "ciclo": (OLD / "ciclo-componenti_listino_2026-06.pdf", NEW / "ciclo-componenti_listino_2026-10.pdf"),
    "trailgear": (OLD / "trailgear_summer-2026.xlsx", NEW / "trailgear_autumn-2026.xlsx"),
}

ALUMINIUM_CODES = {"CC-A118", "CC-A121", "CC-A130", "CC-A140", "CC-M520", "CC-B610"}


def changes_for(supplier):
    """Old vs new price list of one supplier -> {supplier_code: [kinds]}."""
    from mg.extract import extract_price_list
    from mg.match import diff_price_lists

    old_path, new_path = PRICE_LISTS[supplier]
    old_lines, _ = extract_price_list(old_path)
    new_lines, _ = extract_price_list(new_path)
    kinds = {}
    for change in diff_price_lists(old_lines, new_lines):
        kinds.setdefault(change.supplier_code, []).append(change.kind)
    return kinds


def all_findings():
    """The whole pipeline on the three suppliers -> list of Finding."""
    from mg.analyze import analyze
    from mg.extract import extract_price_list
    from mg.match import diff_price_lists, match_to_catalog

    findings = []
    for old_path, new_path in PRICE_LISTS.values():
        old_lines, _ = extract_price_list(old_path)
        new_lines, notes = extract_price_list(new_path)
        matched = match_to_catalog(diff_price_lists(old_lines, new_lines), CATALOG)
        findings += analyze(matched, notes, new_lines)
    return findings
