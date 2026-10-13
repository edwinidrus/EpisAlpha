"""M5-T03 — the one-way, byte-stable Obsidian vault for one run (acceptance row A15).

Rendering and writing are tested over the SYNTHETIC :class:`RunKnowledge` fixture; scope and the
CLI against real fake-runtime runs. Fake runs are labelled fixtures, never live evidence.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fixtures.run_knowledge import RUN, SCRIPT, knowledge
from fixtures.synthetic_knowledge import REPORTED_CLAIM
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import ValidationError
from typer.testing import CliRunner

from episalpha.cli import app
from episalpha.contracts.errors import EpisAlphaError
from episalpha.contracts.research import RETROSPECTIVE_NOTICE, RunState
from episalpha.knowledge.export_obsidian import (
    export_knowledge,
    export_run,
    render_notes,
    safe_name,
)
from episalpha.knowledge.query import RunKnowledge
from episalpha.observability import configure_tracing, shutdown_tracing
from episalpha.research import services
from episalpha.settings import Settings

LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
FENCE = re.compile(r"^(`{3,})[^\n]*\n.*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)
BASE = f"generated/{RUN}"
HOSTILE = "Revenue ``` [[evil-note]] <script>alert(1)</script> ![[embed]] #tag"


def outside_fences(text: str) -> str:
    return FENCE.sub("", text)


def links(text: str) -> list[str]:
    return LINK.findall(outside_fences(text))


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def hostile() -> RunKnowledge:
    base = knowledge()
    claim = REPORTED_CLAIM.model_copy(update={"statement": HOSTILE, "attribution": HOSTILE})
    return dataclasses.replace(base, claims={**base.claims, claim.claim_id: claim})


# --- rendering ---------------------------------------------------------------------------------


def test_one_note_per_record_named_by_stable_id_only() -> None:
    notes = render_notes(knowledge(), BASE)
    assert sorted(notes) == sorted(
        [
            f"thesis/{RUN}.thesis.md",
            "claims/synthetic-claim.revenue.md",
            "claims/synthetic-claim.demand.md",
            "claims/synthetic-claim.prior.md",
            f"claims/{RUN}.d1.md",
            "hypotheses/synthetic-hypothesis.demand.md",
            "spans/synthetic-span.revenue.md",
            "spans/synthetic-span.demand.md",
            "spans/synthetic-span.prior.md",
            "documents/synthetic-doc.v1.md",
            "documents/synthetic-doc.copy.md",
            f"relations/{RUN}.r1.md",
        ]
    )
    assert all(not text.count("\r") and text.endswith("\n") for text in notes.values())


def test_front_matter_is_flat_sorted_and_quoted() -> None:
    for name, text in render_notes(knowledge(), BASE).items():
        assert text.startswith("---\n"), name
        block = text.split("---\n")[1]
        keys = []
        for line in block.splitlines():
            if line.startswith("  - "):
                assert line[4] == '"', (name, line)  # list items are quoted strings
                continue
            key, _, value = line.partition(": ")
            keys.append(key.rstrip(":"))
            assert re.fullmatch(r"[a-z_]+", keys[-1]), (name, line)
            assert (
                value == ""
                and line.endswith(":")
                or re.fullmatch(r'".*"|null|true|false|-?\d+|\[\]', value)
            ), (name, line)
        assert keys == sorted(keys), name
        assert {"id", "kind", "run"} <= set(keys), name


def test_claim_note_carries_status_chain_and_resolvable_links() -> None:
    notes = render_notes(knowledge(), BASE)
    derived = notes[f"claims/{RUN}.d1.md"]
    assert 'epistemic_status: "derived"' in derived
    assert 'status: "unreviewed"' in derived
    assert "pct_change@1" in derived and "0.03" in derived  # A8: recomputed, not asserted
    assert "matches the claimed value" in derived
    assert f"[[{BASE}/claims/synthetic-claim.prior.md|synthetic-claim.prior]]" in derived
    demand = notes["claims/synthetic-claim.demand.md"]
    assert 'status: "unsupported"' in demand
    revenue = notes["claims/synthetic-claim.revenue.md"]
    assert f"[[{BASE}/claims/synthetic-claim.demand.md|synthetic-claim.demand]]" in revenue


def test_thesis_note_shows_limitations() -> None:
    thesis = render_notes(knowledge(), BASE)[f"thesis/{RUN}.thesis.md"]
    assert "[FIXTURE] fake runtime" in thesis
    assert RETROSPECTIVE_NOTICE in thesis
    assert 'runtime: "fake"' in thesis
    assert "Common lineage" in render_notes(knowledge(), BASE)["documents/synthetic-doc.copy.md"]


def test_untrusted_text_is_fenced_and_inert() -> None:
    notes = render_notes(hostile(), BASE)
    claim = notes["claims/synthetic-claim.revenue.md"]
    assert HOSTILE in claim  # kept verbatim, inside a fence longer than any backtick run
    assert "<script>" not in outside_fences(claim)
    assert "evil-note" not in " ".join(links(claim)) and "![[" not in outside_fences(claim)
    span = notes["spans/synthetic-span.prior.md"]
    assert SCRIPT in span and "<script>" not in outside_fences(span)
    front = claim.split("---\n")[1]
    assert "evil" not in front and "script" not in front  # no model text in properties


def test_a_run_without_thesis_exports_its_records_with_honest_notices(tmp_path: Path) -> None:
    rejected = dataclasses.replace(
        knowledge(), thesis=None, persisted=False, state=RunState.REJECTED
    )
    result = export_knowledge(rejected, tmp_path / "vault")
    names = {p.relative_to(result.destination).as_posix() for p in result.destination.rglob("*.md")}
    assert not any(name.startswith("thesis/") for name in names) and f"claims/{RUN}.d1.md" in names
    note = (result.destination / "claims" / f"{RUN}.d1.md").read_text()
    assert "never persisted" in note
    for path in result.destination.rglob("*.md"):
        assert all((tmp_path / "vault" / t).is_file() for t in links(path.read_text()))


# --- writing -----------------------------------------------------------------------------------


def test_every_generated_link_resolves(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    result = export_knowledge(knowledge(), vault)
    found = 0
    for path in result.destination.rglob("*.md"):
        for target in links(path.read_text()):
            found += 1
            assert target.endswith(".md"), target
            assert (vault / target).is_file(), (path.name, target)
    assert found > 20


def test_repeated_export_is_byte_stable(tmp_path: Path) -> None:
    first = export_knowledge(knowledge(), tmp_path / "vault")
    before = tree(tmp_path / "vault")
    second = export_knowledge(knowledge(), tmp_path / "vault")
    assert tree(tmp_path / "vault") == before
    assert first.manifest_hash == second.manifest_hash and second.conflicts == ()
    elsewhere = export_knowledge(knowledge(), tmp_path / "other")
    assert tree(elsewhere.destination) == tree(first.destination)  # no clock, no absolute path
    manifest = json.loads((first.destination / "manifest.json").read_text())
    assert set(manifest["files"]) == set(render_notes(knowledge(), BASE))
    assert manifest["run_id"] == RUN and manifest["destination"] == BASE


def test_ids_cannot_traverse_and_nothing_escapes_the_vault(tmp_path: Path) -> None:
    for bad in ("../evil", "a/b", "..", "", "/etc/passwd", "UPPER", "x\\y"):
        with pytest.raises(ValueError):
            safe_name(bad)
    with pytest.raises(ValidationError):
        REPORTED_CLAIM.model_copy(update={"claim_id": "../evil"}).model_validate(
            {**REPORTED_CLAIM.model_dump(), "claim_id": "../evil"}
        )
    vault = (tmp_path / "vault").resolve()
    result = export_knowledge(knowledge(), vault)
    for path in result.destination.rglob("*"):
        assert path.resolve().is_relative_to(vault)


def test_a_symlink_out_of_the_vault_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "generated").symlink_to(outside, target_is_directory=True)
    with pytest.raises(EpisAlphaError):
        export_knowledge(knowledge(), vault)
    assert list(outside.iterdir()) == []


def test_user_annotations_are_never_touched(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    export_knowledge(knowledge(), vault)
    assert (vault / "annotations").is_dir()
    note = vault / "annotations" / "my-thoughts.md"
    note.write_text("my own words [[generated/whatever]]\n")
    stat = note.stat()
    export_knowledge(knowledge(), vault)
    assert note.read_text() == "my own words [[generated/whatever]]\n"
    assert note.stat().st_mtime_ns == stat.st_mtime_ns
    assert sorted(p.name for p in (vault / "annotations").iterdir()) == ["my-thoughts.md"]


def test_an_edited_generated_note_moves_the_export_never_overwrites(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    first = export_knowledge(knowledge(), vault)
    edited = first.destination / "claims" / "synthetic-claim.revenue.md"
    edited.write_text(edited.read_text() + "\nmy edit\n")
    mine = edited.read_bytes()
    second = export_knowledge(knowledge(), vault)
    assert second.conflicts == (f"{RUN}/claims/synthetic-claim.revenue.md",)
    assert second.destination == vault / "generated" / f"{RUN}.2"
    assert edited.read_bytes() == mine
    for path in second.destination.rglob("*.md"):
        for target in links(path.read_text()):
            assert target.startswith(f"generated/{RUN}.2/") and (vault / target).is_file()
    third = export_knowledge(knowledge(), vault)  # idempotent: reuses the clean .2
    assert third.destination == second.destination and third.manifest_hash == second.manifest_hash
    assert not (vault / "generated" / f"{RUN}.3").exists()


def test_an_interrupted_export_is_not_mistaken_for_an_edit(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    first = export_knowledge(knowledge(), vault)
    (first.destination / "manifest.json").unlink()  # crash before the manifest was written
    again = export_knowledge(knowledge(), vault)
    assert again.destination == first.destination and again.conflicts == ()


def test_a_tampered_manifest_cannot_delete_files_outside_its_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    first = export_knowledge(knowledge(), vault)
    mine = vault / "annotations" / "mine.md"
    mine.write_text("keep me\n")
    manifest = json.loads((first.destination / "manifest.json").read_text())
    digest = hashlib.sha256(b"keep me\n").hexdigest()
    manifest["files"]["../../annotations/mine.md"] = digest  # names a matching owner file
    (first.destination / "manifest.json").write_text(json.dumps(manifest))
    export_knowledge(knowledge(), vault)
    assert mine.read_text() == "keep me\n"


def test_a_stale_generated_note_is_removed_only_when_unedited(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    first = export_knowledge(knowledge(), vault)
    old = first.destination / "claims" / "synthetic-claim.gone.md"
    old.write_text("an earlier export's note\n")
    manifest = json.loads((first.destination / "manifest.json").read_text())
    manifest["files"]["claims/synthetic-claim.gone.md"] = hashlib.sha256(
        old.read_bytes()
    ).hexdigest()
    (first.destination / "manifest.json").write_text(json.dumps(manifest))
    export_knowledge(knowledge(), vault)
    assert not old.exists()


def test_a_symlinked_manifest_moves_the_export(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    first = export_knowledge(knowledge(), vault)
    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}")
    (first.destination / "manifest.json").unlink()
    (first.destination / "manifest.json").symlink_to(outside)
    second = export_knowledge(knowledge(), vault)
    assert second.conflicts == (f"{RUN}/manifest.json",)
    assert outside.read_text() == "{}"


# --- observability -----------------------------------------------------------------------------


@pytest.fixture
def spans(tmp_path: Path) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    settings = Settings.model_validate(
        {"paths": {"project_root": tmp_path, "data_root": tmp_path / "data"}}
    )
    configure_tracing(settings, extra_exporter=exporter)
    yield exporter
    shutdown_tracing()


def test_export_emits_one_metadata_only_span(tmp_path: Path, spans: InMemorySpanExporter) -> None:
    result = export_knowledge(hostile(), tmp_path / "vault")
    (span,) = [s for s in spans.get_finished_spans() if s.name == "export.obsidian"]
    attributes = dict(span.attributes or {})
    assert attributes["episalpha.run_id"] == RUN
    assert attributes["episalpha.files"] == result.files == 13  # 12 notes + manifest
    assert attributes["episalpha.manifest_hash"] == result.manifest_hash
    assert attributes["episalpha.conflicts"] == 0
    shown = " ".join(str(value) for value in attributes.values())
    assert "script" not in shown and "Revenue" not in shown and str(tmp_path) not in shown


# --- real runs ---------------------------------------------------------------------------------


def test_only_the_selected_run_is_exported(
    workbench: services.Workbench, fake_run: Callable[[str], str], tmp_path: Path
) -> None:
    first, second = fake_run("one"), fake_run("two")
    vault = tmp_path / "vault"
    result = export_run(workbench.repo, workbench.runs_dir, first, vault)
    assert [p.name for p in (vault / "generated").iterdir()] == [first]
    texts = "\n".join(p.read_text() for p in result.destination.rglob("*") if p.is_file())
    assert second not in texts and first in texts
    assert "Fourth quarter revenue reached EUR 412.0 million." in texts


def test_an_unfinished_run_cannot_be_exported(
    workbench: services.Workbench, tmp_path: Path
) -> None:
    with pytest.raises(EpisAlphaError):
        export_run(workbench.repo, workbench.runs_dir, "run-000000000000", tmp_path / "vault")


def test_cli_exports_and_refuses_unknown_runs(
    config: Path, fake_run: Callable[[str], str], tmp_path: Path
) -> None:
    run_id = fake_run("cli")
    vault = tmp_path / "vault"
    arguments = ["--config", str(config), "export", "obsidian", "--run", run_id]
    result = CliRunner().invoke(app, [*arguments, "--output", str(vault)])
    assert result.exit_code == 0, result.output
    assert "[FIXTURE]" in result.output
    assert f"generated/{run_id}" in result.output and "conflicts: 0" in result.output
    repeat = CliRunner().invoke(app, [*arguments, "--output", str(vault)])
    assert repeat.exit_code == 0 and repeat.output == result.output
    unknown = ["--config", str(config), "export", "obsidian", "--run", "run-000000000000"]
    refused = CliRunner().invoke(app, [*unknown, "--output", str(vault)])
    assert refused.exit_code == 2
    blocker = tmp_path / "a-file"
    blocker.write_text("not a directory")
    unwritable = CliRunner().invoke(app, [*arguments, "--output", str(blocker / "vault")])
    assert unwritable.exit_code == 2 and "cannot write the vault" in unwritable.output
