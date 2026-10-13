"""mg.match: old vs new price list -> Change; Change + catalog -> MatchedChange."""
import pytest

from conftest import CATALOG, PRICE_LISTS, changes_for

pytestmark = pytest.mark.xfail(reason="mg.match is not built yet")


def test_veloparts_changes():
    kinds = changes_for("veloparts")
    for code in ("VP-10233", "VP-10234", "VP-30108", "VP-60030"):
        assert kinds[code] == ["price_up"]
    assert kinds["VP-50310"] == ["price_down"]
    assert kinds["VP-50320"] == ["discontinued"]
    assert kinds["VP-10250"] == ["new_product"]
    assert len(kinds) == 7  # nothing else changed


def test_ciclo_changes():
    kinds = changes_for("ciclo")
    assert "price_up" in kinds["CC-S305"]
    assert "price_up" in kinds["CC-C705"]
    assert "moq_change" in kinds["CC-G401"]


def test_trailgear_changes():
    kinds = changes_for("trailgear")
    for code in ("TG-T1001", "TG-T1002", "TG-T1010", "TG-T1020", "TG-L5001"):
        assert kinds[code] == ["price_up"]
    assert "pack_change" in kinds["TG-B4001"]


def test_every_known_code_finds_its_sku():
    from mg.extract import extract_price_list
    from mg.match import diff_price_lists, match_to_catalog

    for old_path, new_path in PRICE_LISTS.values():
        old_lines, _ = extract_price_list(old_path)
        new_lines, _ = extract_price_list(new_path)
        for matched in match_to_catalog(diff_price_lists(old_lines, new_lines), CATALOG):
            if matched.kind == "new_product":
                continue  # VP-10250 is not in the catalog yet
            assert matched.sku is not None
            assert matched.match_method == "exact_code"
            assert matched.confidence == 1.0


@pytest.mark.network
def test_a_code_missing_from_the_catalog_goes_through_the_model():
    """A known product whose supplier code is not in the catalog is matched by name."""
    from mg.extract import extract_price_list
    from mg.match import diff_price_lists, match_to_catalog

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
