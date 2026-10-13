"""Step 6: the email to a supplier, asking to reduce the increases. Nothing is sent from here.

Who writes what:
  - the SENTENCES are written by the Evolus email tool, which is told not to write any
    number and to leave marked gaps instead: [PRODUCT_LIST], [YEARLY_UNITS], ...
  - the NUMBERS are put into the gaps by this code, straight from the findings.

Two checks, both plain code:
  - the text that comes back from the tool must contain no digit and every gap exactly once;
  - in the finished email every number must be one of the numbers this code put there.
"""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from pydantic import BaseModel

from mg import config, llm
from mg.catalog import Product
from mg.schemas import Finding

EVOLUS_API = "https://api.evolus.ai/api/v1"
MAX_ATTEMPTS = 3
GAPS = ("[PRODUCT_LIST]", "[YEARLY_UNITS]", "[YEARLY_COST]", "[PROPOSAL]", "[SENDER]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


class NegotiationError(Exception):
    """The email could not be prepared in a way that passes the checks."""


class EmailDraft(BaseModel):
    """An email ready to be read by the person. It is never sent by this code."""

    supplier: str
    to: str
    subject: str
    body: str
    numbers_checked: int  # how many numbers are in the body, all found among the facts


def brief_for(supplier: str) -> str:
    """What the email tool is asked to write. It never sees a number."""
    return (
        f"Write an email from a small online bike shop ({config.SHOP_NAME}) to its supplier {supplier}. "
        "The supplier raised the prices of several products in its new price list. "
        "Ask firmly but politely to reduce the increases. "
        "IMPORTANT: do not write any number, price, percentage or quantity yourself. "
        "Write exactly [PRODUCT_LIST] on its own line where the list of products and increases goes, "
        "[YEARLY_UNITS] where the number of units we buy from them in a year goes, "
        "[YEARLY_COST] where the extra yearly cost goes, and [PROPOSAL] on its own line where our "
        "counter-proposal goes. Sign as [SENDER]. Keep it under 150 words."
    )


def draft_email(supplier: str, findings: list[Finding], products: dict[str, Product], units_per_month: dict[str, float]) -> EmailDraft:
    """The email to one supplier about all its increases. findings: the ones of that supplier that cost money."""
    if not findings:
        raise NegotiationError(f"no increase to negotiate with {supplier}")

    facts = build_facts(findings, products, units_per_month)
    template = load_or_write_template(supplier)
    subject, text = split_subject(template)

    body = text
    for gap, value in facts["gaps"].items():
        body = body.replace(gap, value)

    unknown = [number for number in NUMBER.findall(body) if number not in facts["allowed_numbers"]]
    if unknown:
        raise NegotiationError(f"the email contains numbers that are not in the calculations: {unknown}")

    return EmailDraft(
        supplier=supplier,
        to=config.SUPPLIER_EMAILS.get(supplier, ""),
        subject=subject,
        body=body,
        numbers_checked=len(NUMBER.findall(body)),
    )


def build_facts(findings: list[Finding], products: dict[str, Product], units_per_month: dict[str, float]) -> dict:
    """The text of every gap, built from the findings, and the list of every number written in it."""
    allowed = set()

    def n(value: float, decimals: int = 2) -> str:
        """Formats a number and remembers it as one this code wrote."""
        text = f"{value:.{decimals}f}"
        allowed.add(text)
        return text

    share = config.NEGOTIATION_SHARE
    rows, total_units, total_cost = [], 0.0, 0.0
    for finding in sorted(findings, key=lambda f: f.monthly_impact_eur, reverse=True):
        product = products[finding.sku]
        units_year = units_per_month[finding.sku] * 12
        proposed = finding.old_unit_cost_eur + (finding.new_unit_cost_eur - finding.old_unit_cost_eur) * (1 - share)
        total_units += units_year
        total_cost += finding.monthly_impact_eur * 12
        rows.append(
            f"- {product.supplier_code} ({product.name}): from {n(finding.old_unit_cost_eur)} to "
            f"{n(finding.new_unit_cost_eur)} EUR per unit, +{n(finding.pct_change, 1)}%. "
            f"We buy about {n(units_year, 0)} units a year. We propose {n(proposed)} EUR."
        )
    for finding in findings:
        product = products[finding.sku]
        allowed.update(NUMBER.findall(f"{product.supplier_code} {product.name}"))  # digits inside codes and names

    gaps = {
        "[PRODUCT_LIST]": "\n".join(rows),
        "[YEARLY_UNITS]": f"about {n(total_units, 0)} units",
        "[YEARLY_COST]": f"about {n(total_cost, 0)} EUR",
        "[PROPOSAL]": f"Apply {n(share * 100, 0)}% of each increase, at the prices proposed above, for the next {n(12, 0)} months.",
        "[SENDER]": config.SHOP_NAME,
    }
    return {"gaps": gaps, "allowed_numbers": allowed}


def split_subject(template: str) -> tuple[str, str]:
    """The tool starts its answer with a 'Subject: ...' line: split it from the text."""
    first, _, rest = template.partition("\n")
    if first.lower().startswith("subject:"):
        return first.split(":", 1)[1].strip(), rest.strip()
    return "Your new price list", template.strip()


def template_problem(template: str) -> str | None:
    """Why a text from the tool cannot be used. None if it is fine."""
    if re.search(r"\d", template):
        return "the tool wrote a number, which only the code may do"
    for gap in GAPS:
        if template.count(gap) != 1:
            return f"the gap {gap} must appear exactly once"
    return None


def load_or_write_template(supplier: str) -> str:
    """The saved text for this supplier, or a new one from the Evolus email tool (checked, then saved)."""
    saved_path = config.EMAIL_RESULTS_DIR / f"{supplier.lower().replace(' ', '-')}.json"
    if saved_path.exists():
        return json.loads(saved_path.read_text())["template"]

    problem = "not tried"
    for _ in range(MAX_ATTEMPTS):
        template = call_email_tool(brief_for(supplier))
        problem = template_problem(template)
        if problem is None:
            saved_path.parent.mkdir(parents=True, exist_ok=True)
            saved = {
                "supplier": supplier,
                "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "written_by": "Evolus AI tool 'email' (mode write, tone assertive)",
                "template": template,
            }
            saved_path.write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n")
            return template
    raise NegotiationError(f"no usable text after {MAX_ATTEMPTS} attempts: {problem}")


def call_email_tool(brief: str) -> str:
    """Asks the Evolus email tool to write the sentences. Returns its text."""
    llm.load_env()
    key = os.environ.get("EVOLUS_API_KEY", "")
    application_id = os.environ.get("EVOLUS_APPLICATION_ID", "")
    if not key or not application_id:
        raise NegotiationError("EVOLUS_API_KEY or EVOLUS_APPLICATION_ID is missing in .env")
    request = urllib.request.Request(
        f"{EVOLUS_API}/ai-tools/email/run",
        data=json.dumps({"text": brief, "options": {"mode": "write", "tone": "assertive"}}).encode(),
        method="POST",
        headers={"X-ApiKey": key, "X-Application-Id": application_id, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())["output"]
    except urllib.error.HTTPError as error:
        raise NegotiationError(f"Evolus answered HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
        raise NegotiationError(f"Evolus email tool failed: {error}") from error
