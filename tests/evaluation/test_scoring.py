"""M6-T01 — labelled cases and deterministic metrics (plan section 12.3).

The outcomes here are hand-built SYNTHETIC runs over the synthetic corpus, never research. The
last test scores one real fake-runtime run end to end; it is a labelled fixture as well.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fixtures.synthetic_knowledge import (
    CONTRADICTING_CLAIM,
    REPORTED_CLAIM,
    SYNTHETIC_DOCUMENT,
)

from episalpha.contracts.errors import EpisAlphaError
from episalpha.contracts.knowledge import (
    AvailabilityBasis,
    Claim,
    EpistemicStatus,
    Relation,
    RelationPredicate,
)
from episalpha.contracts.research import RunState, RuntimeMode
from episalpha.evaluation import cases as cases_module
from episalpha.evaluation import scoring
from episalpha.evaluation.cases import (
    EvalCase,
    ExpectedContradiction,
    ExpectedFact,
    Labels,
    check_partitions,
    evaluator_hash,
    labels_hash,
    load_cases,
    load_labels,
)
from episalpha.evaluation.scoring import RunOutcome, pool, score_case
from episalpha.research import services
from episalpha.settings import load_settings

REPO = Path(__file__).resolve().parents[2]
CUTOFF = datetime(2026, 9, 10, tzinfo=UTC)
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
REVENUE, DEMAND = "synthetic-span.revenue", "synthetic-span.demand"

LABELS = Labels(
    case_id="dev-synthetic-revenue",
    facts=(
        ExpectedFact(fact_id="f-revenue", span_ids=(REVENUE,), value="412000000.00", unit="EUR"),
        ExpectedFact(fact_id="f-demand", span_ids=(DEMAND,)),
    ),
    contradictions=(
        ExpectedContradiction(
            contradiction_id="x-demand-vs-revenue",
            side_a_span_ids=(DEMAND,),
            side_b_span_ids=(REVENUE,),
        ),
    ),
    should_abstain=False,
    supporting_span_ids=(REVENUE, DEMAND),
)

CONTRADICTION = Relation(
    relation_id="run-a.r1",
    predicate=RelationPredicate.CONTRADICTS,
    source_id=CONTRADICTING_CLAIM.claim_id,
    target_id=REPORTED_CLAIM.claim_id,
    evidence_span_ids=(DEMAND,),
    epistemic_status=EpistemicStatus.REPORTED,
    created_at=NOW,
)


def outcome(**changes: object) -> RunOutcome:
    base: dict[str, object] = {
        "run_id": "run-a",
        "state": RunState.RESEARCH_COMPLETED,
        "claims": (REPORTED_CLAIM, CONTRADICTING_CLAIM),
        "relations": (CONTRADICTION,),
        "hypotheses": 1,
        "proposals": (),
        "permitted_span_ids": (REVENUE, DEMAND),
        "documents": (SYNTHETIC_DOCUMENT,),
        "research_cutoff": CUTOFF,
        "failed_checks": (),
        "model_requests": 6,
        "latency_seconds": 12,
    }
    base.update(changes)
    return RunOutcome(**base)  # type: ignore[arg-type]


def ratio(score: scoring.CaseScore | scoring.PooledScore, metric: str) -> tuple[int, int]:
    value = score.metrics[metric]
    return value.numerator, value.denominator


# --- metric direction and denominators -----------------------------------------------------


def test_a_complete_correct_run_scores_every_metric_in_full() -> None:
    score = score_case(outcome(), LABELS, {"synthetic-claim.revenue": "supported"})
    assert ratio(score, "citation_correctness") == (2, 2)
    assert ratio(score, "supported_claim_precision") == (1, 2)  # one claim never assessed
    assert ratio(score, "required_fact_recall") == (2, 2)
    assert ratio(score, "contradiction_recall") == (1, 1)
    assert ratio(score, "correct_abstention") == (1, 1)
    assert ratio(score, "completion") == (1, 1)
    assert score.metrics["numeric_correctness"].value is None  # no derived number proposed
    assert str(score.metrics["numeric_correctness"]) == "N/A"
    assert score.hypotheses == 1  # reported separately, never counted as supported facts


def test_a_citation_to_an_unlabelled_passage_is_not_correct() -> None:
    labels = LABELS.model_copy(update={"supporting_span_ids": (REVENUE,)})
    assert ratio(score_case(outcome(), labels), "citation_correctness") == (1, 2)


def test_a_wrong_value_does_not_recover_the_fact() -> None:
    wrong = REPORTED_CLAIM.model_copy(
        update={
            "numeric_fact": REPORTED_CLAIM.numeric_fact.model_copy(  # type: ignore[union-attr]
                update={"value": Decimal("412.0")}
            )
        }
    )
    score = score_case(outcome(claims=(wrong, CONTRADICTING_CLAIM)), LABELS)
    assert ratio(score, "required_fact_recall") == (1, 2)


def test_an_empty_answer_loses_on_recall_completion_and_abstention() -> None:
    empty = outcome(state=RunState.ABSTAINED, claims=(), relations=(), hypotheses=0)
    score = score_case(empty, LABELS)
    assert ratio(score, "required_fact_recall") == (0, 2)
    assert ratio(score, "contradiction_recall") == (0, 1)
    assert ratio(score, "completion") == (0, 1)
    assert ratio(score, "correct_abstention") == (0, 1)
    # Avoiding claims never buys precision: nothing emitted is N/A, not 1.
    assert score.metrics["supported_claim_precision"].value is None
    assert score.metrics["citation_correctness"].value is None


def test_a_correct_abstention_is_complete() -> None:
    labels = Labels(case_id="dev-missing", should_abstain=True)
    score = score_case(outcome(state=RunState.ABSTAINED, claims=(), relations=()), labels)
    assert ratio(score, "correct_abstention") == (1, 1)
    assert ratio(score, "completion") == (1, 1)
    assert score.metrics["required_fact_recall"].value is None  # no expected facts: N/A


def test_a_failed_case_stays_in_every_denominator() -> None:
    failed = outcome(state=RunState.FAILED, claims=(), relations=(), hypotheses=0)
    scores = [score_case(outcome(), LABELS), score_case(failed, LABELS)]
    pooled = pool(scores)
    assert ratio(pooled, "required_fact_recall") == (2, 4)
    assert ratio(pooled, "contradiction_recall") == (1, 2)
    assert ratio(pooled, "completion") == (1, 2)
    assert ratio(pooled, "correct_abstention") == (1, 2)
    assert pooled.cases == 2


def test_a_provider_failure_is_not_a_correct_abstention() -> None:
    labels = Labels(case_id="dev-missing", should_abstain=True)
    failed = outcome(state=RunState.FAILED, claims=(), relations=())
    assert ratio(score_case(failed, labels), "correct_abstention") == (0, 1)


def test_pooling_with_no_applicable_denominator_is_na() -> None:
    labels = Labels(case_id="dev-free")  # no facts, no contradictions, no abstain decision
    pooled = pool([score_case(outcome(claims=(), relations=()), labels)])
    for metric in ("required_fact_recall", "contradiction_recall", "correct_abstention"):
        assert pooled.metrics[metric].value is None
        assert str(pooled.metrics[metric]) == "N/A"
    assert pool([]).metrics["completion"].value is None


def test_numeric_correctness_reads_the_proposals_before_repair() -> None:
    q3 = {
        "key": "c0",
        "statement": "Third quarter revenue was EUR 400.0 million.",
        "epistemic_status": "reported",
        "span_ids": [REVENUE],
        "numeric_fact": {**REPORTED_CLAIM.numeric_fact.model_dump(mode="json"), "value": "400"},  # type: ignore[union-attr]
    }
    q4 = {**q3, "key": "c1", "numeric_fact": {**q3["numeric_fact"], "value": "412"}}  # type: ignore[dict-item]

    def growth(key: str, value: str) -> dict[str, object]:
        return {
            "key": key,
            "statement": "Revenue grew quarter on quarter.",
            "epistemic_status": "derived",
            "derivation": {
                "method": "pct_change",
                "method_version": "1",
                "input_claim_ids": ["run-a.c0", "run-a.c1"],
            },
            "numeric_fact": {**q3["numeric_fact"], "value": value, "unit": "ratio"},  # type: ignore[dict-item]
        }

    first = {
        "stage": "researching",
        "attempt": 1,
        "payload": {"claims": [q3, q4, growth("g", "0.03")]},
    }
    repaired = {"stage": "researching", "attempt": 2, "payload": {"claims": [growth("g", "0.03")]}}
    critic = {
        "stage": "critiquing",
        "attempt": 1,
        "payload": {"counter_claims": [growth("k", "0.5")]},
    }
    score = score_case(outcome(proposals=(first, repaired, critic)), LABELS)
    # Attempt 1 of each stage only: 0.03 recomputes (12/400), 0.5 does not; the repair is ignored.
    assert ratio(score, "numeric_correctness") == (1, 2)


def test_violations_are_counted_not_hidden() -> None:
    late = SYNTHETIC_DOCUMENT.model_copy(
        update={
            "document_id": "synthetic-doc.late",
            "public_available_at": CUTOFF + timedelta(days=1),
            "availability_basis": AvailabilityBasis.PROVIDER_VERIFIED,
        }
    )
    stray = REPORTED_CLAIM.model_copy(
        update={"claim_id": "run-a.stray", "span_ids": ("outside-snapshot.span",)}
    )
    score = score_case(
        outcome(
            documents=(SYNTHETIC_DOCUMENT, late),
            claims=(REPORTED_CLAIM, CONTRADICTING_CLAIM, stray),
            failed_checks=("claim.run-a.x.references",),
        ),
        LABELS,
    )
    assert score.temporal_violations == 1
    assert score.boundary_violations == 1
    assert score.reference_violations == 1
    pooled = pool([score, score_case(outcome(), LABELS)])
    assert (pooled.temporal_violations, pooled.boundary_violations) == (1, 1)
    assert pooled.model_requests == (6, 6) and pooled.latencies == (12, 12)


def test_hypothesized_claims_are_not_factual_claims() -> None:
    guess = Claim(
        claim_id="run-a.guess",
        statement="Demand may recover.",
        subject_ids=("synthetic-issuer.eq",),
        attribution="model",
        epistemic_status=EpistemicStatus.HYPOTHESIZED,
        created_at=NOW,
    )
    score = score_case(outcome(claims=(REPORTED_CLAIM, CONTRADICTING_CLAIM, guess)), LABELS)
    assert ratio(score, "supported_claim_precision")[1] == 2


# --- cases, partitions and sealed labels ---------------------------------------------------


def case(case_id: str, partition: str, family: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        partition=partition,  # type: ignore[arg-type]
        family_id=family,
        case_type="extraction",  # type: ignore[arg-type]
        instrument_id="synthetic-issuer.eq",
        snapshot_ref="synthetic",
        question="What revenue did the issuer report for the fourth quarter?",
        research_cutoff=CUTOFF,
    )


def test_one_family_in_two_partitions_fails() -> None:
    check_partitions([case("dev-a", "development", "fam-1"), case("dev-b", "development", "fam-1")])
    with pytest.raises(EpisAlphaError, match="fam-1"):
        check_partitions(
            [case("dev-a", "development", "fam-1"), case("val-a", "validation", "fam-1")]
        )
    with pytest.raises(EpisAlphaError, match="dev-a"):
        check_partitions(
            [case("dev-a", "development", "fam-1"), case("dev-a", "development", "fam-2")]
        )


def test_the_drafted_development_cases_load_and_partition_cleanly() -> None:
    loaded = load_cases(REPO / "eval_cases" / "campaigns" / "demo-v1" / "cases")
    assert loaded and all(item.partition == "development" for item in loaded)
    check_partitions(loaded)


@pytest.fixture
def sealed(tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    project, labels = tmp_path / "project", tmp_path / "sealed-labels"
    labels.mkdir()
    (labels / f"{LABELS.case_id}.json").write_text(LABELS.model_dump_json())
    config = tmp_path / "test.toml"
    config.write_text(
        f'[paths]\nproject_root = "{project}"\ndata_root = "{project / ".episalpha"}"\n'
        f'\n[evaluation]\nlabels_dir = "{labels}"\n'
    )
    yield config, labels


def test_only_the_evaluator_loads_labels(sealed: tuple[Path, Path]) -> None:
    config, labels = sealed
    settings = load_settings(config)
    assert load_labels(settings, caller="evaluator") == {LABELS.case_id: LABELS}
    for caller in ("research", "tool", "candidate_author"):
        with pytest.raises(EpisAlphaError, match="evaluator"):
            load_labels(settings, caller=caller)


def test_labels_inside_the_agent_accessible_workspace_are_refused(tmp_path: Path) -> None:
    project = tmp_path / "project"
    for inside in (project / "eval_cases" / "labels", project / ".episalpha" / "labels"):
        inside.mkdir(parents=True)
        config = tmp_path / "test.toml"
        config.write_text(
            f'[paths]\nproject_root = "{project}"\ndata_root = "{project / ".episalpha"}"\n'
            f'\n[evaluation]\nlabels_dir = "{inside}"\n'
        )
        with pytest.raises(EpisAlphaError, match="workspace"):
            load_labels(load_settings(config), caller="evaluator")


def test_unconfigured_labels_are_refused(tmp_path: Path) -> None:
    config = tmp_path / "test.toml"
    config.write_text(f'[paths]\nproject_root = "{tmp_path}"\ndata_root = "{tmp_path / "d"}"\n')
    with pytest.raises(EpisAlphaError, match="labels_dir"):
        load_labels(load_settings(config), caller="evaluator")


def test_the_evaluator_hash_changes_when_a_label_changes(sealed: tuple[Path, Path]) -> None:
    _, labels = sealed
    before, before_labels = evaluator_hash(labels), labels_hash(labels)
    changed = LABELS.model_copy(update={"should_abstain": True})
    (labels / f"{LABELS.case_id}.json").write_text(changed.model_dump_json())
    assert evaluator_hash(labels) != before and labels_hash(labels) != before_labels


def test_the_evaluator_hash_covers_the_scoring_source(
    sealed: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, labels = sealed
    before = evaluator_hash(labels)
    monkeypatch.setattr(cases_module, "EVALUATOR_SOURCES", (Path(scoring.__file__),))
    assert evaluator_hash(labels) != before


def test_a_label_file_must_be_named_after_its_case(sealed: tuple[Path, Path]) -> None:
    config, labels = sealed
    (labels / "other-name.json").write_text(LABELS.model_dump_json())
    with pytest.raises(EpisAlphaError, match="other-name"):
        load_labels(load_settings(config), caller="evaluator")


# --- a real fake-runtime run ---------------------------------------------------------------


def test_a_fake_run_is_scored_from_its_saved_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EPISALPHA_FAKE_SCENARIO", "completion")
    config = tmp_path / "test.toml"
    config.write_text(f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n')
    workbench = services.open_workbench(load_settings(config))
    try:
        services.seed_demo(workbench)
        request, plan = services.plan_case(
            workbench, "supported", RuntimeMode.FAKE, now=NOW, nonce="scoring"
        )
        services.submit(workbench, request, plan)
        services.execute(workbench, request.run_id, worker_id="test", now=lambda: NOW)
        loaded = scoring.load_outcome(workbench.repo, workbench.runs_dir, request.run_id)
    finally:
        workbench.close()
    assert loaded.state is RunState.RESEARCH_COMPLETED
    assert {stage["stage"] for stage in loaded.proposals} == {
        "researching",
        "critiquing",
        "synthesizing",
    }
    score = score_case(loaded, LABELS.model_copy(update={"case_id": "dev-fake"}))
    assert ratio(score, "required_fact_recall") == (2, 2)
    assert ratio(score, "contradiction_recall") == (1, 1)  # the critic's c2 CONTRADICTS c1
    assert score.model_requests == 6 and score.latency_seconds == 0
    assert json.loads(json.dumps(scoring.as_json(score)))["case_id"] == "dev-fake"


def test_the_development_label_drafts_validate_and_match_the_cases() -> None:
    drafts = REPO / "docs" / "implementation" / "m6-label-drafts" / "development"
    cases = {item.case_id for item in load_cases(REPO / "eval_cases/campaigns/demo-v1/cases")}
    labels = [Labels.model_validate_json(path.read_text()) for path in drafts.glob("*.json")]
    assert {item.case_id for item in labels} == cases
    assert all(item.reviewed_by is None for item in labels)  # drafts until the owner signs


def test_answering_when_the_honest_answer_is_to_abstain_is_wrong() -> None:
    labels = Labels(case_id="dev-missing", should_abstain=True)
    score = score_case(outcome(), labels)  # a confident completed thesis
    assert ratio(score, "correct_abstention") == (0, 1)
    assert ratio(score, "completion") == (0, 1)


def test_scoring_refuses_a_tampered_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Scoring reads artifacts without replay's up-front verify(); RunArtifacts.read's own hash
    # check is what keeps an edited artifact out of the scores (found by a mutation check).
    from episalpha.research.artifacts import ArtifactIntegrityError

    monkeypatch.setenv("EPISALPHA_FAKE_SCENARIO", "completion")
    config = tmp_path / "test.toml"
    config.write_text(f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n')
    workbench = services.open_workbench(load_settings(config))
    try:
        services.seed_demo(workbench)
        request, plan = services.plan_case(
            workbench, "supported", RuntimeMode.FAKE, now=NOW, nonce="tamper"
        )
        services.submit(workbench, request, plan)
        services.execute(workbench, request.run_id, worker_id="test", now=lambda: NOW)
        records = workbench.runs_dir / request.run_id / "records.json"
        records.write_text(records.read_text().replace("412000000.00", "999000000.00"))
        with pytest.raises(ArtifactIntegrityError):
            scoring.load_outcome(workbench.repo, workbench.runs_dir, request.run_id)
    finally:
        workbench.close()
