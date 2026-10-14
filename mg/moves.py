"""Step 4: a Finding -> the three moves the shop can make, each with its numbers.

    absorb     keep your prices and pay the higher cost
    reprice    raise your price to get the old margin back, and sell a bit less
    negotiate  ask the supplier to give up part of the increase

Every move is measured against the same starting point: the yearly profit on that
product BEFORE the new price list. So the three numbers can be compared directly.

Plain Python, no model. What is estimated (how sales react to price) comes with its
source; what is assumed (how a negotiation ends) is written as an assumption.
"""
import csv
from pathlib import Path

from mg.analyze import expected_monthly_units, margin_pct
from mg.catalog import Product, load_catalog
from mg.config import CATALOG_PATH, COMPETITOR_PRICES_PATH, NEGOTIATION_SHARE, SALES_HISTORY_PATH
from mg.forecast import Elasticity, estimate_elasticity, load_sales
from mg.schemas import Finding, Move

MONTHS = 12


def build_moves(
    findings: list[Finding],
    catalog_path: Path | str = CATALOG_PATH,
    sales_path: Path | str = SALES_HISTORY_PATH,
    competitor_path: Path | str = COMPETITOR_PRICES_PATH,
) -> list[Move]:
    """The moves for every finding that costs money. A price that went down needs no move."""
    products = load_catalog(catalog_path)
    product_by_sku = {product.sku: product for product in products}
    sales = load_sales(sales_path)
    cheapest = cheapest_competitor_prices(competitor_path)
    elasticity_by_category = {}

    moves = []
    for finding in findings:
        if finding.monthly_impact_eur <= 0:
            continue
        product = product_by_sku[finding.sku]
        if product.category not in elasticity_by_category:
            elasticity_by_category[product.category] = estimate_elasticity(product.category, sales, products)
        units = expected_monthly_units(product, sales)

        moves.append(absorb(finding, units))
        reprice_move = reprice(finding, product, units, elasticity_by_category[product.category], cheapest.get(product.sku))
        if reprice_move:
            moves.append(reprice_move)
        moves.append(negotiate(finding, units))
    return moves


def cheapest_competitor_prices(path: Path | str) -> dict[str, float]:
    """For each SKU, the lowest price seen at a competitor."""
    cheapest = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            price = float(row["price_eur"])
            if row["sku"] not in cheapest or price < cheapest[row["sku"]]:
                cheapest[row["sku"]] = price
    return cheapest


def absorb(finding: Finding, units: float) -> Move:
    """Keep the retail price: the whole increase comes out of the margin."""
    extra_cost = finding.new_unit_cost_eur - finding.old_unit_cost_eur
    yearly = -extra_cost * units * MONTHS
    return Move(
        finding_id=finding.id,
        kind="absorb",
        yearly_impact_eur=round(yearly, 2),
        units_delta=0,
        assumptions="You keep your price and sell as many pieces as in the last 12 months.",
        calc_trace=(
            f"yearly impact = -(new cost - old cost) * units per month * 12 = "
            f"-({finding.new_unit_cost_eur:.4f} - {finding.old_unit_cost_eur:.4f}) * {units:.1f} * 12 = {yearly:+.2f} EUR"
        ),
    )


def negotiate(finding: Finding, units: float) -> Move:
    """The supplier gives up part of the increase; the rest is absorbed."""
    extra_cost = finding.new_unit_cost_eur - finding.old_unit_cost_eur
    kept_share = 1 - NEGOTIATION_SHARE
    yearly = -extra_cost * kept_share * units * MONTHS
    return Move(
        finding_id=finding.id,
        kind="negotiate",
        yearly_impact_eur=round(yearly, 2),
        units_delta=0,
        assumptions=(
            f"ASSUMPTION, not an estimate: the supplier gives up {NEGOTIATION_SHARE:.0%} of the increase. "
            "You keep your price and your sales."
        ),
        calc_trace=(
            f"yearly impact = -(new cost - old cost) * share you still pay * units per month * 12 = "
            f"-({finding.new_unit_cost_eur:.4f} - {finding.old_unit_cost_eur:.4f}) * {kept_share:g} * {units:.1f} * 12 = {yearly:+.2f} EUR"
        ),
    )


