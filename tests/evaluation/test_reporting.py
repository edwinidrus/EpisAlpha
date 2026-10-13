"""M6-T04 — the experiment report reads only the campaign's manifest and ledger.

Every campaign here is hand-written SYNTHETIC test data, not a measured experiment.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from episalpha.evaluation.reporting import DISCLAIMER, build_report, list_campaigns, render_markdown
from episalpha.evolution.candidates import Ledger

NOW = datetime(2026, 10, 13, 1, 0, tzinfo=UTC)
PROPOSAL = {
    "parent_harness_id": "harness.baseline",
    "hypothesis": "An explicit contradiction retrieval step improves recall.",
    "rationale": "Development failures.",
    "patch": [{"op": "replace", "path": "/contradiction_search", "value": True}],
}


def metrics(contradictions: tuple[int, int], completion: tuple[int, int]) -> dict[str, Any]:
    base = {"numerator": 1, "denominator": 1, "display": "1/1"}
    found = {
        "citation_correctness": base,
        "contradiction_recall": {
            "numerator": contradictions[0],
            "denominator": contradictions[1],
            "display": f"{contradictions[0]}/{contradictions[1]}",
        },
        "completion": {
            "numerator": completion[0],
            "denominator": completion[1],
            "display": f"{completion[0]}/{completion[1]}",
        },
    }
    return found


def trial(ledger: Ledger, phase: str, variant: str, case_id: str, **extra: Any) -> None:
    status = extra.pop("status", "scored")
    fields: dict[str, Any] = {
        "phase": phase,
        "variant": variant,
        "case_id": case_id,
        "execution_id": f"exec-{phase}-{variant}-{case_id}",
        "attempt": extra.pop("attempt", 1),
        "harness_id": "harness.baseline" if variant == "baseline" else "harness.cand-0123",
        "harness_hash": "h" * 64,
        "snapshot": "synthetic",
    }
    if status == "scored":
        fields |= {
            "run_id": f"run-{phase}-{variant}-{case_id}",
            "state": extra.pop("state", "RESEARCH_COMPLETED"),
            "model_requests": extra.pop("model_requests", 6),
            "score": {
                "metrics": extra.pop("metrics", metrics((1, 1), (1, 1))),
                "latency_seconds": extra.pop("latency", 12),
            },
        }
    ledger.append("trial", campaign_id="camp-a", now=NOW, status=status, **fields, **extra)


def campaign(root: Path, campaign_id: str = "camp-a", **manifest: Any) -> tuple[Path, Ledger]:
    directory = root / campaign_id
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "name": "demo-v1",
                "runtime": "fake",
                "model": "fixture",
                "rule": {"version": "1"},
                "partitions": {
                    "development": ["dev-a"],
                    "validation": ["val-a"],
                    "final": ["fin-a"],
                },
                "evaluator_hash": "e" * 64,
                "labels_hash": "l" * 64,
                "labels_reviewed": False,
                "limitations": ["one run per variant and case"],
                **manifest,
            }
        )
    )
    ledger = Ledger(directory / "ledger.jsonl")
    ledger.append("manifest_frozen", campaign_id=campaign_id, now=NOW, manifest_hash="m" * 64)
    return directory, ledger


def rejected_campaign(root: Path) -> Path:
    directory, ledger = campaign(root)
    trial(ledger, "development", "baseline", "dev-a")
    ledger.append(
        "proposal_accepted",
        campaign_id="camp-a",
        now=NOW,
        candidate_id="cand-0123",
        parent_harness_hash="p" * 64,
        proposal=PROPOSAL,
    )
    ledger.append(
        "materialized",
        campaign_id="camp-a",
        now=NOW,
        candidate_id="cand-0123",
        parent_harness_hash="p" * 64,
        child_harness_hash="c" * 64,
    )
    trial(ledger, "validation", "baseline", "val-a")
    trial(ledger, "validation", "challenger", "val-a", status="interrupted", error="worker lost")
    trial(
        ledger,
        "validation",
        "challenger",
        "val-a",
        attempt=2,
        state="FAILED",
        metrics=metrics((0, 1), (0, 1)),
    )
    gates = [
        {"gate": "1 zero violations", "passed": True, "detail": "baseline 0, challenger 0"},
        {"gate": "3 contradiction gain", "passed": False, "detail": "new 0, lost 1"},
    ]
    ledger.append("validation_gates", campaign_id="camp-a", now=NOW, gates=gates)
    ledger.append(
        "decision",
        campaign_id="camp-a",
        now=NOW,
        decision="baseline_retained",
        candidate_id="cand-0123",
        gates=gates,
        note="the baseline stays active",
    )
    return directory


def test_failed_and_interrupted_trials_are_in_the_report(tmp_path: Path) -> None:
    report = build_report(rejected_campaign(tmp_path))
    statuses = [(t.variant, t.status, t.state) for t in report.trials if t.phase == "validation"]
    assert ("challenger", "interrupted", None) in statuses
    assert ("challenger", "scored", "FAILED") in statuses
    text = render_markdown(report)
    assert "interrupted" in text and "worker lost" in text and "FAILED" in text


def test_a_rejected_candidate_is_a_complete_valid_result(tmp_path: Path) -> None:
    report = build_report(rejected_campaign(tmp_path))
    assert report.decision == "baseline_retained" and report.status == "decided"
    text = render_markdown(report)
    assert "complete, valid result" in text
    assert "improve" not in text.replace(PROPOSAL["hypothesis"], "")  # only the hypothesis says it
    assert "3 contradiction gain: FAIL (new 0, lost 1)" in text
    assert '"path": "/contradiction_search"' in text  # the candidate diff


def test_aggregates_are_numerators_and_denominators_from_the_ledger(tmp_path: Path) -> None:
    report = build_report(rejected_campaign(tmp_path))
    pooled = {(a.phase, a.variant): a for a in report.aggregates}
    challenger = pooled["validation", "challenger"]
    assert challenger.metrics["contradiction_recall"] == (0, 1)
    assert challenger.metrics["completion"] == (0, 1)
    assert challenger.trials == 2 and challenger.interrupted == 1
    assert challenger.model_requests == 6 and challenger.tokens == "unknown"
    assert challenger.cost == "unknown"
    assert pooled["validation", "baseline"].metrics["completion"] == (1, 1)


def test_the_disclaimer_is_always_present_and_there_is_no_score(tmp_path: Path) -> None:
    for directory in (rejected_campaign(tmp_path / "a"), campaign(tmp_path / "b")[0]):
        report = build_report(directory)
        assert render_markdown(report).startswith(f"> {DISCLAIMER}")
        names = {field.name for field in dataclasses.fields(report)}
        assert not names & {"score", "total", "weighted_score", "overall"}
        for aggregate in report.aggregates:
            assert "score" not in {f.name for f in dataclasses.fields(aggregate)}
    assert "alpha" not in render_markdown(build_report(rejected_campaign(tmp_path / "c"))).lower()


def test_an_undecided_campaign_says_so(tmp_path: Path) -> None:
    directory, ledger = campaign(tmp_path)
    ledger.append(
        "paused",
        campaign_id="camp-a",
        now=NOW,
        reason="cap",
        spent_today=6,
        cap=10,
        next_trial=["development", "baseline", "dev-a"],
    )
    report = build_report(directory)
    assert report.status == "paused" and report.decision is None
    assert "paused" in render_markdown(report)


def test_final_cases_are_marked_exposed_and_reuse_is_flagged(tmp_path: Path) -> None:
    first, ledger = campaign(tmp_path, "camp-a")
    trial(ledger, "final", "baseline", "fin-a")
    assert build_report(first).exposed_final_cases == ("fin-a",)
    later, _ = campaign(tmp_path, "camp-b", name="demo-v2")
    report = build_report(later)
    assert report.reuse_warnings == ("fin-a: final-check case already exposed in camp-a",)
    assert "already exposed" in render_markdown(report)


def test_campaigns_are_listed_newest_first(tmp_path: Path) -> None:
    campaign(tmp_path, "camp-a")
    campaign(tmp_path, "camp-b")
    # Same freezing time here, so the campaign ID breaks the tie, newest-named first.
    assert [c.name for c in list_campaigns(tmp_path)] == ["camp-b", "camp-a"]
    assert list_campaigns(tmp_path / "missing") == []


@pytest.mark.parametrize("decision", ["challenger_passed"])
def test_a_passed_challenger_is_never_called_promoted(tmp_path: Path, decision: str) -> None:
    directory, ledger = campaign(tmp_path)
    ledger.append(
        "decision",
        campaign_id="camp-a",
        now=NOW,
        decision=decision,
        candidate_id="cand-0123",
        gates=[],
        note="the baseline stays active",
    )
    text = render_markdown(build_report(directory))
    assert "promotion is an explicit owner action" in text
    assert "baseline stays active" in text
