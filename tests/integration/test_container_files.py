"""Portable Docker (M0-T08, A15): what may enter an image, and line endings for Windows clones.

Static checks only: no Docker needed. The image build itself is verified in the task journal.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def context_includes(relative: str) -> bool:
    """Apply .dockerignore the way Docker does: the last matching pattern wins."""
    included = True
    for raw in (REPO / ".dockerignore").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line.lstrip("!").rstrip("/")
        if fnmatch(relative, pattern) or fnmatch(relative, pattern + "/*"):
            included = negated
    return included


def test_secrets_data_and_history_never_enter_the_build_context() -> None:
    for path in (
        ".env",
        ".env.local",
        ".episalpha/app.sqlite3",
        ".git/config",
        ".venv/bin/python",
        "config/demo.toml",
        "tests/conftest.py",
        "src/episalpha/__pycache__/cli.cpython-312.pyc",
    ):
        assert not context_includes(path), path


def test_the_code_the_image_needs_is_in_the_build_context() -> None:
    for path in (
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "src/episalpha/cli.py",
        "apps/streamlit_app.py",
        "harnesses/baseline/researcher.md",
        "eval_cases/demo/synthetic_corpus.json",
        "scripts/setup_worker.py",
        "worker/hermes_stage.py",
        "container/forwarder.py",
        "config/runtime.lock.json",
        "config/demo.example.toml",
        ".streamlit/config.toml",
    ):
        assert context_includes(path), path


def test_container_files_keep_lf_line_endings() -> None:
    rules = (REPO / ".gitattributes").read_text().splitlines()
    for pattern in ("Dockerfile", "*.sh", "*.py", "*.toml", "*.yaml"):
        assert f"{pattern} text eol=lf" in rules, pattern


def test_dockerfile_pins_bases_and_has_runtime_and_dev_targets() -> None:
    text = (REPO / "Dockerfile").read_text()
    assert "AS runtime" in text and "AS dev" in text
    for line in text.splitlines():
        if line.startswith("FROM ") and " AS " in line and "@sha256:" not in line:
            assert line.split()[1] in ("base", "runtime"), line  # stages, not registries
    assert "ENTRYPOINT" not in text
    assert "app-entrypoint" not in text
