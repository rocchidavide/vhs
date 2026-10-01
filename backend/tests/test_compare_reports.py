"""scripts/compare_reports.py: outcome of a restore (0 ok, 3 known problems, 1 failed)."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compare_reports.py"
spec = importlib.util.spec_from_file_location("compare_reports", SCRIPT)
compare_reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_reports)


def report(*problems, complete=True, reason=""):
    return {"complete": complete, "incomplete_reason": reason, "problems": list(problems)}


def problem(kind, path, detail="", video_id=None):
    return {"kind": kind, "path": path, "detail": detail, "video_id": video_id}


STRAY = problem("unreferenced", "youtube/stray.mp4")
MISSING = problem("main_missing", "youtube/a [a].mp4", video_id=3)


def test_clean_restore_succeeds():
    code, lines = compare_reports.compare(report(), report())
    assert code == 0
    assert lines == ["RESTORE SUCCEEDED: the verification found no problem."]


def test_only_problems_already_in_the_backup():
    code, lines = compare_reports.compare(report(STRAY), report(STRAY))
    assert code == 3
    assert lines[0].startswith("DATA RESTORED, WITH PROBLEMS ALREADY PRESENT IN THE BACKUP (1)")
    assert "youtube/stray.mp4" in lines[1]


def test_a_new_problem_means_the_restore_failed():
    code, lines = compare_reports.compare(report(STRAY), report(STRAY, MISSING))
    assert code == 1
    assert lines[0] == "RESTORE FAILED: problems not present in the backup (1):"
    assert "youtube/a [a].mp4" in lines[1] and "video 3" in lines[1]
    assert any("already present" in line for line in lines)


def test_an_incomplete_verification_is_a_failure():
    code, lines = compare_reports.compare(report(), report(complete=False, reason="3 read errors"))
    assert code == 1
    assert "incomplete (3 read errors)" in lines[0]


def test_abandoned_temporaries_of_the_backup_do_not_count():
    baseline = report(problem("incomplete_abandoned", ".incomplete/7"))
    assert compare_reports.compare(baseline, report())[0] == 0
    # ...and cannot hide a problem with the same path after the restore.
    restored = report(problem("unreferenced", ".incomplete/7"))
    assert compare_reports.compare(baseline, restored)[0] == 1


@pytest.mark.parametrize(
    ("kind", "before", "after"),
    [
        ("size_mismatch", "registrati 10 byte, trovati 12", "registrati 10 byte, trovati 9"),
        ("checksum_mismatch", "found aaa", "found bbb"),
    ],
)
def test_same_file_different_in_another_way_is_new(kind, before, after):
    path = "youtube/a [a].mp4"
    same = compare_reports.compare(
        report(problem(kind, path, before)), report(problem(kind, path, before))
    )
    other = compare_reports.compare(
        report(problem(kind, path, before)), report(problem(kind, path, after))
    )
    assert same[0] == 3
    assert other[0] == 1


def test_the_observed_value_is_compared_without_the_wording():
    # Same problem, detail written in another language: "found" decides.
    before = dict(problem("size_mismatch", "youtube/a [a].mp4", "registrati 10 byte, trovati 12"))
    after = dict(problem("size_mismatch", "youtube/a [a].mp4", "10 bytes registered, 12 found"))
    before["found"] = after["found"] = "12"
    assert compare_reports.compare(report(before), report(after))[0] == 3
    after["found"] = "9"
    assert compare_reports.compare(report(before), report(after))[0] == 1


def test_an_incomplete_baseline_proves_nothing():
    baseline = report(STRAY, complete=False, reason="x")
    assert compare_reports.compare(baseline, report(STRAY))[0] == 1


def test_command_line(tmp_path, capsys):
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    before.write_text(json.dumps(report(STRAY)))
    after.write_text(json.dumps(report(STRAY)))

    assert compare_reports.main(["compare_reports.py", str(before), str(after)]) == 3
    assert "ALREADY PRESENT" in capsys.readouterr().out
