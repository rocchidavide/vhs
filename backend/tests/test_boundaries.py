"""The engine is pure Python: it must not depend on Django or VHS models (§5.5)."""

import ast
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
FORBIDDEN_IN_ENGINE = {"django", "ninja", "django_q", "core", "api", "services", "tasks"}


def imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize(
    "path",
    sorted((BACKEND_DIR / "engine").rglob("*.py")),
    ids=lambda path: str(path.relative_to(BACKEND_DIR)),
)
def test_engine_does_not_import_django(path):
    assert not imported_roots(path) & FORBIDDEN_IN_ENGINE
