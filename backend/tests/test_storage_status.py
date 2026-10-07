from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def status(settings, tmp_path, host_library):
    settings.VHS_MEDIA_ROOT = tmp_path
    settings.VHS_HOST_LIBRARY = host_library
    out = StringIO()
    call_command("storage_status", stdout=out)
    return out.getvalue()


def test_shows_the_folder_as_the_server_knows_it(settings, tmp_path):
    output = status(settings, tmp_path, "/srv/vhs/library")

    assert f"/srv/vhs/library on the server ({tmp_path} inside the containers)" in output


def test_without_docker_shows_the_folder_only(settings, tmp_path):
    output = status(settings, tmp_path, "")

    assert output.splitlines()[0].split() == ["Folder:", str(tmp_path)]
    assert "on the server" not in output
