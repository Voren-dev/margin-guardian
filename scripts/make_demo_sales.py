#!/usr/bin/env python3
"""Generates data/demo/sales_history.csv: 24 months of invented sales per SKU.

Unlike a flat price history, this one contains past price changes and short promotions,
so the price elasticity of demand can be estimated from the data instead of being assumed.
The true elasticities used here are written in data/demo/ANSWER_KEY.md, for testing only.

Deterministic: the same seed always gives the same file.
"""
import csv
import math
import random
from pathlib import Path

SEED = 20261012
DEMO = Path(__file__).resolve().parent.parent / "data" / "demo"
MONTHS = [f"{y}-{m:02d}" for y, m in [(2024, 10), (2024, 11), (2024, 12)]
          + [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 10)]]

# Demand multiplier by calendar month: cycling season peaks in late spring and summer.
SEASON = {1: 0.70, 2: 0.74, 3: 0.98, 4: 1.10, 5: 1.34, 6: 1.26, 7: 1.28, 8: 1.24, 9: 1.04, 10: 0.90, 11: 0.72, 12: 0.70}
# Lights sell more when days get shorter.
SEASON_LIGHTS = {1: 1.10, 2: 0.95, 3: 0.85, 4: 0.80, 5: 0.82, 6: 0.80, 7: 0.82, 8: 0.90, 9: 1.10, 10: 1.30, 11: 1.32, 12: 1.24}

# True price elasticity of demand by category (units change by e% when price changes by 1%).
ELASTICITY = {
    "Lights": -1.3, "Locks": -0.9, "Pumps": -1.1, "Tools": -1.0, "Accessories": -1.5,
    "Components": -0.8, "Saddles": -1.0, "Drivetrain": -0.7, "Brakes": -0.6, "Tyres": -0.9,
    "Tubes": -0.5, "Maintenance": -0.8, "Bottles": -1.6, "Bags": -1.4, "Apparel": -1.7,
}
NOISE_SD = 0.07


def price_path(rng, final_price):
    """Returns one price per month, ending at the current catalog price."""
    prices = [final_price] * len(MONTHS)
    # Past permanent increases: before the change month the price was lower.
    n_changes = rng.choices([0, 1, 2], weights=[20, 45, 35])[0]
    change_months = sorted(rng.sample(range(3, len(MONTHS) - 2), n_changes), reverse=True)
    level = final_price
    last = len(MONTHS)
    for cm in change_months:
        for i in range(cm, last):
            prices[i] = level
        level = round(level / (1 + rng.uniform(0.04, 0.10)), 2)
        last = cm
    for i in range(0, last):
        prices[i] = level
    # Short promotions: one month at a discount, for most products.
    for _ in range(rng.choices([0, 1, 2], weights=[30, 45, 25])[0]):
        pm = rng.randrange(1, len(MONTHS) - 1)
        prices[pm] = round(prices[pm] * (1 - rng.uniform(0.10, 0.20)), 2)
    return prices


def main():
    rng = random.Random(SEED)
    rows = []
    with open(DEMO / "catalog.csv", newline="") as f:
        catalog = list(csv.DictReader(f))
    for item in catalog:
        final_price = float(item["retail_price_eur"])
        base = float(item["avg_monthly_units"])
        e = ELASTICITY[item["category"]]
        season = SEASON_LIGHTS if item["category"] == "Lights" else SEASON
        # Normalise so the last 12 months at the current price average the catalog figure.
        norm = sum(season.values()) / 12
        for month, price in zip(MONTHS, price_path(rng, final_price)):
            m = int(month[5:])
            expected = base * season[m] / norm * (price / final_price) ** e
            units = max(0, round(expected * math.exp(rng.gauss(0, NOISE_SD))))
            rows.append({"month": month, "sku": item["sku"], "units_sold": units, "avg_selling_price_eur": f"{price:.2f}"})
    with open(DEMO / "sales_history.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["month", "sku", "units_sold", "avg_selling_price_eur"])
        w.writeheader()
        w.writerows(rows)
    changed = len({r["sku"] for r in rows if float(r["avg_selling_price_eur"]) != float(next(c for c in catalog if c["sku"] == r["sku"])["retail_price_eur"])})
    print(f"{len(rows)} rows, {len(catalog)} SKUs, {len(MONTHS)} months, {changed} SKUs with at least one price change")


if __name__ == "__main__":
    main()
