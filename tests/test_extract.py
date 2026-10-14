"""mg.extract: a price list file -> (list of PriceLine, list of DocumentNote)."""
import pytest

from conftest import ALUMINIUM_CODES, PRICE_LISTS

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


def test_pdf_lines_point_to_their_page_and_row():
    lines, _ = by_code("veloparts")
    light = lines["VP-10233"]
    assert light.source.page == 1
    assert "VP-10233" in light.source.raw_text and "26.39" in light.source.raw_text


def test_unknown_format_is_refused():
    from mg.extract import extract_price_list

    with pytest.raises(ValueError, match="unsupported"):
        extract_price_list("price-list.docx")


# --- the check of the extractor's answer against the PDF (no network: answers are written by hand) ---

PDF_ROWS = [
    (1, 5, "VP-60010  Satteltasche S, 0,6 L  Bags  1  9.90"),
    (1, 6, "VP-60020  Rahmentasche 1,5 L wasserabweisend  Bags  1  16.20"),
    (1, 7, "Preise netto zzgl. MwSt. Gültig ab 01.10.2026. Mindestbestellwert 250 EUR."),
]


def answer(*lines):
    return {"lines": [{"supplier_code": code, "price": price} for code, price in lines]}


def test_a_correct_answer_passes_the_check():
    from mg.extract.pdf import check_against_pdf

    data = answer(("VP-60010", 9.90), ("VP-60020", 16.20))
    assert check_against_pdf(data, PDF_ROWS) == []
    assert data["lines"][1]["row"] == 6
    assert data["lines"][1]["raw_text"] == PDF_ROWS[1][2]


def test_a_wrong_price_is_caught():
    from mg.extract.pdf import check_against_pdf

    problems = check_against_pdf(answer(("VP-60010", 24.90), ("VP-60020", 16.20)), PDF_ROWS)
    assert len(problems) == 1 and "VP-60010" in problems[0] and "24.9" in problems[0]


def test_a_skipped_row_is_caught():
    from mg.extract.pdf import check_against_pdf

    problems = check_against_pdf(answer(("VP-60010", 9.90)), PDF_ROWS)
    assert len(problems) == 1 and "VP-60020" in problems[0]


def test_an_invented_product_is_caught():
    from mg.extract.pdf import check_against_pdf

    problems = check_against_pdf(answer(("VP-60010", 9.90), ("VP-60020", 16.20), ("VP-99999", 5.00)), PDF_ROWS)
    assert problems == ["VP-99999 is not in the document"]


def test_a_footnote_number_must_be_written_in_the_note():
    from mg.extract.pdf import keep_what_is_written

    note = "Dal 1° novembre 2026 verrà applicata una maggiorazione del 4% sugli articoli con *."
    assert keep_what_is_written({"surcharge_pct": 4, "valid_from": "2026-11-01"}, note) == {
        "surcharge_pct": 4.0,
        "valid_from": "2026-11-01",
    }
    # a surcharge the note does not state is dropped, and its date with it
    assert keep_what_is_written({"surcharge_pct": 6, "valid_from": "2026-11-01"}, note) == {
        "surcharge_pct": None,
        "valid_from": None,
    }


def test_every_line_points_to_its_row():
    for supplier in PRICE_LISTS:
        lines, _ = by_code(supplier)
        for line in lines.values():
            assert line.source.document == PRICE_LISTS[supplier][1].name
            assert line.supplier_code in line.source.raw_text


def test_a_malformed_answer_becomes_a_problem_not_a_crash():
    from mg.extract.pdf import check_against_pdf
    rows = [(1, 1, "VP-10233  Front light  1  26.39")]
    for bad in (
        {"lines": [{"supplier_code": "VP-10233", "price": "€ 26,39"}]},
        {"lines": [{"price": 26.39}]},
        {"lines": [{"supplier_code": "VP-10233", "price": None}]},
        {"lines": ["not a line"]},
        {},
    ):
        problems = check_against_pdf(bad, rows)
        assert problems, bad


def test_a_line_extracted_twice_is_a_problem():
    from mg.extract.pdf import check_against_pdf
    rows = [(1, 1, "VP-10233  Front light  1  26.39")]
    line = {"supplier_code": "VP-10233", "price": 26.39}
    problems = check_against_pdf({"lines": [dict(line), dict(line)]}, rows)
    assert any("twice" in problem for problem in problems)
