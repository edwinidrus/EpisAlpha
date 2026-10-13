"""M6-T02 — the one-mutation candidate surface and its append-only ledger (plan section 12.2).

Proposals are data. Nothing here executes anything a proposal contains (M6 article 4).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from episalpha.contracts.errors import EpisAlphaError
from episalpha.evolution.candidates import (
    CandidateRejected,
    Ledger,
    abandon,
    materialize,
    propose,
    validate_proposal,
)
from episalpha.runtime.hermes import load_harness

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "candidates"
NOW = datetime(2026, 10, 12, 21, 0, tzinfo=UTC)
REJECTED = [
    ("empty", "exactly one operation"),
    ("duplicate", "exactly one operation"),
    ("multiple", "exactly one operation"),
    ("budget", "/contradiction_search"),
    ("traversal", "/contradiction_search"),
    ("add-op", "replace"),
    ("non-boolean", "boolean"),
    ("unchanged", "already"),
]


def raw(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / f"{name}.json").read_text())  # type: ignore[no-any-return]


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode() + path.read_bytes())
    return digest.hexdigest()


@pytest.fixture
def baseline(tmp_path: Path) -> Path:
    copy = tmp_path / "harnesses" / "baseline"
    shutil.copytree(REPO / "harnesses" / "baseline", copy)
    return copy


def test_the_baseline_is_the_plan_configuration() -> None:
    config = json.loads((REPO / "harnesses" / "baseline" / "config.json").read_text())
    assert config == {"schema_version": "1", "contradiction_search": False}


def test_the_allowed_flag_change_passes(baseline: Path) -> None:
    candidate = validate_proposal(raw("allowed"), load_harness(baseline))
    assert candidate.config == {"schema_version": "1", "contradiction_search": True}
    assert candidate.parent_harness_hash == load_harness(baseline).harness_hash
    assert candidate.candidate_id.startswith("cand-")
    # The same proposal on the same parent is the same candidate.
    assert validate_proposal(raw("allowed"), load_harness(baseline)) == candidate


@pytest.mark.parametrize(("name", "reason"), REJECTED)
def test_every_other_patch_is_rejected_and_recorded(
    baseline: Path, tmp_path: Path, name: str, reason: str
) -> None:
    ledger = Ledger(tmp_path / "candidates" / "ledger.jsonl")
    with pytest.raises(CandidateRejected, match=reason):
        propose(raw(name), baseline, ledger, campaign_id="demo-v1-fake", now=NOW)
    (record,) = ledger.records()
    assert record["kind"] == "proposal_rejected"
    assert reason in record["reason"]
    assert record["campaign_id"] == "demo-v1-fake"
    assert record["proposal"] == raw(name)  # the rejected proposal itself is kept


def test_a_proposal_for_another_parent_is_rejected(baseline: Path) -> None:
    other = {**raw("allowed"), "parent_harness_id": "harness.someone-else"}
    with pytest.raises(CandidateRejected, match="parent"):
        validate_proposal(other, load_harness(baseline))


def test_unknown_fields_and_missing_hypothesis_are_rejected(baseline: Path) -> None:
    with pytest.raises(CandidateRejected):
        validate_proposal({**raw("allowed"), "code": "import os"}, load_harness(baseline))
    with pytest.raises(CandidateRejected):
        validate_proposal({**raw("allowed"), "hypothesis": ""}, load_harness(baseline))


def test_materialize_copies_and_patches_without_touching_the_baseline(
    baseline: Path, tmp_path: Path
) -> None:
    before = tree_hash(baseline)
    ledger = Ledger(tmp_path / "candidates" / "ledger.jsonl")
    candidate = propose(raw("allowed"), baseline, ledger, campaign_id="demo-v1-fake", now=NOW)
    made = materialize(candidate, baseline, tmp_path / "candidates", ledger, now=NOW)
    assert tree_hash(baseline) == before  # the active harness never changes
    assert made.root == tmp_path / "candidates" / candidate.candidate_id
    child = load_harness(made.root)
    assert child.config["contradiction_search"] is True
    assert child.harness_hash == made.child_hash != made.parent_hash
    assert made.parent_hash == load_harness(baseline).harness_hash
    kinds = [record["kind"] for record in ledger.records()]
    assert kinds == ["proposal_accepted", "materialized"]
    assert ledger.records()[-1]["child_harness_hash"] == made.child_hash
    # Materializing again is idempotent; a tampered candidate directory is refused.
    assert materialize(candidate, baseline, tmp_path / "candidates", ledger, now=NOW) == made
    (made.root / "critic.md").write_text("tampered")
    with pytest.raises(EpisAlphaError, match="differs"):
        materialize(candidate, baseline, tmp_path / "candidates", ledger, now=NOW)


def test_materialize_never_writes_inside_the_baseline(baseline: Path, tmp_path: Path) -> None:
    candidate = validate_proposal(raw("allowed"), load_harness(baseline))
    ledger = Ledger(tmp_path / "ledger.jsonl")
    with pytest.raises(EpisAlphaError, match="baseline"):
        materialize(candidate, baseline, baseline / "candidates", ledger, now=NOW)


def test_abandoned_proposals_stay_in_the_ledger(baseline: Path, tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    candidate = propose(raw("allowed"), baseline, ledger, campaign_id="demo-v1-fake", now=NOW)
    abandon(ledger, candidate.candidate_id, "interrupted before any trial", "demo-v1-fake", now=NOW)
    assert [r["kind"] for r in ledger.records()] == ["proposal_accepted", "abandoned"]
    assert ledger.records()[-1]["reason"] == "interrupted before any trial"


def test_the_ledger_is_append_only(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append("trial", campaign_id="c", now=NOW, case_id="a")
    first = (tmp_path / "ledger.jsonl").read_bytes()
    ledger.append("trial", campaign_id="c", now=NOW, case_id="b")
    assert (tmp_path / "ledger.jsonl").read_bytes().startswith(first)
    assert [r["case_id"] for r in ledger.records()] == ["a", "b"]
    assert ledger.records()[0]["at"] == NOW.isoformat()
