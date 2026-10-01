"""Outcome of a restore: compare the verify_library report taken at backup time with the one
taken after the restore. Standard library only: restore.sh runs it with the Python of the
backend image, so the host needs no Python.

Usage: python compare_reports.py <verify-at-backup.json> <verify-after-restore.json>

Exit codes (those of restore.sh):
  0  restore succeeded: complete report, no problem
  3  data restored, with problems already present in the backup (and only those)
  1  restore failed: new problems, or an incomplete report
"""

import json
import sys

RESTORED, RESTORED_WITH_KNOWN_PROBLEMS, FAILED = 0, 3, 1

# The backup does not copy temporary files: their absence after the restore is expected.
NOT_COPIED = {"incomplete_abandoned"}


def key(problem: dict) -> tuple[str, str, str]:
    # The observed value (found size or checksum) is part of the identity: a file that was
    # already different at backup time and is different in another way now counts as new.
    # "found" is language-independent; reports written before it existed only have "detail".
    observed = problem["found"] if "found" in problem else problem.get("detail", "")
    return problem["kind"], problem["path"], observed


def describe(problem: dict) -> str:
    extra = [f"video {problem['video_id']}"] if problem.get("video_id") else []
    extra += [problem["detail"]] if problem.get("detail") else []
    return f"  - [{problem['kind']}] {problem['path']}" + (
        f"  ({'; '.join(extra)})" if extra else ""
    )


def compare(baseline: dict, restored: dict) -> tuple[int, list[str]]:
    lines = []
    if not restored.get("complete"):
        reason = restored.get("incomplete_reason") or "unknown reason"
        lines.append(f"RESTORE FAILED: the verification is incomplete ({reason}).")
        return FAILED, lines

    known = {key(p) for p in baseline.get("problems", []) if p["kind"] not in NOT_COPIED}
    if not baseline.get("complete"):
        known = set()  # An incomplete baseline proves nothing about what was already there.
    problems = restored.get("problems", [])
    new = [p for p in problems if key(p) not in known]
    old = [p for p in problems if key(p) in known]

    if new:
        lines.append(f"RESTORE FAILED: problems not present in the backup ({len(new)}):")
        lines += [describe(p) for p in new]
        if old:
            lines.append(f"Also, problems already present at backup time ({len(old)}):")
            lines += [describe(p) for p in old]
        return FAILED, lines
    if old:
        lines.append(
            f"DATA RESTORED, WITH PROBLEMS ALREADY PRESENT IN THE BACKUP ({len(old)}), "
            "not caused by the restore:"
        )
        lines += [describe(p) for p in old]
        return RESTORED_WITH_KNOWN_PROBLEMS, lines
    lines.append("RESTORE SUCCEEDED: the verification found no problem.")
    return RESTORED, lines


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return FAILED
    with open(argv[1], encoding="utf-8") as handle:
        baseline = json.load(handle)
    with open(argv[2], encoding="utf-8") as handle:
        restored = json.load(handle)
    code, lines = compare(baseline, restored)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
