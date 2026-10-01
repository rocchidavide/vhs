import json
import sys

from django.core.management.base import BaseCommand
from django.utils.translation import gettext, gettext_lazy, ngettext

from services.verification_service import Kind, verify_library

EXIT_OK, EXIT_PROBLEMS, EXIT_INCOMPLETE = 0, 1, 2

TITLES = {
    Kind.MAIN_MISSING: gettext_lazy("Missing main files"),
    Kind.SIZE_MISMATCH: gettext_lazy("Size different from the registered one"),
    Kind.CHECKSUM_MISMATCH: gettext_lazy("Checksum different from the registered one"),
    Kind.UNREFERENCED: gettext_lazy("Files not referenced in the database"),
    Kind.INCOMPLETE_ABANDONED: gettext_lazy("Abandoned .incomplete temporary files"),
    Kind.SYMLINK: gettext_lazy("Symbolic links (not followed)"),
}


class Command(BaseCommand):
    help = (
        "Compare the database with the library folder (read-only): missing main files, "
        "size or checksum mismatches, unreferenced files, abandoned temporary files."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--checksums",
            action="store_true",
            help="Also compare the SHA-256 of every main file (reads the whole library).",
        )
        parser.add_argument(
            "--json", action="store_true", dest="as_json", help="Machine-readable output."
        )

    def handle(self, *args, checksums, as_json, **options):
        report = verify_library(checksums=checksums)
        if as_json:
            self.stdout.write(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        else:
            self._print(report)
        if not report.complete:
            sys.exit(EXIT_INCOMPLETE)
        if report.problems:
            sys.exit(EXIT_PROBLEMS)

    def _print(self, report):
        out = self.stdout.write
        checksums = gettext("yes") if report.checksums else gettext("no (use --checksums)")
        rows = [
            (gettext("Library"), report.root),
            (gettext("Checksums"), checksums),
            (gettext("Videos checked"), report.videos_checked),
            (gettext("Files scanned"), report.files_scanned),
        ]
        width = max(len(label) for label, _value in rows) + 2
        for label, value in rows:
            out(f"{label + ':':<{width}}{value}")
        for kind, title in TITLES.items():
            items = [finding for finding in report.problems if finding.kind == kind]
            if not items:
                continue
            out("")
            out(f"{title} ({len(items)}):")
            for finding in items:
                extra = (
                    [gettext("video {id}").format(id=finding.video_id)] if finding.video_id else []
                )
                extra += [finding.detail] if finding.detail else []
                out(f"  - {finding.path}" + (f"  ({'; '.join(extra)})" if extra else ""))
        if report.active:
            out("")
            out(gettext("In progress, not problems ({count}):").format(count=len(report.active)))
            for finding in report.active:
                out(f"  - {finding.path}  ({finding.detail})")
        if report.errors:
            out("")
            out(gettext("Read errors ({count}):").format(count=len(report.errors)))
            for error in report.errors:
                out(f"  - {error}")
        out("")
        if not report.complete:
            reason = report.incomplete_reason.rstrip(".")
            out(self.style.ERROR(gettext("INCOMPLETE CHECK: {reason}.").format(reason=reason)))
            out(gettext("The report does not guarantee that the library is in order."))
        elif report.problems:
            found = len(report.problems)
            message = ngettext(
                "{count} problem found. Nothing was changed.",
                "{count} problems found. Nothing was changed.",
                found,
            ).format(count=found)
            out(self.style.WARNING(message))
        else:
            out(self.style.SUCCESS(gettext("No problem found.")))
