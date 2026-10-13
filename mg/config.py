"""Fixed values the calculations depend on. Each one is declared, never guessed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The shop's catalog: SKU, supplier code, unit cost, retail price, average monthly units.
CATALOG_PATH = ROOT / "data" / "demo" / "catalog.csv"

# Exchange rates to EUR. These are fixed DEMO rates, not market rates:
# the demo data was built with 1 GBP = 1.17 EUR (see data/demo/README.md).
# With real data this becomes a dated rate from a named source.
FX_TO_EUR = {
    "EUR": 1.0,
    "GBP": 1.17,
}
FX_NOTE = "demo rate, fixed (data/demo/README.md)"
