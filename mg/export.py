"""The new retail prices of the reprice move, as a CSV file the shop can import.

Shop platforms and stock software update prices from a CSV file, so this is the
format that saves retyping. Only products whose price actually goes up are listed.
"""
import csv
import io

from mg.catalog import Product
from mg.schemas import Move

COLUMNS = ["sku", "product", "supplier", "current_price_eur", "new_price_eur", "change_pct"]


def new_prices_csv(moves: list[Move], findings_sku: dict[str, str], products: dict[str, Product]) -> str:
    """One row per product to reprice. `findings_sku` maps a finding id to its SKU."""
    rows = []
    for move in moves:
        if move.kind != "reprice" or move.new_retail_price_eur is None:
            continue
        product = products[findings_sku[move.finding_id]]
        current = product.retail_price_eur
        if move.new_retail_price_eur <= current:
            continue
        rows.append(
            {
                "sku": product.sku,
                "product": product.name,
                "supplier": product.supplier,
                "current_price_eur": f"{current:.2f}",
                "new_price_eur": f"{move.new_retail_price_eur:.2f}",
                "change_pct": f"{(move.new_retail_price_eur / current - 1) * 100:.1f}",
            }
        )

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(sorted(rows, key=lambda row: row["sku"]))
    return out.getvalue()
