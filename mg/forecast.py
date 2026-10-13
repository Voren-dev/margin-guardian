"""What the sales history says: how many pieces sell in a month, and how sales react to price.

Plain statistics on the shop's own data, no model involved.

Two numbers come out of here:

  monthly units     the average of the last 12 months of sales of a product.
                    Twelve months, so that a whole season is inside.

  price elasticity  by how many percent the units change when the price changes by 1%.
                    -1.3 means: price up 10%, units down about 13%.
                    It is estimated per product category with a linear regression on the
                    past price changes, and it always comes with its interval.
"""
import csv
import math
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from mg.catalog import Product
from mg.config import SALES_HISTORY_PATH

MONTHS_IN_A_YEAR = 12


class Sale(BaseModel):
    """One product in one month."""

    month: str  # "2026-09"
    sku: str
    units_sold: int
    avg_selling_price_eur: float


class Elasticity(BaseModel):
    """The estimate for one category, with what it is based on."""

    category: str
    value: float  # e.g. -1.3
    low: float  # 95% interval
    high: float
    products: int  # how many products of the category are in the data
    observations: int  # how many product-months


def load_sales(path: Path | str = SALES_HISTORY_PATH) -> list[Sale]:
    with open(path, newline="", encoding="utf-8") as f:
        return [Sale(**row) for row in csv.DictReader(f)]


def monthly_units(sku: str, sales: list[Sale]) -> float | None:
    """Average units per month over the last 12 months of the product. None if it has no history."""
    history = sorted((sale for sale in sales if sale.sku == sku), key=lambda sale: sale.month)
    last_year = history[-MONTHS_IN_A_YEAR:]
    if not last_year:
        return None
    return sum(sale.units_sold for sale in last_year) / len(last_year)


def estimate_elasticity(category: str, sales: list[Sale], products: list[Product]) -> Elasticity | None:
    """Price elasticity of one category, from its past price changes. None if it cannot be estimated.

    The regression, in words: the logarithm of the units sold is explained by
      - the logarithm of the price        -> its coefficient IS the elasticity
      - which product it is               -> some products simply sell more than others
      - which month of the year it is     -> the season
    Taking out product and season leaves the effect of the price alone.
    """
    skus = sorted(product.sku for product in products if product.category == category)
    rows = [sale for sale in sales if sale.sku in skus and sale.units_sold > 0]
    if not rows:
        return None

    # A price that never moved says nothing about how sales react to price.
    prices_by_sku = {sku: {sale.avg_selling_price_eur for sale in rows if sale.sku == sku} for sku in skus}
    if all(len(prices) < 2 for prices in prices_by_sku.values()):
        return None

    columns = []
    for sale in rows:
        month_of_year = int(sale.month[5:7])
        columns.append(
            [math.log(sale.avg_selling_price_eur)]
            + [1.0 if sale.sku == sku else 0.0 for sku in skus]
            + [1.0 if month_of_year == month else 0.0 for month in range(2, 13)]  # January is the baseline
        )
    x = np.array(columns)
    y = np.array([math.log(sale.units_sold) for sale in rows])

    coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
    elasticity = float(coefficients[0])

    # Standard error of the price coefficient -> 95% interval.
    residuals = y - x @ coefficients
    degrees_of_freedom = len(rows) - x.shape[1]
    if degrees_of_freedom <= 0:
        return None
    variance = float(residuals @ residuals) / degrees_of_freedom
    standard_error = math.sqrt(variance * float(np.linalg.pinv(x.T @ x)[0, 0]))

    return Elasticity(
        category=category,
        value=round(elasticity, 2),
        low=round(elasticity - 1.96 * standard_error, 2),
        high=round(elasticity + 1.96 * standard_error, 2),
        products=len(skus),
        observations=len(rows),
    )
