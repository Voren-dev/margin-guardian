"""mg.export: the reprice move -> a CSV of new retail prices."""
import csv
import io

from conftest import all_findings
from mg.catalog import load_catalog
from mg.config import CATALOG_PATH
from mg.export import COLUMNS, new_prices_csv
from mg.moves import build_moves


def demo_csv():
    findings = all_findings()
    products = {product.sku: product for product in load_catalog(CATALOG_PATH)}
    moves = build_moves(findings)
    return new_prices_csv(moves, {finding.id: finding.sku for finding in findings}, products), moves, products


def test_every_row_is_a_price_that_goes_up_and_matches_its_move():
    text, moves, products = demo_csv()
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows, "the demo has products to reprice"
    assert list(rows[0]) == COLUMNS
    prices = {m.new_retail_price_eur for m in moves if m.kind == "reprice"}
    for row in rows:
        assert float(row["new_price_eur"]) > float(row["current_price_eur"])
        assert float(row["current_price_eur"]) == products[row["sku"]].retail_price_eur
        assert float(row["new_price_eur"]) in {round(p, 2) for p in prices}


def test_a_product_appears_only_once():
    text, _, _ = demo_csv()
    skus = [row["sku"] for row in csv.DictReader(io.StringIO(text))]
    assert len(skus) == len(set(skus))
