"""mg.extract.photo: a row of a photo counts only if the two readings agree on it."""
from mg.extract import photo
from mg.report import supplier_of


def reading(*rows, notes=()):
    return {
        "supplier": "Ciclo Componenti Srl", "currency": "€",
        "lines": [{"code": c, "description": "x", "price": p, "pack": k, "moq": 1, "marker": m} for c, p, k, m in rows],
        "notes": [{"text": t, "marker": "*"} for t in notes],
    }


def test_only_the_rows_both_readings_agree_on_are_kept():
    first = reading(("CC-A118", 18.5, 1, "*"), ("CC-B200", 9.6, 8, ""), ("CC-C300", 4.1, 1, ""))
    second = reading(("cc-a118", "18,50", 1, "*"), ("CC-B200", 9.6, 10, ""))  # pack read differently, C300 missing
    agreed, dropped = photo.agreed_rows(first, second)
    assert [row["code"] for row in agreed] == ["CC-A118"]
    assert dropped == 2


def test_a_row_with_an_unreadable_price_is_left_out():
    assert photo.clean_row({"code": "CC-A118", "price": "n/a"}) is None
    assert photo.clean_row({"code": "", "price": 3}) is None


def test_the_photo_becomes_price_lines_of_the_right_supplier(monkeypatch):
    rows = [("CC-A118", 18.5, 1, "*"), ("CC-A121", 22.9, 1, "*"), ("CC-S305", 12.4, 1, ""), ("CC-S310", 8.9, 1, "")]
    monkeypatch.setattr(photo, "ask_model", lambda content, mime, model: reading(*rows))
    supplier, lines, notes, dropped, model = photo.read_photo(b"jpeg")
    assert model == "Gemma-4-31B-IT"
    assert dropped == 0 and lines[0].currency == "EUR" and lines[0].markers == ["*"]
    assert lines[0].source.document == photo.PHOTO_NAME and "18.50" in lines[0].source.raw_text
    assert supplier_of(lines) == "ciclo"


def test_a_surcharge_needs_both_readings(monkeypatch):
    note = "dal 1 novembre 2026 maggiorazione del 4% sugli articoli con *"
    monkeypatch.setattr(photo, "read_note", lambda text: {"surcharge_pct": 4.0, "valid_from": "2026-11-01"})
    both = photo.photo_notes(reading(notes=[note]), reading(notes=[note]))
    one = photo.photo_notes(reading(notes=[note]), reading(notes=["maggiorazione sugli articoli con *"]))
    assert both[0].effect == {"surcharge_pct": 4.0}
    assert one[0].effect == {}


def test_a_note_that_writes_the_star_refers_to_the_starred_rows():
    assert photo.note_marker({"marker": ""}, "maggiorazione del 4% sugli articoli contrassegnati con *") == "*"
    assert photo.note_marker({}, "Prezzi IVA esclusa") is None


def test_when_gemma_is_down_the_next_model_reads_the_photo(monkeypatch):
    def ask(content, mime, model):
        if model == "Gemma-4-31B-IT":
            raise photo.llm.LLMError("HTTP 500: no available workers")
        return reading(("CC-A118", 18.5, 1, "*"))
    monkeypatch.setattr(photo, "ask_model", ask)
    assert photo.read_photo(b"jpeg")[4] == "Qwen3.8-Flash-Next"