def price_that_restores_the_margin(new_unit_cost: float, old_margin_pct: float) -> float:
    """The retail price at which the margin is again what it was before the increase."""
    return new_unit_cost / (1 - old_margin_pct / 100)


def reprice(
    finding: Finding, product: Product, units: float, elasticity: Elasticity | None, cheapest_competitor: float | None
) -> Move | None:
    """Raise the retail price to restore the margin, but never above the cheapest competitor.

    A higher price sells fewer pieces: how many fewer comes from the price elasticity
    of the product's category. Without an elasticity there is no honest number, so no move.
    """
    if elasticity is None:
        return None

    retail = product.retail_price_eur
    old_cost, new_cost = finding.old_unit_cost_eur, finding.new_unit_cost_eur
    old_margin = margin_pct(retail, old_cost)
    wanted = price_that_restores_the_margin(new_cost, old_margin)

    new_price = wanted
    ceiling_note = "no competitor price is known for this product, so there is no ceiling"
    if cheapest_competitor is not None:
        new_price = max(retail, min(wanted, cheapest_competitor))
        if cheapest_competitor <= retail:
            ceiling_note = f"the cheapest competitor sells at {cheapest_competitor:.2f}, not above your price: no room to raise it"
        elif cheapest_competitor < wanted:
            ceiling_note = f"stopped at the cheapest competitor, {cheapest_competitor:.2f}: the margin is only partly restored"
        else:
            ceiling_note = f"still below the cheapest competitor, {cheapest_competitor:.2f}"
    new_price = round(new_price, 2)

    # units change by (elasticity)% for every 1% of price: new units = units * (new price / old price) ^ elasticity
    new_units = units * (new_price / retail) ** elasticity.value
    profit_before = (retail - old_cost) * units * MONTHS
    profit_after = (new_price - new_cost) * new_units * MONTHS
    yearly = profit_after - profit_before
    units_delta = (new_units - units) * MONTHS

    return Move(
        finding_id=finding.id,
        kind="reprice",
        yearly_impact_eur=round(yearly, 2),
        units_delta=round(units_delta, 1),
        new_retail_price_eur=new_price,
        assumptions=(
            f"New retail price {new_price:.2f} EUR (now {retail:.2f}); {ceiling_note}. "
            f"Price elasticity of {product.category}: {elasticity.value} "
            f"(95% interval {elasticity.low} to {elasticity.high}"
            f"{', a weak estimate: the interval includes zero' if elasticity.low <= 0 <= elasticity.high else ''}), "
            f"estimated from {elasticity.observations} product-months of sales."
            + (
                " You end up earning more than before the increase: restoring the margin in percent "
                "raises the margin per piece, and these customers barely react to price."
                if yearly > 0 else ""
            )
        ),
        calc_trace="\n".join(
            [
                f"price that restores the margin = new cost / (1 - old margin) = {new_cost:.4f} / (1 - {old_margin:.2f}/100) = {wanted:.2f} EUR",
                f"new retail price = {new_price:.2f} EUR ({ceiling_note})",
                f"new units per month = units * (new price / old price) ^ elasticity = {units:.1f} * ({new_price:.2f} / {retail:.2f}) ^ {elasticity.value} = {new_units:.1f}",
                f"yearly profit before = (old price - old cost) * units * 12 = ({retail:.2f} - {old_cost:.4f}) * {units:.1f} * 12 = {profit_before:.2f} EUR",
                f"yearly profit after = (new price - new cost) * new units * 12 = ({new_price:.2f} - {new_cost:.4f}) * {new_units:.1f} * 12 = {profit_after:.2f} EUR",
                f"yearly impact = after - before = {yearly:+.2f} EUR; units per year {units_delta:+.1f}",
            ]
        ),
    )
