"""Portable Docker (M0-T08, A15): what may enter an image, and line endings for Windows clones.

Static checks only: no Docker needed. The image build itself is verified in the task journal.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def context_includes(relative: str) -> bool:
    """Match path segments and their parents; the last matching Docker pattern wins."""
    included = True
    parts = relative.split("/")
    for raw in (REPO / ".dockerignore").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line.lstrip("!").rstrip("/")
        # shortcut: rooted globs and leading **/ only; expand if the allowlist adds other syntax.
        if pattern.startswith("**/"):
            matches = any(fnmatch(part, pattern[3:]) for part in parts)
        else:
            patterns = pattern.split("/")
            matches = len(parts) >= len(patterns) and all(
                fnmatch(part, glob) for part, glob in zip(parts, patterns, strict=False)
            )
        if matches:
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
        "tests/fixtures/connectors/sample.json",
        "tests/integration/test_package.py",
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
        "tests/fixtures/runtime/completion.json",
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
    assert "RUN uv sync --no-dev\n" in text
    assert "RUN uv sync --all-groups\n" in text
    assert "COPY tests/fixtures/runtime ./tests/fixtures/runtime" in text
