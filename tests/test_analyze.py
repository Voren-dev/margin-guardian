"""mg.analyze: MatchedChange -> Finding. All the maths is plain Python."""
import pytest

from conftest import all_findings

pytestmark = pytest.mark.xfail(reason="mg.analyze is not built yet")


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
