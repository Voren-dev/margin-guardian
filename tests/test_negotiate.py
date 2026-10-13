"""mg.negotiate: the email to a supplier. Sentences from the tool, numbers from the code."""
import pytest

from conftest import CATALOG, all_findings
from mg import negotiate
from mg.catalog import load_catalog
from mg.forecast import load_sales, monthly_units
from mg.negotiate import NegotiationError, draft_email, template_problem

GOOD_TEMPLATE = (
    "Subject: Your new price list\n\nDear supplier,\n\n[PRODUCT_LIST]\n\nWe buy [YEARLY_UNITS] from you. "
    "This costs us [YEARLY_COST] more.\n\n[PROPOSAL]\n\nKind regards,\n[SENDER]"
)


def veloparts():
    products = {product.sku: product for product in load_catalog(CATALOG)}
    sales = load_sales()
    findings = [f for f in all_findings() if f.monthly_impact_eur > 0 and products[f.sku].supplier == "VeloParts GmbH"]
    units = {f.sku: monthly_units(f.sku, sales) for f in findings}
    return findings, products, units


def test_a_text_with_a_number_is_refused():
    assert template_problem(GOOD_TEMPLATE) is None
    assert "number" in template_problem(GOOD_TEMPLATE.replace("Dear supplier", "Dear supplier, prices went up 6%"))


def test_a_text_with_a_missing_gap_is_refused():
    assert "[PROPOSAL]" in template_problem(GOOD_TEMPLATE.replace("[PROPOSAL]", ""))


def test_the_email_carries_the_numbers_of_the_findings(monkeypatch):
    monkeypatch.setattr(negotiate, "load_or_write_template", lambda supplier: GOOD_TEMPLATE)
    findings, products, units = veloparts()
    draft = draft_email("VeloParts GmbH", findings, products, units)
    assert draft.to == "sales@veloparts.example"
    assert draft.subject == "Your new price list"
    assert "VP-10233" in draft.body and "from 24.90 to 26.39 EUR" in draft.body
    assert "We propose 25.6" in draft.body  # half of the increase: 24.90 + 1.49 / 2 = 25.645
    assert "[" not in draft.body  # no gap left empty
    assert draft.numbers_checked > 0


def test_a_number_slipped_into_the_text_stops_the_email(monkeypatch):
    slipped = GOOD_TEMPLATE.replace("Kind regards", "We expect an answer within 7 days.\n\nKind regards")
    monkeypatch.setattr(negotiate, "load_or_write_template", lambda supplier: slipped)
    findings, products, units = veloparts()
    with pytest.raises(NegotiationError, match="not in the calculations"):
        draft_email("VeloParts GmbH", findings, products, units)


def test_the_saved_demo_emails_pass_the_checks():
    findings, products, units = veloparts()
    draft = draft_email("VeloParts GmbH", findings, products, units)  # uses the saved text, no network
    assert "VP-10233" in draft.body
