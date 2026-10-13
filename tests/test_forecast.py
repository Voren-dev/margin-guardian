"""mg.forecast: monthly units and price elasticity from the sales history."""
import pytest

from conftest import CATALOG
from mg.catalog import load_catalog
from mg.forecast import Sale, estimate_elasticity, load_sales, monthly_units

# The elasticities the demo sales were generated with (data/demo/ANSWER_KEY.md).
TRUE_ELASTICITY = {
    "Accessories": -1.5, "Apparel": -1.7, "Bags": -1.4, "Bottles": -1.6, "Brakes": -0.6,
    "Components": -0.8, "Drivetrain": -0.7, "Lights": -1.3, "Locks": -0.9, "Maintenance": -0.8,
    "Pumps": -1.1, "Saddles": -1.0, "Tools": -1.0, "Tubes": -0.5, "Tyres": -0.9,
}


def test_monthly_units_is_the_average_of_the_last_twelve_months():
    sales = [Sale(month=f"2025-{m:02d}", sku="A", units_sold=100, avg_selling_price_eur=10) for m in range(1, 13)]
    sales += [Sale(month=f"2026-{m:02d}", sku="A", units_sold=50, avg_selling_price_eur=10) for m in range(1, 13)]
    assert monthly_units("A", sales) == 50
    assert monthly_units("unknown", sales) is None


def test_top_seller_sells_about_what_the_catalog_says():
    assert monthly_units("RL-1001", load_sales()) == pytest.approx(140, abs=5)


@pytest.mark.parametrize("category, true_value", sorted(TRUE_ELASTICITY.items()))
def test_elasticity_is_recovered_from_the_sales_history(category, true_value):
    estimate = estimate_elasticity(category, load_sales(), load_catalog(CATALOG))
    assert estimate.low <= true_value <= estimate.high  # the true value is inside the interval
    assert estimate.value == pytest.approx(true_value, abs=0.31)
    assert estimate.value < 0  # a higher price never sells more here


def test_no_price_change_means_no_estimate():
    products = [p for p in load_catalog(CATALOG) if p.sku == "RL-1001"]
    flat = [Sale(month=f"2026-{m:02d}", sku="RL-1001", units_sold=100 + m, avg_selling_price_eur=48.99) for m in range(1, 13)]
    assert estimate_elasticity("Lights", flat, products) is None
