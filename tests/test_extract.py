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
    return {"lines": [{"supplier_code": code, "price": price, "pack_size": 1} for code, price in lines]}


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
    line = {"supplier_code": "VP-10233", "price": 26.39, "pack_size": 1}
    problems = check_against_pdf({"lines": [dict(line), dict(line)]}, rows)
    assert any("twice" in problem for problem in problems)


# --- the pack size: under the pack column if there is one, 1 otherwise (rows with the spacing of the PDF) ---

PACK_ROWS = [
    (1, 7, "     Art.-Nr.             Bezeichnung / Description                 Kategorie             VE         Netto EUR"),
    (1, 9, "     VP-60010             Satteltasche S, 0,6 L                     Bags                        1              9.90"),
    (1, 11, "     VP-60011             Flickzeug, 10 Stück                       Bags                       10              4.80"),
]
MIN_ORDER_ROWS = [
    (1, 6, "     Codice             Articolo                                   Prezzo netto             Min. ord."),
    (1, 8, "     CC-G401            Manopole ergonomiche con blocco                 € 7,80             20 pz"),
]


def test_the_pack_printed_under_its_column_passes():
    from mg.extract.pdf import check_against_pdf

    data = {"lines": [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": 1},
                      {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 10}]}
    assert check_against_pdf(data, PACK_ROWS) == []
    assert data["lines"][1]["raw_text"] == "VP-60011  Flickzeug, 10 Stück  Bags  10  4.80"


def test_a_wrong_pack_is_caught():
    from mg.extract.pdf import check_against_pdf

    data = {"lines": [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": 1},
                      {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 1}]}
    problems = check_against_pdf(data, PACK_ROWS)
    assert len(problems) == 1 and "VP-60011" in problems[0] and "10 is printed" in problems[0]


def test_the_minimum_order_is_not_taken_for_a_pack():
    from mg.extract.pdf import check_against_pdf

    good = {"lines": [{"supplier_code": "CC-G401", "price": 7.80, "pack_size": 1}]}
    assert check_against_pdf(good, MIN_ORDER_ROWS) == []
    bad = {"lines": [{"supplier_code": "CC-G401", "price": 7.80, "pack_size": 20}]}
    problems = check_against_pdf(bad, MIN_ORDER_ROWS)
    assert len(problems) == 1 and "no pack column" in problems[0]


def test_a_pack_written_on_the_row_must_match():
    from mg.extract.pdf import check_against_pdf

    rows = [(1, 1, "     TG-B4001     Brake pads, pack of 2        5.10")]
    assert check_against_pdf({"lines": [{"supplier_code": "TG-B4001", "price": 5.10, "pack_size": 2}]}, rows) == []
    problems = check_against_pdf({"lines": [{"supplier_code": "TG-B4001", "price": 5.10, "pack_size": 4}]}, rows)
    assert len(problems) == 1 and "pack of 2" in problems[0]


def test_a_pack_that_is_not_a_whole_number_is_a_problem():
    from mg.extract.pdf import check_against_pdf

    for bad in (None, "two", 2.5, 0, float("inf"), float("nan"), "Infinity"):
        data = {"lines": [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": bad},
                          {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 10}]}
        problems = check_against_pdf(data, PACK_ROWS)
        assert len(problems) == 1 and "VP-60010" in problems[0], bad


def test_the_pack_header_is_recognised_in_its_variants():
    from mg.extract.pdf import check_against_pdf

    for header in ("VPE", "VE (Stk.)", "VE*", "Conf", "Pz/conf", "Pack Qty", "Inhalt"):
        rows = [(1, 7, PACK_ROWS[0][2].replace("VE        ", header.ljust(10)[:10], 1))] + PACK_ROWS[1:]
        good = {"lines": [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": 1},
                          {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 10}]}
        assert check_against_pdf(good, rows) == [], header
        bad = {"lines": [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": 1},
                         {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 1}]}
        problems = check_against_pdf(bad, rows)
        assert len(problems) == 1 and "10 is printed" in problems[0], header


def test_a_header_on_two_rows_finds_the_pack():
    from mg.extract.pdf import check_against_pdf

    rows = [
        (1, 1, "  Code      Description              Units/      Price"),
        (1, 2, "                                       Pack        EUR"),
        (1, 3, "  TG-1      Brake cable, steel         12          4.10"),
    ]
    assert check_against_pdf({"lines": [{"supplier_code": "TG-1", "price": 4.10, "pack_size": 12}]}, rows) == []
    problems = check_against_pdf({"lines": [{"supplier_code": "TG-1", "price": 4.10, "pack_size": 1}]}, rows)
    assert len(problems) == 1 and "12 is printed" in problems[0]


def test_an_empty_pack_cell_is_refused():
    from mg.extract.pdf import check_against_pdf

    lines = [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": 1},
             {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 10}]
    rows = PACK_ROWS + [(1, 13, "     VP-60012             Bottle cage                               Bags                                       4.10")]
    problems = check_against_pdf({"lines": lines + [{"supplier_code": "VP-60012", "price": 4.10, "pack_size": 1}]}, rows)
    assert len(problems) == 1 and "VP-60012" in problems[0] and "no pack size printed" in problems[0]
    # a pack printed with its unit, right-aligned, ends up nearer to the price: still refused, never taken as 1
    rows = PACK_ROWS + [(1, 13, "     VP-60012             Bottle cage                               Bags                          12 pz        4.10")]
    problems = check_against_pdf({"lines": lines + [{"supplier_code": "VP-60012", "price": 4.10, "pack_size": 1}]}, rows)
    assert len(problems) == 1 and "VP-60012" in problems[0]


def test_a_second_table_without_pack_column_ends_the_first():
    from mg.extract.pdf import check_against_pdf

    rows = PACK_ROWS + [
        (1, 14, "     Art.-Nr.             Service                                                            Netto EUR"),
        (1, 16, "     VP-90001             Workshop check                                                         25.00"),
    ]
    lines = [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": 1},
             {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 10}]
    assert check_against_pdf({"lines": lines + [{"supplier_code": "VP-90001", "price": 25.00, "pack_size": 1}]}, rows) == []
    problems = check_against_pdf({"lines": lines + [{"supplier_code": "VP-90001", "price": 25.00, "pack_size": 5}]}, rows)
    assert len(problems) == 1 and "no pack column" in problems[0]


def test_a_section_title_with_pack_word_is_not_a_header():
    from mg.extract.pdf import check_against_pdf

    rows = [
        (1, 1, "     Codice             Articolo                                   Prezzo netto"),
        (1, 3, "     Zubehör  VE"),
        (1, 4, "     CC-G401            Manopole ergonomiche con blocco                 € 7,80"),
    ]
    assert check_against_pdf({"lines": [{"supplier_code": "CC-G401", "price": 7.80, "pack_size": 1}]}, rows) == []


def test_a_translated_second_header_row_keeps_the_pack_column():
    from mg.extract.pdf import check_against_pdf

    rows = [PACK_ROWS[0],
            (1, 8, "     Code                 Description                               Category              Qty        Net EUR")] + PACK_ROWS[1:]
    good = {"lines": [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": 1},
                      {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 10}]}
    assert check_against_pdf(good, rows) == []
    bad = {"lines": [{"supplier_code": "VP-60010", "price": 9.90, "pack_size": 1},
                     {"supplier_code": "VP-60011", "price": 4.80, "pack_size": 1}]}
    problems = check_against_pdf(bad, rows)
    assert len(problems) == 1 and "10 is printed" in problems[0]
