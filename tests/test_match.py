"""mg.match: old vs new price list -> Change; Change + catalog -> MatchedChange."""
import pytest

from conftest import CATALOG, PRICE_LISTS, changes_for
from mg.match import diff_price_lists
from mg.schemas import PriceLine, SourceRef

pdf_not_built = pytest.mark.xfail(reason="the PDF reader is not built yet")
llm_match_not_built = pytest.mark.xfail(reason="matching by product name with the model is not built yet")


def line(code, price, pack_size=1, min_order_qty=1):
    """A hand-written price list row, for the suppliers whose PDF is not readable yet."""
    return PriceLine(
        supplier="Test Supplier",
        supplier_code=code,
        description=code,
        price=price,
        currency="EUR",
        pack_size=pack_size,
        min_order_qty=min_order_qty,
        source=SourceRef(document="test.pdf", page=1, row=1, raw_text=f"{code} {price}"),
    )


def kinds_of(changes):
    kinds = {}
    for change in changes:
        kinds.setdefault(change.supplier_code, []).append(change.kind)
    return kinds


def test_veloparts_rows_written_by_hand():
    old = [
        line("VP-10233", 24.90), line("VP-10234", 11.40), line("VP-10240", 19.80),
        line("VP-30108", 34.90), line("VP-60030", 8.30), line("VP-50310", 39.50),
        line("VP-50320", 6.20),
    ]
    new = [
        line("VP-10233", 26.39), line("VP-10234", 11.75), line("VP-10240", 19.80),
        line("VP-30108", 36.20), line("VP-60030", 8.65), line("VP-50310", 37.50),
        line("VP-10250", 32.80),
    ]
    assert kinds_of(diff_price_lists(old, new)) == {
        "VP-10233": ["price_up"],
        "VP-10234": ["price_up"],
        "VP-30108": ["price_up"],
        "VP-60030": ["price_up"],
        "VP-50310": ["price_down"],
        "VP-10250": ["new_product"],
        "VP-50320": ["discontinued"],
    }


def test_ciclo_rows_written_by_hand():
    old = [line("CC-S305", 16.90), line("CC-C705", 21.90), line("CC-G401", 6.40, min_order_qty=5)]
    new = [line("CC-S305", 18.25), line("CC-C705", 22.90), line("CC-G401", 6.40, min_order_qty=20)]
    assert kinds_of(diff_price_lists(old, new)) == {
        "CC-S305": ["price_up"],
        "CC-C705": ["price_up"],
        "CC-G401": ["moq_change"],
    }


def test_pack_change_hides_the_listed_price_change():
    """Pack of 4 at 9.60 -> pack of 2 at 5.10: one pack_change, no price_down."""
    changes = diff_price_lists([line("TG-B4001", 9.60, pack_size=4)], [line("TG-B4001", 5.10, pack_size=2)])
    assert [change.kind for change in changes] == ["pack_change"]
    assert changes[0].old.pack_size == 4 and changes[0].new.pack_size == 2


def test_price_and_minimum_order_can_change_together():
    changes = diff_price_lists([line("X-1", 10.00, min_order_qty=5)], [line("X-1", 11.00, min_order_qty=20)])
    assert [change.kind for change in changes] == ["price_up", "moq_change"]


def test_same_price_written_differently_is_not_a_change():
    assert diff_price_lists([line("X-1", 5.10)], [line("X-1", 5.1)]) == []


def test_a_code_listed_twice_is_an_error():
    with pytest.raises(ValueError):
        diff_price_lists([line("X-1", 1.00), line("X-1", 2.00)], [])


@pdf_not_built
def test_veloparts_changes():
    kinds = changes_for("veloparts")
    for code in ("VP-10233", "VP-10234", "VP-30108", "VP-60030"):
        assert kinds[code] == ["price_up"]
    assert kinds["VP-50310"] == ["price_down"]
    assert kinds["VP-50320"] == ["discontinued"]
    assert kinds["VP-10250"] == ["new_product"]
    assert len(kinds) == 7  # nothing else changed


@pdf_not_built
def test_ciclo_changes():
    kinds = changes_for("ciclo")
    assert "price_up" in kinds["CC-S305"]
    assert "price_up" in kinds["CC-C705"]
    assert "moq_change" in kinds["CC-G401"]


def test_trailgear_changes():
    kinds = changes_for("trailgear")
    for code in ("TG-T1001", "TG-T1002", "TG-T1010", "TG-T1020", "TG-L5001"):
        assert kinds[code] == ["price_up"]
    assert kinds["TG-B4001"] == ["pack_change"]
    assert len(kinds) == 6  # nothing else changed


def test_trailgear_codes_find_their_sku():
    from mg.extract import extract_price_list
    from mg.match import match_to_catalog

    old_path, new_path = PRICE_LISTS["trailgear"]
    old_lines, _ = extract_price_list(old_path)
    new_lines, _ = extract_price_list(new_path)
    matched = match_to_catalog(diff_price_lists(old_lines, new_lines), CATALOG)
    assert {m.supplier_code: m.sku for m in matched}["TG-B4001"] == "RL-1044"
    for m in matched:
        assert m.sku is not None
        assert m.match_method == "exact_code"
        assert m.confidence == 1.0


def test_a_code_the_catalog_does_not_know_has_no_sku():
    from mg.match import match_to_catalog

    changes = diff_price_lists([], [line("ZZ-0001", 9.90)])  # a new product
    matched = match_to_catalog(changes, CATALOG)[0]
    assert matched.kind == "new_product"
    assert matched.sku is None


@pdf_not_built
def test_every_known_code_finds_its_sku():
    from mg.extract import extract_price_list
    from mg.match import match_to_catalog

    for old_path, new_path in PRICE_LISTS.values():
        old_lines, _ = extract_price_list(old_path)
        new_lines, _ = extract_price_list(new_path)
        for matched in match_to_catalog(diff_price_lists(old_lines, new_lines), CATALOG):
            if matched.kind == "new_product":
                continue  # VP-10250 is not in the catalog yet
            assert matched.sku is not None
            assert matched.match_method == "exact_code"
            assert matched.confidence == 1.0


@llm_match_not_built
@pytest.mark.network
def test_a_code_missing_from_the_catalog_goes_through_the_model():
    """A known product whose supplier code is not in the catalog is matched by name."""
    from mg.extract import extract_price_list
    from mg.match import match_to_catalog

    old_path, new_path = PRICE_LISTS["veloparts"]
    old_lines, _ = extract_price_list(old_path)
    new_lines, _ = extract_price_list(new_path)
    changes = diff_price_lists(old_lines, new_lines)
    front_light = next(c for c in changes if c.supplier_code == "VP-10233")
    # same product, but with a code the catalog has never seen
    renamed = front_light.model_copy(update={"supplier_code": "VP-X0001"})
    matched = match_to_catalog([renamed], CATALOG)[0]
    assert matched.sku == "RL-1001"
    assert matched.match_method == "llm"
