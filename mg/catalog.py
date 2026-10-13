"""The shop's catalog, read from a CSV file."""
import csv
from pathlib import Path

from pydantic import BaseModel


class Product(BaseModel):
    """One row of the catalog."""

    sku: str
    name: str
    category: str
    supplier: str
    supplier_code: str
    unit_cost_eur: float
    retail_price_eur: float
    avg_monthly_units: int


def load_catalog(path: Path | str) -> list[Product]:
    with open(path, newline="", encoding="utf-8") as f:
        return [Product(**row) for row in csv.DictReader(f)]
