"""The whole chain for one demo supplier, without the app. Used by the Telegram bot.

Same steps as the app: read old and new price list, compare, calculate, review, moves.
The PDFs are not read again: the saved readings in data/demo/results/extract are used.
"""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from mg.analyze import analyze
from mg.catalog import Product, load_catalog
from mg.config import CATALOG_PATH
from mg.extract import extract_price_list
from mg.match import diff_price_lists, match_to_catalog
from mg.moves import build_moves
from mg.review import audit
from mg.schemas import Finding, Move

SUPPLIERS_DIR = Path(__file__).resolve().parent.parent / "data" / "demo" / "suppliers"

# key -> (supplier name in the catalog, old price list, new price list)
DEMO_SUPPLIERS = {
    "veloparts": ("VeloParts GmbH", "veloparts_Q3-2026.pdf", "veloparts_Q4-2026.pdf"),
    "ciclo": ("Ciclo Componenti Srl", "ciclo-componenti_listino_2026-06.pdf", "ciclo-componenti_listino_2026-10.pdf"),
    "trailgear": ("TrailGear Ltd", "trailgear_summer-2026.xlsx", "trailgear_autumn-2026.xlsx"),
}

HIDDEN_KINDS = ("pack_change", "surcharge_note")


@dataclass
class SupplierReport:
    key: str
    supplier: str
    new_file: str
    findings: list[Finding]  # passed the reviewer, biggest monthly cost first
    held_back: list[Finding]  # refused by the reviewer
    moves: dict[str, dict[str, Move]] = field(default_factory=dict)  # finding id -> kind -> move
    products: dict[str, Product] = field(default_factory=dict)

    def total(self, kind: str) -> float:
        """Yearly impact of one move over all the increases."""
        return sum(by_kind[kind].yearly_impact_eur for by_kind in self.moves.values() if kind in by_kind)

    def hidden(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.kind in HIDDEN_KINDS]

    def increases(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.id in self.moves]


def run_supplier(key: str) -> SupplierReport:
    supplier, old_name, new_name = DEMO_SUPPLIERS[key]
    old_lines, _ = extract_price_list(SUPPLIERS_DIR / "old" / old_name)
    new_lines, notes = extract_price_list(SUPPLIERS_DIR / "new" / new_name)
    matched = match_to_catalog(diff_price_lists(old_lines, new_lines), CATALOG_PATH)
    findings = analyze(matched, notes, new_lines)

    passed = [finding for finding in findings if audit(finding).passed]
    held_back = [finding for finding in findings if not audit(finding).passed]
    passed.sort(key=lambda finding: finding.monthly_impact_eur, reverse=True)

    moves = {}
    for move in build_moves(passed):
        moves.setdefault(move.finding_id, {})[move.kind] = move

    products = {product.sku: product for product in load_catalog(CATALOG_PATH)}
    return SupplierReport(key, supplier, new_name, passed, held_back, moves, products)


def identify(content: bytes) -> str | None:
    """The demo supplier whose new price list is exactly this file, or None."""
    digest = hashlib.sha256(content).hexdigest()
    for key, (_, _, new_name) in DEMO_SUPPLIERS.items():
        if hashlib.sha256((SUPPLIERS_DIR / "new" / new_name).read_bytes()).hexdigest() == digest:
            return key
    return None
