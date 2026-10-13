"""Step 1: a supplier price list file -> (list of PriceLine, list of DocumentNote)."""
from pathlib import Path

from mg.extract.pdf import read_pdf_price_list
from mg.extract.xlsx import read_xlsx_price_list
from mg.schemas import DocumentNote, PriceLine


def extract_price_list(path) -> tuple[list[PriceLine], list[DocumentNote]]:
    """Read one price list, choosing the reader from the file extension."""
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return read_xlsx_price_list(path)
    if path.suffix.lower() == ".pdf":
        return read_pdf_price_list(path)
    raise ValueError(f"unsupported price list format: {path.name}")
