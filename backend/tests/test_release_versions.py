"""The version of a release is written in several files (CONTRIBUTING.md, "Releasing"): they
must agree, or an installation would run images of another version than the one it shows."""

import json
import re
import tomllib

from django.conf import settings


def test_versions_agree():
    root = settings.PROJECT_DIR
    with open(root / "pyproject.toml", "rb") as file:
        version = tomllib.load(file)["project"]["version"]
    package = json.loads((root / "frontend" / "package.json").read_text())
    compose = (root / "docker-compose.yml").read_text()
    images = re.findall(r"image: ghcr\.io/rocchidavide/(vhs-[a-z]+):(\S+)", compose)

    assert package["version"] == version
    assert sorted(images) == [("vhs-backend", version), ("vhs-nginx", version)]
