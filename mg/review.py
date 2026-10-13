"""Step 5: the reviewer. Finding -> AuditResult. Plain code, not a second model.

A Finding reaches the screen only if its numbers can be traced back to the rows of
the documents it cites. The reviewer does not trust the numbers it is given: it
starts again from the source rows and checks that the costs come out of them.

Three checks:
  1. the Finding cites its sources (no source, no number on screen);
  2. each unit cost comes out of a price written in its source row
     (price / pack size * exchange rate), or, for a footnote surcharge,
     out of the listed cost plus a percentage written in the footnote;
  3. the percentage change agrees with the two costs.
"""
import re

from mg.config import FX_TO_EUR
from mg.schemas import AuditResult, Finding

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

    old_row = finding.sources[0].raw_text
    if not cost_comes_from_row(finding.old_unit_cost_eur, old_row):
        return f"old unit cost {finding.old_unit_cost_eur} does not come out of its source row: {old_row}"

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
        new_row = finding.sources[1].raw_text
        if not cost_comes_from_row(finding.new_unit_cost_eur, new_row):
            return f"new unit cost {finding.new_unit_cost_eur} does not come out of its source row: {new_row}"

    expected_pct = (finding.new_unit_cost_eur - finding.old_unit_cost_eur) / finding.old_unit_cost_eur * 100
    if abs(expected_pct - finding.pct_change) > 0.05:
        return f"the change {finding.pct_change}% does not agree with the two costs ({expected_pct:.2f}%)"
    return None


def numbers_in(text: str) -> list[float]:
    """Every number written in a row, with a dot or a comma as decimal separator."""
    return [float(number.replace(",", ".")) for number in NUMBER.findall(text)]


def cost_comes_from_row(unit_cost_eur: float, raw_text: str) -> bool:
    """True if some price written in the row gives this unit cost: price / pack size * exchange rate.

    The pack size must be written in the row too (or be 1), and the rate must be one we declare.
    """
    numbers = numbers_in(raw_text)
    pack_sizes = {1.0} | {number for number in numbers if number == int(number) and 1 < number <= 1000}
    for price in numbers:
        for pack_size in pack_sizes:
            for rate in FX_TO_EUR.values():
                if abs(price / pack_size * rate - unit_cost_eur) < CENT:
                    return True
    return False


def percent_is_written(percent: float, text: str) -> bool:
    """True if this percentage is literally written in the text, e.g. '4%' or '4 %'."""
    wanted = f"{percent:g}"
    return any(found.replace(",", ".") == wanted for found in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", text))
