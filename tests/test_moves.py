"""mg.moves: a Finding -> absorb, reprice, negotiate, each with its numbers."""
import pytest

from conftest import all_findings
from mg.catalog import Product
from mg.forecast import Elasticity
from mg.moves import absorb, build_moves, negotiate, price_that_restores_the_margin, reprice
from mg.schemas import Finding, SourceRef

# A product bought at 6.00 and sold at 10.00 (margin 40%), 100 pieces a month.
# The supplier raises the cost to 6.60 (+10%): 0.60 more per piece, 60 EUR a month.
PRODUCT = Product(
    sku="T-1", name="Test product", category="Test", supplier="S", supplier_code="S-1",
    unit_cost_eur=6.00, retail_price_eur=10.00, avg_monthly_units=100,
)
FINDING = Finding(
    id="T-1-price_up", sku="T-1", kind="price_up",
    old_unit_cost_eur=6.00, new_unit_cost_eur=6.60, pct_change=10.0,
    old_margin_pct=40.0, new_margin_pct=34.0, monthly_impact_eur=60.0,
    rationale="test", calc_trace="test",
    sources=[SourceRef(document="test.pdf", row=1, raw_text="S-1 6.60")],
)
UNITS = 100.0


def elasticity(value):
    return Elasticity(category="Test", value=value, low=value - 0.3, high=value + 0.3, products=3, observations=72)


def test_absorb_costs_the_whole_increase_for_a_year():
    move = absorb(FINDING, UNITS)
    assert move.yearly_impact_eur == pytest.approx(-720.00)  # 0.60 * 100 * 12
    assert move.units_delta == 0


def test_negotiate_costs_half_of_it_and_says_it_is_an_assumption():
    move = negotiate(FINDING, UNITS)
    assert move.yearly_impact_eur == pytest.approx(-360.00)
    assert "ASSUMPTION" in move.assumptions


def test_the_price_that_restores_the_margin():
    # cost 6.60, margin 40% -> 6.60 / 0.60 = 11.00
    assert price_that_restores_the_margin(6.60, 40.0) == pytest.approx(11.00)


def test_reprice_with_customers_who_do_not_react_keeps_all_the_units():
    move = reprice(FINDING, PRODUCT, UNITS, elasticity(0.0), cheapest_competitor=None)
    # price 11.00, same 100 units: (11.00 - 6.60) * 100 * 12 = 5280, before (10 - 6) * 100 * 12 = 4800
    assert move.yearly_impact_eur == pytest.approx(480.00)
    assert move.units_delta == 0


def test_reprice_sells_fewer_pieces_when_customers_react():
    move = reprice(FINDING, PRODUCT, UNITS, elasticity(-1.0), cheapest_competitor=None)
    # price +10% with elasticity -1 -> units 100 * (11/10)^-1 = 90.91
    assert move.units_delta == pytest.approx((90.909 - 100) * 12, abs=0.1)
    # (11.00 - 6.60) * 90.909 * 12 = 4800.0 -> same profit as before
    assert move.yearly_impact_eur == pytest.approx(0.0, abs=0.05)


def test_reprice_stops_at_the_cheapest_competitor():
    move = reprice(FINDING, PRODUCT, UNITS, elasticity(0.0), cheapest_competitor=10.50)
    assert "10.50" in move.assumptions and "partly" in move.assumptions
    # (10.50 - 6.60) * 100 * 12 = 4680 -> 120 less than before
    assert move.yearly_impact_eur == pytest.approx(-120.00)


def test_reprice_has_no_room_when_a_competitor_is_already_cheaper():
    move = reprice(FINDING, PRODUCT, UNITS, elasticity(-1.0), cheapest_competitor=9.50)
    assert "no room" in move.assumptions
    assert move.yearly_impact_eur == pytest.approx(absorb(FINDING, UNITS).yearly_impact_eur)


def test_no_elasticity_means_no_reprice_move():
    assert reprice(FINDING, PRODUCT, UNITS, None, cheapest_competitor=None) is None


def test_top_seller_gets_its_three_moves():
    findings = all_findings()
    moves = {move.kind: move for move in build_moves(findings) if move.finding_id == "RL-1001-price_up"}
    assert set(moves) == {"absorb", "reprice", "negotiate"}
    # VP-10233: 26.39 - 24.90 = 1.49 more per piece, about 137.6 pieces a month
    assert moves["absorb"].yearly_impact_eur == pytest.approx(-1.49 * 137.58 * 12, abs=1.0)
    assert moves["negotiate"].yearly_impact_eur == pytest.approx(moves["absorb"].yearly_impact_eur / 2, abs=0.01)
    assert "51.92" in moves["reprice"].assumptions  # 26.39 / (1 - 0.4917)
    assert moves["reprice"].units_delta < 0
    assert moves["reprice"].yearly_impact_eur > moves["absorb"].yearly_impact_eur


def test_a_price_that_went_down_gets_no_moves():
    findings = all_findings()
    cheaper = [f.id for f in findings if f.monthly_impact_eur <= 0]
    assert cheaper  # the torque wrench
    assert not [move for move in build_moves(findings) if move.finding_id in cheaper]


def test_a_reprice_that_ends_above_the_old_profit_says_why():
    moves = build_moves(all_findings())
    above = [m for m in moves if m.kind == "reprice" and m.yearly_impact_eur > 0]
    assert above, "the demo has reprice moves that earn more than before"
    assert all("earning more than before" in m.assumptions for m in above)
