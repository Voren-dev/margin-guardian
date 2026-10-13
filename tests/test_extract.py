"""mg.extract: a price list file -> (list of PriceLine, list of DocumentNote)."""
import pytest

from conftest import ALUMINIUM_CODES, PRICE_LISTS

pdf_not_built = pytest.mark.xfail(reason="the PDF reader is not built yet")


def by_code(supplier):
    from mg.extract import extract_price_list

    lines, notes = extract_price_list(PRICE_LISTS[supplier][1])
    return {line.supplier_code: line for line in lines}, notes


@pdf_not_built
def test_veloparts_pdf_is_read():
    lines, _ = by_code("veloparts")
    assert lines["VP-10233"].price == 26.39
    assert lines["VP-10233"].currency == "EUR"
    assert "VP-10250" in lines  # the new product
    assert "VP-50320" not in lines  # discontinued


@pdf_not_built
def test_ciclo_prices_with_a_comma_are_read():
    lines, _ = by_code("ciclo")
    assert lines["CC-S305"].price == 18.25
    assert lines["CC-C705"].price == 22.90
    assert lines["CC-G401"].min_order_qty == 20


@pdf_not_built
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


def test_trailgear_old_list_has_the_pack_of_four():
    from mg.extract import extract_price_list

    lines, _ = extract_price_list(PRICE_LISTS["trailgear"][0])
    pads = next(line for line in lines if line.supplier_code == "TG-B4001")
    assert (pads.price, pads.pack_size) == (9.60, 4)


def test_trailgear_lines_point_to_their_sheet_row():
    lines, notes = by_code("trailgear")
    assert len(lines) == 15
    pads = lines["TG-B4001"]
    assert pads.supplier == "TrailGear Ltd"
    assert pads.source.document == PRICE_LISTS["trailgear"][1].name
    assert pads.source.sheet == "Trade Prices"
    assert pads.source.row == 13
    assert "TG-B4001" in pads.source.raw_text and "5.1" in pads.source.raw_text
    assert any("GBP" in note.text for note in notes)


def test_pdf_says_not_implemented_yet():
    from mg.extract import extract_price_list

    with pytest.raises(NotImplementedError, match="not implemented yet"):
        extract_price_list(PRICE_LISTS["veloparts"][1])


@pdf_not_built
def test_every_line_points_to_its_row():
    for supplier in PRICE_LISTS:
        lines, _ = by_code(supplier)
        for line in lines.values():
            assert line.source.document == PRICE_LISTS[supplier][1].name
            assert line.supplier_code in line.source.raw_text
