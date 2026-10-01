"""Completed downloads recorded only the size of their last stream (usually the audio).

Corrects only the attempts provably tied to the current file: completed with a transfer
(not recovered_existing), and whose checksum and path are still the video's. The file
then holds exactly the bytes that attempt produced, so its size is the attempt's size.
Every other row keeps its historical value.
"""

from django.db import migrations
from django.db.models import F


def provable(Download):
    return Download.objects.filter(
        status="completed",
        recovered_existing=False,
        video__file_size__isnull=False,
        checksum_sha256=F("video__checksum_sha256"),
        target_path=F("video__file_path"),
    ).exclude(checksum_sha256="")


def correct_sizes(apps, schema_editor):
    Download = apps.get_model("core", "Download")
    for download in provable(Download).select_related("video"):
        size = download.video.file_size
        Download.objects.filter(pk=download.pk).update(total_bytes=size, downloaded_bytes=size)


class Migration(migrations.Migration):
    dependencies = [("core", "0007_i18n_playback_issues")]

    # The wrong values are not kept: there is nothing to restore them to.
    operations = [migrations.RunPython(correct_sizes, migrations.RunPython.noop)]
