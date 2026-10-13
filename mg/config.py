"""Fixed values the calculations depend on. Each one is declared, never guessed."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The shop's catalog: SKU, supplier code, unit cost, retail price, average monthly units.
CATALOG_PATH = ROOT / "data" / "demo" / "catalog.csv"

# The shop's sales: one row per product and month (units sold, average selling price).
SALES_HISTORY_PATH = ROOT / "data" / "demo" / "sales_history.csv"

# Exchange rates to EUR. These are fixed DEMO rates, not market rates:
# the demo data was built with 1 GBP = 1.17 EUR (see data/demo/README.md).
# With real data this becomes a dated rate from a named source.
FX_TO_EUR = {
    "EUR": 1.0,
    "GBP": 1.17,
}
FX_NOTE = "demo rate, fixed (data/demo/README.md)"

# The Evolus document extractor that reads PDF price lists, and its output format.
# These are identifiers, not secrets: without the API key they open nothing.
# Set the two variables to point the code at another workspace.
EVOLUS_EXTRACTOR_ID = os.environ.get("EVOLUS_EXTRACTOR_ID", "38d6aa12-292a-4746-9b3c-bd910df0e753")
EVOLUS_PRICE_LIST_FORMAT_ID = os.environ.get("EVOLUS_PRICE_LIST_FORMAT_ID", "a2096135-3a56-4d52-8020-86a364964cf2")

# Saved extractor answers, one per PDF. Reused while the PDF is unchanged.
EXTRACT_RESULTS_DIR = ROOT / "data" / "demo" / "results" / "extract"
