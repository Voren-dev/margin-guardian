"""mg.extract: a price list file -> (list of PriceLine, list of DocumentNote)."""
import pytest

from conftest import ALUMINIUM_CODES, PRICE_LISTS

pytestmark = pytest.mark.xfail(reason="mg.extract is not built yet")


def by_code(supplier):
    from mg.extract import extract_price_list

    lines, notes = extract_price_list(PRICE_LISTS[supplier][1])
    return {line.supplier_code: line for line in lines}, notes


def test_veloparts_pdf_is_read():
    lines, _ = by_code("veloparts")
    assert lines["VP-10233"].price == 26.39
    assert lines["VP-10233"].currency == "EUR"
    assert "VP-10250" in lines  # the new product
    assert "VP-50320" not in lines  # discontinued


def test_ciclo_prices_with_a_comma_are_read():
    lines, _ = by_code("ciclo")
    assert lines["CC-S305"].price == 18.25
    assert lines["CC-C705"].price == 22.90
    assert lines["CC-G401"].min_order_qty == 20


def test_ciclo_footnote_becomes_a_document_note():
    lines, notes = by_code("ciclo")
    surcharges = [note for note in notes if note.effect.get("surcharge_pct") == 4]
    assert len(surcharges) == 1
    assert surcharges[0].applies_to_marker == "*"
    assert str(surcharges[0].valid_from) == "2026-11-01"
    marked = {code for code, line in lines.items() if "*" in line.markers}
    assert marked == ALUMINIUM_CODES


def test_trailgear_is_in_gbp_with_pack_sizes():
    lines, _ = by_code("trailgear")
    assert all(line.currency == "GBP" for line in lines.values())
    assert lines["TG-B4001"].price == 5.10
    assert lines["TG-B4001"].pack_size == 2


def test_every_line_points_to_its_row():
    for supplier in PRICE_LISTS:
        lines, _ = by_code(supplier)
        for line in lines.values():
            assert line.source.document == PRICE_LISTS[supplier][1].name
            assert line.supplier_code in line.source.raw_text
