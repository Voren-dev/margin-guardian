"""The whole chain for one demo supplier: compare, link to the catalog, calculate, review, moves.

Used by the app and by the Telegram bot. By default the saved readings of the demo PDFs
(data/demo/results/extract) are used; a reading made elsewhere (a PDF read live, a photo)
can be passed in instead.
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
from mg.schemas import DocumentNote, Finding, MatchedChange, Move, PriceLine

SUPPLIERS_DIR = Path(__file__).resolve().parent.parent / "data" / "demo" / "suppliers"

# key -> (supplier name in the catalog, old price list, new price list)
DEMO_SUPPLIERS = {
    "veloparts": ("VeloParts GmbH", "veloparts_Q3-2026.pdf", "veloparts_Q4-2026.pdf"),
    "ciclo": ("Ciclo Componenti Srl", "ciclo-componenti_listino_2026-06.pdf", "ciclo-componenti_listino_2026-10.pdf"),
    "trailgear": ("TrailGear Ltd", "trailgear_summer-2026.xlsx", "trailgear_autumn-2026.xlsx"),
}

HIDDEN_KINDS = ("pack_change", "surcharge_note")
OTHER_KINDS = ("new_product", "discontinued", "moq_change")


@dataclass
class SupplierReport:
    key: str
    supplier: str
    new_file: str
    findings: list[Finding]  # passed the reviewer, biggest monthly cost first
    held_back: list[Finding]  # refused by the reviewer
    moves: dict[str, dict[str, Move]] = field(default_factory=dict)  # finding id -> kind -> move
    products: dict[str, Product] = field(default_factory=dict)
    changes: list[MatchedChange] = field(default_factory=list)  # everything the comparison found

    def other_changes(self) -> list[MatchedChange]:
        """Changes that cost nothing today, so they get no numbers: a new product, a dropped one, a new minimum order."""
        return [change for change in self.changes if change.kind in OTHER_KINDS]

    def total(self, kind: str) -> float:
        """Yearly impact of one move over all the increases."""
        return sum(by_kind[kind].yearly_impact_eur for by_kind in self.moves.values() if kind in by_kind)

    def hidden(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.kind in HIDDEN_KINDS]

    def increases(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.id in self.moves]


def run_supplier(key: str, new_lines: list[PriceLine] | None = None, notes: list[DocumentNote] | None = None,
                 new_file: str | None = None, complete: bool = True) -> SupplierReport:
    """The chain on one demo supplier. Pass new_lines and notes to use a reading made elsewhere.

    complete=False for a photo: a row the two readings did not agree on is missing from it,
    so a missing row there does not mean a discontinued product.
    """
    supplier, old_name, new_name = DEMO_SUPPLIERS[key]
    old_lines, _ = extract_price_list(SUPPLIERS_DIR / "old" / old_name)
    if new_lines is None:
        new_lines, notes = extract_price_list(SUPPLIERS_DIR / "new" / new_name)
    else:
        new_name = new_file or new_name
    matched = match_to_catalog(diff_price_lists(old_lines, new_lines), CATALOG_PATH)
    if not complete:
        matched = [change for change in matched if change.kind != "discontinued"]
    findings = analyze(matched, notes, new_lines)

    passed = [finding for finding in findings if audit(finding).passed]
    held_back = [finding for finding in findings if not audit(finding).passed]
    passed.sort(key=lambda finding: finding.monthly_impact_eur, reverse=True)

    moves = {}
    for move in build_moves(passed):
        moves.setdefault(move.finding_id, {})[move.kind] = move

    products = {product.sku: product for product in load_catalog(CATALOG_PATH)}
    return SupplierReport(key, supplier, new_name, passed, held_back, moves, products, matched)


def identify(content: bytes) -> str | None:
    """The demo supplier whose new price list is exactly this file, or None."""
    digest = hashlib.sha256(content).hexdigest()
    for key, (_, _, new_name) in DEMO_SUPPLIERS.items():
        if hashlib.sha256((SUPPLIERS_DIR / "new" / new_name).read_bytes()).hexdigest() == digest:
            return key
    return None


def supplier_of(lines: list[PriceLine]) -> str | None:
    """The demo supplier whose last price list shares the most article codes with these lines, or None."""
    codes = {line.supplier_code for line in lines}
    best, shared = None, 0
    for key, (_, old_name, _) in DEMO_SUPPLIERS.items():
        old_lines, _ = extract_price_list(SUPPLIERS_DIR / "old" / old_name)
        count = len(codes & {line.supplier_code for line in old_lines})
        if count > shared:
            best, shared = key, count
    return best if shared >= 3 else None
