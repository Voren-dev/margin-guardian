"""mg.review: the reviewer is code, not a model. Finding -> AuditResult."""
from conftest import all_findings

def front_light():
    return next(f for f in all_findings() if f.sku == "RL-1001")


def test_an_untouched_finding_passes():
    from mg.review import audit

    assert audit(front_light()).passed


def test_a_finding_without_sources_is_rejected():
    from mg.review import audit

    finding = front_light().model_copy(update={"sources": []})
    result = audit(finding)
    assert not result.passed
    assert result.reason


def test_a_finding_with_a_changed_number_is_rejected():
    from mg.review import audit

    finding = front_light().model_copy(update={"new_unit_cost_eur": 25.39})
    assert not audit(finding).passed


def test_every_finding_of_the_demo_passes():
    from mg.review import audit

    results = [audit(finding) for finding in all_findings()]
    assert len(results) == 19
    assert all(result.passed for result in results), [r.reason for r in results if not r.passed]


def test_the_pack_trap_is_checked_per_unit():
    from mg.review import cost_comes_from_row

    row = "TG-B4001 | Disc Pads Organic, pack of 2 pairs | Brakes | 2 | 5.1 | 9.69"
    assert cost_comes_from_row(2.9835, row)  # 5.10 GBP / 2 * 1.17
    assert not cost_comes_from_row(2.50, row)


def test_a_surcharge_not_written_in_the_footnote_is_rejected():
    from mg.review import audit

    surcharge = next(f for f in all_findings() if f.kind == "surcharge_note")
    assert audit(surcharge).passed
    inflated = surcharge.model_copy(
        update={"pct_change": 6.0, "new_unit_cost_eur": round(surcharge.old_unit_cost_eur * 1.06, 4)}
    )
    result = audit(inflated)
    assert not result.passed and "not written in the footnote" in result.reason


def test_a_wrong_percentage_is_rejected():
    from mg.review import audit

    finding = front_light().model_copy(update={"pct_change": 3.0})
    result = audit(finding)
    assert not result.passed and "does not agree" in result.reason
