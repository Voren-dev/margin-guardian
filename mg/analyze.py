"""Step 3: MatchedChange -> Finding. All the maths is plain Python, no model.

The one rule that matters: costs are always compared PER UNIT and IN EUR.

    unit cost in EUR = listed price / pack size * exchange rate

That is what catches a pack going from 4 to 2: the listed price drops,
the cost of one piece goes up.

Handled here: price_up, price_down, pack_change, and surcharge_note
(a surcharge announced in a footnote, on rows whose listed price did not change).
Not handled yet: moq_change, new_product, discontinued (no cost to compare).
"""
from pathlib import Path

from mg.catalog import Product, load_catalog
from mg.config import CATALOG_PATH, FX_NOTE, FX_TO_EUR, SALES_HISTORY_PATH
from mg.forecast import Sale, load_sales, monthly_units
from mg.schemas import DocumentNote, Finding, MatchedChange, PriceLine

COST_KINDS = ("price_up", "price_down", "pack_change")


def analyze(
    matched: list[MatchedChange],
    notes: list[DocumentNote],
    new_lines: list[PriceLine],
    catalog_path: Path | str = CATALOG_PATH,
    sales_path: Path | str = SALES_HISTORY_PATH,
) -> list[Finding]:
    """Turn the matched changes into findings with their numbers.

    notes and new_lines are needed for a surcharge announced in a footnote:
    it applies to the marked rows of the new list, even if their price did not change.
    """
    products = load_catalog(catalog_path)
    sales = load_sales(sales_path)
    product_by_sku = {product.sku: product for product in products}
    findings = []
    for change in matched:
        if change.kind not in COST_KINDS:
            continue
        if change.sku is None:
            continue  # not linked to a catalog product: nothing to calculate on
        findings.append(_cost_finding(change, product_by_sku[change.sku], sales))

    product_by_code = {product.supplier_code: product for product in products}
    repriced = {finding.sku for finding in findings}  # rows whose listed price changed too
    for note in notes:
        surcharge = note.effect.get("surcharge_pct")
        if not surcharge or not note.applies_to_marker:
            continue  # the note does not announce a surcharge on marked rows
        for line in new_lines:
            if note.applies_to_marker in line.markers and line.supplier_code in product_by_code:
                product = product_by_code[line.supplier_code]
                findings.append(_surcharge_finding(line, note, surcharge, product, sales, product.sku in repriced))
    return findings


def unit_cost_eur(line: PriceLine) -> float:
    """Cost of one piece in EUR: listed price / pack size * exchange rate."""
    if line.currency not in FX_TO_EUR:
        raise ValueError(f"no exchange rate for currency {line.currency}")
    return line.price / line.pack_size * FX_TO_EUR[line.currency]


def margin_pct(retail_price: float, unit_cost: float) -> float:
    """Share of the retail price that is left after paying the supplier."""
    return (retail_price - unit_cost) / retail_price * 100


def expected_monthly_units(product: Product, sales: list[Sale]) -> float:
    """How many pieces the shop is expected to sell in a month.

    The average of the last 12 months of sales (a whole season). A product with
    no sales history falls back to the catalog average.
    """
    from_history = monthly_units(product.sku, sales)
    return from_history if from_history is not None else product.avg_monthly_units


UNITS_NOTE = "units per month: average of the last 12 months of sales"


def _cost_finding(change: MatchedChange, product: Product, sales: list[Sale]) -> Finding:
    old_cost = unit_cost_eur(change.old)
    new_cost = unit_cost_eur(change.new)
    pct_change = (new_cost - old_cost) / old_cost * 100
    old_margin = margin_pct(product.retail_price_eur, old_cost)
    new_margin = margin_pct(product.retail_price_eur, new_cost)
    units = expected_monthly_units(product, sales)
    monthly_impact = (new_cost - old_cost) * units

    direction = "up" if new_cost > old_cost else "down"
    rationale = (
        f"{product.name}: cost per unit {direction} {abs(pct_change):.2f}%, "
        f"margin from {old_margin:.1f}% to {new_margin:.1f}%."
    )
    if change.kind == "pack_change":
        rationale += f" Pack size changed from {change.old.pack_size} to {change.new.pack_size}."

    return Finding(
        id=f"{product.sku}-{change.kind}",
        sku=product.sku,
        kind=change.kind,
        old_unit_cost_eur=round(old_cost, 4),
        new_unit_cost_eur=round(new_cost, 4),
        pct_change=round(pct_change, 2),
        old_margin_pct=round(old_margin, 2),
        new_margin_pct=round(new_margin, 2),
        monthly_impact_eur=round(monthly_impact, 2),
        units_per_month=round(units, 4),
        rationale=rationale,
        sources=[change.old.source, change.new.source],
        calc_trace=_trace(change, product, old_cost, new_cost, pct_change, old_margin, new_margin, units, monthly_impact),
    )


