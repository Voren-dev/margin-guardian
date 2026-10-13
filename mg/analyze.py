"""Step 3: MatchedChange -> Finding. All the maths is plain Python, no model.

The one rule that matters: costs are always compared PER UNIT and IN EUR.

    unit cost in EUR = listed price / pack size * exchange rate

That is what catches a pack going from 4 to 2: the listed price drops,
the cost of one piece goes up.

Handled here: price_up, price_down, pack_change.
Not handled yet: moq_change, new_product, discontinued (no cost to compare)
and surcharge_note (comes from the notes of the document).
"""
from pathlib import Path

from mg.catalog import Product, load_catalog
from mg.config import CATALOG_PATH, FX_NOTE, FX_TO_EUR
from mg.schemas import DocumentNote, Finding, MatchedChange, PriceLine

COST_KINDS = ("price_up", "price_down", "pack_change")


def analyze(
    matched: list[MatchedChange],
    notes: list[DocumentNote],
    new_lines: list[PriceLine],
    catalog_path: Path | str = CATALOG_PATH,
) -> list[Finding]:
    """Turn the matched changes into findings with their numbers.

    notes and new_lines are not used yet: they are needed for the surcharge
    announced in a footnote, which applies to rows whose price did not change.
    """
    product_by_sku = {product.sku: product for product in load_catalog(catalog_path)}
    findings = []
    for change in matched:
        if change.kind not in COST_KINDS:
            continue
        if change.sku is None:
            continue  # not linked to a catalog product: nothing to calculate on
        findings.append(_cost_finding(change, product_by_sku[change.sku]))
    return findings


def unit_cost_eur(line: PriceLine) -> float:
    """Cost of one piece in EUR: listed price / pack size * exchange rate."""
    if line.currency not in FX_TO_EUR:
        raise ValueError(f"no exchange rate for currency {line.currency}")
    return line.price / line.pack_size * FX_TO_EUR[line.currency]


def margin_pct(retail_price: float, unit_cost: float) -> float:
    """Share of the retail price that is left after paying the supplier."""
    return (retail_price - unit_cost) / retail_price * 100


def expected_monthly_units(product: Product) -> float:
    """How many pieces the shop sells in a month.

    For now this is the catalog average. The forecast from the sales history
    (seasonality, price elasticity) will replace this one function.
    """
    return product.avg_monthly_units


def _cost_finding(change: MatchedChange, product: Product) -> Finding:
    old_cost = unit_cost_eur(change.old)
    new_cost = unit_cost_eur(change.new)
    pct_change = (new_cost - old_cost) / old_cost * 100
    old_margin = margin_pct(product.retail_price_eur, old_cost)
    new_margin = margin_pct(product.retail_price_eur, new_cost)
    units = expected_monthly_units(product)
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
        rationale=rationale,
        sources=[change.old.source, change.new.source],
        calc_trace=_trace(change, product, old_cost, new_cost, pct_change, old_margin, new_margin, units, monthly_impact),
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
            f"monthly impact = (new - old) * units per month = ({new_cost:.4f} - {old_cost:.4f}) * {units:g} = {monthly_impact:+.2f} EUR",
            f"exchange rate: {FX_NOTE}; units per month: catalog average",
        ]
    )
