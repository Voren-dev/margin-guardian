"""Step 5: the reviewer. Finding -> AuditResult. Plain code, not a second model.

A Finding reaches the screen only if its numbers can be traced back to the rows of
the documents it cites. The reviewer does not trust the numbers it is given: it
starts again from the source rows and checks that the costs come out of them.

Five checks:
  1. the Finding cites its sources (no source, no number on screen);
  2. each unit cost comes out of a price written in its source row, using only
     that row's pack size and currency (price / pack size * exchange rate), or,
     for a footnote surcharge, out of the listed cost plus a percentage written
     in the footnote;
  3. the percentage change agrees with the two costs;
  4. the two margins agree with the costs and the shop's retail price;
  5. the monthly impact agrees with the cost change and the sales it was calculated with.

What it cannot check: a price, pack size or currency read wrong in the same way as
the document says. For that the person looks at the highlighted source row.
"""
import re
from functools import lru_cache

from mg.catalog import load_catalog
from mg.config import CATALOG_PATH, FX_TO_EUR
from mg.schemas import AuditResult, Finding, SourceRef

CENT = 0.005  # two costs are the same if they differ by less than half a cent
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def audit(finding: Finding) -> AuditResult:
    problem = find_problem(finding)
    return AuditResult(finding_id=finding.id, passed=problem is None, reason=problem or "every number traces back to its source row")


def find_problem(finding: Finding) -> str | None:
    """The first thing that does not add up, in plain words. None if all is fine."""
    if not finding.sources:
        return "no source: the finding does not say which document rows it comes from"
    if finding.old_unit_cost_eur is None or finding.new_unit_cost_eur is None:
        return "the finding has no costs to check"

    old_row = finding.sources[0]
    if not cost_comes_from_row(finding.old_unit_cost_eur, old_row):
        return f"old unit cost {finding.old_unit_cost_eur} does not come out of its source row: {old_row.raw_text}"

    if finding.kind == "surcharge_note":
        if len(finding.sources) < 2:
            return "a footnote surcharge must cite the footnote"
        note = finding.sources[1].raw_text
        if not percent_is_written(finding.pct_change, note):
            return f"the surcharge {finding.pct_change}% is not written in the footnote: {note}"
        expected = finding.old_unit_cost_eur * (1 + finding.pct_change / 100)
        if abs(expected - finding.new_unit_cost_eur) > CENT:
            return f"new unit cost {finding.new_unit_cost_eur} is not the listed cost plus {finding.pct_change}%"
    else:
        if len(finding.sources) < 2:
            return "a price change must cite the old row and the new row"
        new_row = finding.sources[1]
        if not cost_comes_from_row(finding.new_unit_cost_eur, new_row):
            return f"new unit cost {finding.new_unit_cost_eur} does not come out of its source row: {new_row.raw_text}"

    expected_pct = (finding.new_unit_cost_eur - finding.old_unit_cost_eur) / finding.old_unit_cost_eur * 100
    if abs(expected_pct - finding.pct_change) > 0.05:
        return f"the change {finding.pct_change}% does not agree with the two costs ({expected_pct:.2f}%)"

    retail = retail_prices().get(finding.sku)
    if retail is None:
        return f"{finding.sku} is not in the catalog: no retail price to check the margins against"
    for label, cost, margin in (("old", finding.old_unit_cost_eur, finding.old_margin_pct), ("new", finding.new_unit_cost_eur, finding.new_margin_pct)):
        expected_margin = (retail - cost) / retail * 100
        if margin is None or abs(expected_margin - margin) > 0.01:
            return f"the {label} margin {margin}% does not agree with cost {cost} and retail price {retail} ({expected_margin:.2f}%)"

    units = finding.units_per_month
    if units is None:
        return "the finding does not say which sales figure its monthly impact uses"
    expected_impact = (finding.new_unit_cost_eur - finding.old_unit_cost_eur) * units
    if abs(expected_impact - finding.monthly_impact_eur) > 0.02 + units * 0.0001:  # costs are rounded to 4 decimals
        return f"the monthly impact {finding.monthly_impact_eur} does not agree with the cost change and {units:.1f} units a month ({expected_impact:.2f})"
    return None


@lru_cache(maxsize=1)
def retail_prices() -> dict[str, float]:
    """The shop's retail price of every SKU, read from the catalog."""
    return {product.sku: product.retail_price_eur for product in load_catalog(CATALOG_PATH)}


def numbers_in(text: str) -> list[float]:
    """Every number written in a row, with a dot or a comma as decimal separator."""
    return [float(number.replace(",", ".")) for number in NUMBER.findall(text)]


def cost_comes_from_row(unit_cost_eur: float, source: SourceRef) -> bool:
    """True if a price written in the row gives this unit cost: price / pack size * exchange rate.

    Only the row's own pack size and currency are used, so a cost that forgot the pack
    or the exchange rate does not pass. A pack size other than 1 must be written in the row.
    """
    if source.currency not in FX_TO_EUR or not source.pack_size:
        return False
    numbers = numbers_in(source.raw_text)
    if source.pack_size != 1 and float(source.pack_size) not in numbers:
        return False
    rate = FX_TO_EUR[source.currency]
    return any(abs(price / source.pack_size * rate - unit_cost_eur) < CENT for price in numbers)


def percent_is_written(percent: float, text: str) -> bool:
    """True if this percentage is literally written in the text, e.g. '4%' or '4 %'."""
    wanted = f"{percent:g}"
    return any(found.replace(",", ".") == wanted for found in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", text))
