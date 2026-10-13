"""mg.analyze: MatchedChange -> Finding. All the maths is plain Python."""
import pytest

from conftest import all_findings, findings_for
from mg.analyze import margin_pct, unit_cost_eur
from mg.schemas import PriceLine, SourceRef

surcharge_not_built = pytest.mark.xfail(reason="the footnote surcharge is not built yet")


def line(price, currency="EUR", pack_size=1):
    return PriceLine(
        supplier="Test Supplier",
        supplier_code="T-1",
        description="test",
        price=price,
        currency=currency,
        pack_size=pack_size,
        source=SourceRef(document="test.xlsx", sheet="s", row=1, raw_text="T-1"),
    )


def test_unit_cost_is_per_piece_and_in_eur():
    assert unit_cost_eur(line(10.00)) == pytest.approx(10.00)
    assert unit_cost_eur(line(10.00, pack_size=4)) == pytest.approx(2.50)
    assert unit_cost_eur(line(9.60, currency="GBP", pack_size=4)) == pytest.approx(2.808)


def test_unknown_currency_is_an_error():
    with pytest.raises(ValueError):
        unit_cost_eur(line(10.00, currency="USD"))


def test_margin_is_the_share_of_the_retail_price():
    assert margin_pct(retail_price=10.00, unit_cost=6.00) == pytest.approx(40.0)


def test_trailgear_pack_trap_is_an_increase_per_unit():
    pads = [f for f in findings_for("trailgear") if f.sku == "RL-1044"]  # TG-B4001
    assert len(pads) == 1
    assert pads[0].kind == "pack_change"
    assert pads[0].pct_change == pytest.approx(6.25, abs=0.01)
    assert pads[0].old_unit_cost_eur == pytest.approx(2.808)  # 9.60 GBP / 4 * 1.17
    assert pads[0].new_unit_cost_eur == pytest.approx(2.9835)  # 5.10 GBP / 2 * 1.17
    assert pads[0].new_margin_pct < pads[0].old_margin_pct
    assert pads[0].monthly_impact_eur == pytest.approx(14.92)  # 0.1755 EUR * 85 units


def test_trailgear_tyres_go_up_five_percent():
    by_sku = {f.sku: f for f in findings_for("trailgear")}
    for sku in ("RL-1036", "RL-1037", "RL-1038", "RL-1039"):
        assert by_sku[sku].kind == "price_up"
        assert by_sku[sku].pct_change == pytest.approx(5.0, abs=0.05)
    assert len(by_sku) == 6  # 4 tyres, the wet lube, the brake pads


def test_trailgear_findings_show_their_sources_and_their_maths():
    for finding in findings_for("trailgear"):
        assert len(finding.sources) == 2  # the old row and the new row
        assert "old unit cost" in finding.calc_trace
        assert "monthly impact" in finding.calc_trace


def test_top_seller_increase_is_first_by_impact():
    findings = sorted(all_findings(), key=lambda f: f.monthly_impact_eur, reverse=True)
    top = findings[0]
    assert top.sku == "RL-1001"  # VP-10233, front light 800 lm
    assert top.pct_change == pytest.approx(6.0, abs=0.05)
    assert top.old_unit_cost_eur == 24.90
    assert top.new_unit_cost_eur == 26.39


def test_pack_trap_is_an_increase_per_unit():
    pads = [f for f in all_findings() if f.sku == "RL-1044"]  # TG-B4001
    assert len(pads) == 1
    assert pads[0].pct_change == pytest.approx(6.25, abs=0.01)
    assert pads[0].new_unit_cost_eur > pads[0].old_unit_cost_eur
    assert pads[0].monthly_impact_eur > 0


@surcharge_not_built
def test_aluminium_surcharge_reaches_the_six_items():
    surcharged = [f for f in all_findings() if f.kind == "surcharge_note"]
    assert len(surcharged) == 6
    for finding in surcharged:
        assert finding.pct_change == pytest.approx(4.0, abs=0.01)


def test_price_decrease_has_a_negative_impact():
    wrench = [f for f in all_findings() if f.sku == "RL-1014" or f.kind == "price_down"]
    assert any(f.monthly_impact_eur < 0 for f in wrench)


def test_every_finding_shows_its_sources_and_its_maths():
    for finding in all_findings():
        assert finding.sources
        assert finding.calc_trace
