import pytest
from pydantic import ValidationError

from mg.schemas import Change, Decision, Finding, MatchedChange, Move, PriceLine, SourceRef


def pads_line(price, pack_size, document):
    source = SourceRef(document=document, sheet="Prices", row=12, raw_text=f"TG-B4001 | Disc pads | {price}")
    return PriceLine(
        supplier="TrailGear Ltd",
        supplier_code="TG-B4001",
        description="Disc brake pads organic",
        price=price,
        currency="GBP",
        pack_size=pack_size,
        source=source,
    )


def test_price_line_keeps_its_source():
    line = pads_line(5.10, 2, "trailgear_autumn-2026.xlsx")
    assert line.source.document == "trailgear_autumn-2026.xlsx"
    assert line.min_order_qty == 1
    assert line.markers == []


def test_a_price_line_without_source_is_rejected():
    with pytest.raises(ValidationError):
        PriceLine(supplier="TrailGear Ltd", supplier_code="TG-B4001", description="x", price=5.10, currency="GBP")


def test_unknown_kind_is_rejected():
    with pytest.raises(ValidationError):
        Change(supplier_code="TG-B4001", kind="price_sideways")


def test_misspelled_field_is_rejected():
    with pytest.raises(ValidationError):
        Decision(finding_id="F1", status="approved", final_price=4.99)


def test_matched_change_is_a_change_plus_the_catalog_link():
    old = pads_line(9.60, 4, "trailgear_summer-2026.xlsx")
    new = pads_line(5.10, 2, "trailgear_autumn-2026.xlsx")
    matched = MatchedChange(
        supplier_code="TG-B4001", kind="pack_change", old=old, new=new,
        sku="RL-1044", match_method="exact_code", confidence=1.0,
    )
    assert isinstance(matched, Change)
    # the pack trap: the listed price drops, the price per unit goes up 6.25%
    old_unit = matched.old.price / matched.old.pack_size
    new_unit = matched.new.price / matched.new.pack_size
    assert matched.new.price < matched.old.price
    assert round((new_unit / old_unit - 1) * 100, 2) == 6.25


def test_finding_survives_a_json_round_trip():
    new = pads_line(5.10, 2, "trailgear_autumn-2026.xlsx")
    finding = Finding(
        id="F1", sku="RL-1044", kind="pack_change",
        old_unit_cost_eur=2.81, new_unit_cost_eur=2.98, pct_change=6.25,
        old_margin_pct=43.7, new_margin_pct=40.2, monthly_impact_eur=14.9,
        rationale="Pack of 4 became a pack of 2.",
        sources=[new.source],
        calc_trace="(5.10 / 2) / (9.60 / 4) - 1 = 6.25%",
    )
    assert Finding.model_validate_json(finding.model_dump_json()) == finding


def test_move_kind_is_one_of_the_three():
    Move(finding_id="F1", kind="negotiate", yearly_impact_eur=-90.0, units_delta=0,
         assumptions="The supplier accepts half of the increase.", calc_trace="...")
    with pytest.raises(ValidationError):
        Move(finding_id="F1", kind="ignore", yearly_impact_eur=0, units_delta=0, assumptions="", calc_trace="")
