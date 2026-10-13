"""mg.review: the reviewer is code, not a model. Finding -> AuditResult."""
import pytest

from conftest import all_findings

pytestmark = pytest.mark.xfail(reason="mg.review is not built yet")


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
