"""The data contracts: the exact shape of what one step hands to the next.

Flow: price list -> PriceLine + DocumentNote -> Change -> MatchedChange -> Finding
      -> AuditResult (reviewer) -> Move (the three options) -> Decision (the person).

Rule: every number shown to the person carries a SourceRef pointing to the
document row it was read from.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

ChangeKind = Literal[
    "price_up",
    "price_down",
    "new_product",
    "discontinued",
    "moq_change",
    "pack_change",
    "surcharge_note",
]
MatchMethod = Literal["exact_code", "llm"]
MoveKind = Literal["absorb", "reprice", "negotiate"]
DecisionStatus = Literal["approved", "edited", "rejected"]


class Contract(BaseModel):
    """Base for all contracts: a misspelled or unknown field is an error, not silently dropped."""

    model_config = ConfigDict(extra="forbid")


class SourceRef(Contract):
    """Where a value comes from: the document and the row inside it."""

    document: str  # file name
    page: int | None = None  # for PDFs
    sheet: str | None = None  # for spreadsheets
    row: int | str  # row index, or a cell like "C14"
    raw_text: str  # the row exactly as written in the document
    bbox: tuple[float, float, float, float] | None = None  # to highlight the row in the PDF
    currency: str | None = None  # for a price row: the currency the row is priced in
    pack_size: int | None = None  # for a price row: the pack size read on that row


class PriceLine(Contract):
    """One row of a supplier price list, normalized."""

    supplier: str
    supplier_code: str
    description: str
    price: float  # as listed: for the whole pack, in the supplier's currency
    currency: str  # "EUR", "GBP"
    pack_size: int = 1
    min_order_qty: int = 1
    markers: list[str] = []  # e.g. ["*"] when the row points to a footnote
    source: SourceRef


class DocumentNote(Contract):
    """A note outside the table, e.g. a footnote announcing a surcharge."""

    text: str
    applies_to_marker: str | None = None  # e.g. "*"
    effect: dict[str, float] = {}  # e.g. {"surcharge_pct": 4}
    valid_from: date | None = None
    source: SourceRef


class Change(Contract):
    """The difference between the old and the new price list for one supplier code."""

    supplier_code: str
    kind: ChangeKind
    old: PriceLine | None = None  # None for a new product
    new: PriceLine | None = None  # None for a discontinued product


class MatchedChange(Change):
    """A Change linked to a product of the shop's catalog."""

    sku: str | None = None  # None when no catalog product matches
    match_method: MatchMethod
    confidence: float  # 0 to 1; an "llm" match below the threshold goes to "to check"


class Finding(Contract):
    """What the person sees. All costs are per unit and in EUR."""

    id: str
    sku: str
    kind: ChangeKind
    old_unit_cost_eur: float | None = None
    new_unit_cost_eur: float | None = None
    pct_change: float | None = None
    old_margin_pct: float | None = None
    new_margin_pct: float | None = None
    monthly_impact_eur: float
    units_per_month: float | None = None  # the sales figure the impact was calculated with
    proposed_retail_price_eur: float | None = None
    rationale: str
    sources: list[SourceRef]  # the reviewer rejects a Finding with no sources
    calc_trace: str  # the formula with the actual values in it


class Move(Contract):
    """One of the three options in front of a Finding, with its numbers."""

    finding_id: str
    kind: MoveKind
    yearly_impact_eur: float
    units_delta: float  # units sold more (+) or less (-) per year
    assumptions: str  # the assumptions used, in plain words
    calc_trace: str
    new_retail_price_eur: float | None = None  # only for reprice: the price to put in the shop


class AuditResult(Contract):
    """The reviewer's verdict on one Finding."""

    finding_id: str
    passed: bool
    reason: str


class Decision(Contract):
    """What the person decided on one Finding."""

    finding_id: str
    status: DecisionStatus
    final_price_eur: float | None = None
