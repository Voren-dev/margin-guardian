"""mg.report: the chain for one demo supplier, as used by the Telegram bot."""
from mg.report import DEMO_SUPPLIERS, SUPPLIERS_DIR, identify, run_supplier


def test_the_three_reports_add_up_to_the_whole_demo():
    reports = [run_supplier(key) for key in DEMO_SUPPLIERS]
    assert sum(len(report.findings) for report in reports) == 19
    assert sum(len(report.hidden()) for report in reports) == 7
    assert round(sum(report.total("absorb") for report in reports)) == -9155


def test_the_pack_trick_is_found_in_trailgear():
    report = run_supplier("trailgear")
    assert [f.kind for f in report.hidden()] == ["pack_change"]


def test_a_demo_file_is_recognised_and_anything_else_is_not():
    for key, (_, _, new_name) in DEMO_SUPPLIERS.items():
        assert identify((SUPPLIERS_DIR / "new" / new_name).read_bytes()) == key
    assert identify(b"not a price list") is None