def _surcharge_finding(
    line: PriceLine, note: DocumentNote, surcharge_pct: float, product: Product, sales: list[Sale], price_changed: bool = False
) -> Finding:
    """A surcharge written in a footnote: the listed price stays the same, the real cost goes up."""
    listed_cost = unit_cost_eur(line)
    real_cost = listed_cost * (1 + surcharge_pct / 100)
    old_margin = margin_pct(product.retail_price_eur, listed_cost)
    new_margin = margin_pct(product.retail_price_eur, real_cost)
    units = expected_monthly_units(product, sales)
    monthly_impact = (real_cost - listed_cost) * units
    since = f" from {note.valid_from}" if note.valid_from else ""
    retail = product.retail_price_eur

    return Finding(
        id=f"{product.sku}-surcharge_note",
        sku=product.sku,
        kind="surcharge_note",
        old_unit_cost_eur=round(listed_cost, 4),
        new_unit_cost_eur=round(real_cost, 4),
        pct_change=round(surcharge_pct, 2),
        old_margin_pct=round(old_margin, 2),
        new_margin_pct=round(new_margin, 2),
        monthly_impact_eur=round(monthly_impact, 2),
        units_per_month=round(units, 4),
        rationale=(
            f"{product.name}: "
            + ("on top of the new listed price, " if price_changed else "the listed price did not change, but ")
            + f"a footnote adds {surcharge_pct:g}%{since} "
            f"to the rows marked {note.applies_to_marker}. Margin from {old_margin:.1f}% to {new_margin:.1f}%."
        ),
        sources=[line.source, note.source],
        calc_trace="\n".join(
            [
                f"listed unit cost = price / pack size * rate = {line.price:.2f} {line.currency} / {line.pack_size} * {FX_TO_EUR[line.currency]} = {listed_cost:.4f} EUR",
                f"real unit cost = listed * (1 + surcharge) = {listed_cost:.4f} * (1 + {surcharge_pct:g}/100) = {real_cost:.4f} EUR",
                f"old margin = (retail - listed unit cost) / retail = ({retail:.2f} - {listed_cost:.4f}) / {retail:.2f} = {old_margin:.2f}%",
                f"new margin = (retail - real unit cost) / retail = ({retail:.2f} - {real_cost:.4f}) / {retail:.2f} = {new_margin:.2f}%",
                f"monthly impact = (real - listed) * units per month = ({real_cost:.4f} - {listed_cost:.4f}) * {units:.1f} = {monthly_impact:+.2f} EUR",
                f"surcharge: {surcharge_pct:g}%{since}, written in a footnote for rows marked {note.applies_to_marker}; {UNITS_NOTE}",
            ]
        ),
    )


def _trace(change, product, old_cost, new_cost, pct_change, old_margin, new_margin, units, monthly_impact) -> str:
    """The formulas with the actual values in them, one per line."""
    old, new = change.old, change.new
    rate_old, rate_new = FX_TO_EUR[old.currency], FX_TO_EUR[new.currency]
    retail = product.retail_price_eur
    return "\n".join(
        [
            f"old unit cost = price / pack size * rate = {old.price:.2f} {old.currency} / {old.pack_size} * {rate_old} = {old_cost:.4f} EUR",
            f"new unit cost = price / pack size * rate = {new.price:.2f} {new.currency} / {new.pack_size} * {rate_new} = {new_cost:.4f} EUR",
            f"change = (new - old) / old = ({new_cost:.4f} - {old_cost:.4f}) / {old_cost:.4f} = {pct_change:+.2f}%",
            f"old margin = (retail - old unit cost) / retail = ({retail:.2f} - {old_cost:.4f}) / {retail:.2f} = {old_margin:.2f}%",
            f"new margin = (retail - new unit cost) / retail = ({retail:.2f} - {new_cost:.4f}) / {retail:.2f} = {new_margin:.2f}%",
            f"monthly impact = (new - old) * units per month = ({new_cost:.4f} - {old_cost:.4f}) * {units:.1f} = {monthly_impact:+.2f} EUR",
            f"exchange rate: {FX_NOTE}; {UNITS_NOTE}",
        ]
    )
