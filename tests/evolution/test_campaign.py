"""M6-T03 — the offline campaign, end to end on the fake runtime (plan sections 12.2-12.3).

Every run here is a fake-runtime FIXTURE over the SYNTHETIC corpus, never research and never
evidence that a live campaign passed. The test campaign gives its synthetic cases different
family IDs so that all three partitions can be exercised; a real dataset could not do that
with one document.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from episalpha.contracts.errors import EpisAlphaError
from episalpha.contracts.research import RunState, RuntimeMode
from episalpha.evaluation.cases import ExpectedContradiction, ExpectedFact, Labels
from episalpha.evaluation.scoring import METRICS, CaseScore, Ratio
from episalpha.evolution import campaign as campaigns
from episalpha.evolution.campaign import (
    TrialSpec,
    compare,
    execution_id,
    services_executor,
    validation_gates,
)
from episalpha.evolution.candidates import Ledger
from episalpha.observability import shutdown_tracing
from episalpha.research import services
from episalpha.research.artifacts import RunArtifacts
from episalpha.research.runner import ResearchRunner, claim
from episalpha.runtime.fake import FakeRuntime, Scenario
from episalpha.settings import load_settings

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 12, 22, 0, tzinfo=UTC)
REVENUE, DEMAND = "synthetic-span.revenue", "synthetic-span.demand"
CASES = [
    ("dev-one", "development", "fam-dev"),
    ("val-one", "validation", "fam-val"),
    ("fin-one", "final", "fam-fin"),
]
LABEL = Labels(
    case_id="placeholder",
    facts=(ExpectedFact(fact_id="f-revenue", span_ids=(REVENUE,)),),
    contradictions=(
        ExpectedContradiction(
            contradiction_id="x-demand", side_a_span_ids=(DEMAND,), side_b_span_ids=(REVENUE,)
        ),
    ),
    should_abstain=False,
    reviewed_by="test fixture",
    reviewed_at=NOW,
)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    monkeypatch.setenv("EPISALPHA_FAKE_SCENARIO", "completion")
    source = tmp_path / "campaign"
    (source / "cases").mkdir(parents=True)
    labels = tmp_path / "sealed"
    labels.mkdir()
    for case_id, partition, family in CASES:
        case = {
            "case_id": case_id,
            "partition": partition,
            "family_id": family,
            "case_type": "contradiction",
            "instrument_id": "synthetic-issuer.eq",
            "snapshot_ref": "synthetic",
            "question": f"Synthetic fixture question for {case_id}.",
            "research_cutoff": "2026-09-10T00:00:00+00:00",
        }
        (source / "cases" / f"{case_id}.json").write_text(json.dumps(case))
        label = LABEL.model_copy(update={"case_id": case_id})
        (labels / f"{case_id}.json").write_text(label.model_dump_json())
    shutil.copy(REPO / "tests/fixtures/candidates/allowed.json", source / "proposal.json")
    config = tmp_path / "test.toml"

    def write(**limits: int) -> Path:
        extra = "".join(f"{key} = {value}\n" for key, value in limits.items())
        config.write_text(
            f'[paths]\nproject_root = "{REPO}"\ndata_root = "{tmp_path / "data"}"\n\n'
            '[provider]\nmodel_id = "vendor/model:free"\n'
            'endpoint_url = "https://openrouter.ai/api/v1"\napi_key_env = "ENV:NEVER_SET_KEY"\n\n'
            f'[evaluation]\nlabels_dir = "{labels}"\n\n[limits]\n{extra}'
        )
        return config

    write()
    workbench = services.open_workbench(load_settings(config))
    services.seed_demo(workbench)
    workbench.close()
    yield {"source": source, "labels": labels, "config": write, "tmp": tmp_path}
    shutdown_tracing()


def open_bench(world: dict[str, Any], **limits: int) -> services.Workbench:
    return services.open_workbench(load_settings(world["config"](**limits)))


def run(
    world: dict[str, Any],
    mode: RuntimeMode = RuntimeMode.FAKE,
    *,
    now: datetime = NOW,
    executor: Any = None,
    author: Any = None,
    **limits: int,
) -> tuple[campaigns.CampaignResult, list[dict[str, Any]]]:
    workbench = open_bench(world, **limits)
    try:
        result = compare(
            workbench,
            "test-campaign",
            mode,
            now=lambda: now,
            executor=executor,
            author=author,
            source=world["source"],
        )
        return result, Ledger(result.directory / "ledger.jsonl").records()
    finally:
        workbench.close()


def kinds(ledger: list[dict[str, Any]]) -> list[str]:
    return [
        f"{r['kind']}:{r['phase']}:{r['variant']}" if r["kind"] == "trial" else r["kind"]
        for r in ledger
    ]


def test_the_manifest_is_frozen_before_any_trial_and_the_baseline_is_kept(
    world: dict[str, Any],
) -> None:
    result, ledger = run(world)
    assert kinds(ledger) == [
        "manifest_frozen",
        "trial:development:baseline",
        "author_inputs",
        "proposal_accepted",
        "materialized",
        "trial:validation:baseline",
        "trial:validation:challenger",
        "validation_gates",
        "decision",
    ]
    manifest = json.loads((result.directory / "manifest.json").read_text())
    assert manifest["rule"] == dict(campaigns.RULE)
    assert manifest["partitions"] == {
        "development": ["dev-one"],
        "validation": ["val-one"],
        "final": ["fin-one"],
    }
    assert manifest["runtime"] == "fake" and manifest["model"] == "fixture"
    # The fake challenger behaves like the baseline: no new contradiction, so the rule fails
    # and the baseline is retained. The final-check cases were never run.
    assert result.decision == "baseline_retained"
    gates = {gate["gate"]: gate["passed"] for gate in result.gates}
    assert gates["3 contradiction gain"] is False
    assert not any(r.get("phase") == "final" for r in ledger)
    # Nothing replaced the baseline.
    config = json.loads((REPO / "harnesses/baseline/config.json").read_text())
    assert config["contradiction_search"] is False
    assert services.HARNESS_ID == "harness.baseline"


def test_the_challenger_runs_its_own_harness_on_the_baselines_snapshot(
    world: dict[str, Any],
) -> None:
    result, ledger = run(world)
    trials = {(r["phase"], r["variant"]): r for r in ledger if r["kind"] == "trial"}
    base, chal = trials["validation", "baseline"], trials["validation", "challenger"]
    assert chal["snapshot"] == base["snapshot_id"]  # paired on one frozen snapshot
    assert chal["harness_id"] == f"harness.{result.candidate_id}"
    assert chal["harness_hash"] != base["harness_hash"]
    workbench = open_bench(world)
    try:
        record = workbench.repo.get_run(chal["run_id"])
        assert record is not None and record.request.harness_id == chal["harness_id"]
        assert record.snapshot_id is not None
        challenger_snapshot = workbench.repo.get_snapshot(record.snapshot_id)
        baseline_snapshot = workbench.repo.get_snapshot(base["snapshot_id"])
    finally:
        workbench.close()
    assert challenger_snapshot is not None and baseline_snapshot is not None
    assert challenger_snapshot.document_ids == baseline_snapshot.document_ids
    assert challenger_snapshot.permitted_span_ids == baseline_snapshot.permitted_span_ids


def test_the_author_sees_no_labels_and_no_hidden_case(world: dict[str, Any]) -> None:
    seen: list[Mapping[str, Any]] = []

    def author(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(inputs)
        return json.loads((world["source"] / "proposal.json").read_text())  # type: ignore[no-any-return]

    run(world, author=author)
    (inputs,) = seen
    text = json.dumps(inputs)
    for secret in (
        "f-revenue",
        "x-demand",
        REVENUE,
        DEMAND,
        "should_abstain",
        "val-one",
        "fin-one",
    ):
        assert secret not in text
    assert set(inputs) == {"development_failures", "patch_schema"}


def test_fake_and_live_campaigns_never_share_an_id(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, fake_ledger = run(world)
    workbench = open_bench(world, campaign_requests_per_day=1000)
    runs = services_executor(workbench, lambda: NOW)

    def executor(spec: TrialSpec) -> str:
        # The offline suite never calls a model: the "live" trials run the fake path.
        return runs(replace(spec, runtime=RuntimeMode.FAKE))

    try:
        live = compare(
            workbench,
            "test-campaign",
            RuntimeMode.HERMES,
            now=lambda: NOW,
            executor=executor,
            source=world["source"],
        )
    finally:
        workbench.close()
    live_ledger = Ledger(live.directory / "ledger.jsonl").records()
    assert live.campaign_id != fake.campaign_id
    fake_ids = {r["execution_id"] for r in fake_ledger if r["kind"] == "trial"}
    live_ids = {r["execution_id"] for r in live_ledger if r["kind"] == "trial"}
    assert fake_ids and live_ids and not fake_ids & live_ids
    identity = {
        "campaign_id": "c",
        "model": "m",
        "snapshot": "s",
        "harness_hash": "h",
        "evaluator_hash": "e",
        "labels_hash": "l",
        "case_id": "k",
        "attempt": 1,
    }
    assert execution_id(runtime="fake", **identity) != execution_id(runtime="hermes", **identity)
    assert execution_id(runtime="fake", **identity) != execution_id(
        runtime="fake", **{**identity, "attempt": 2}
    )


def test_a_live_campaign_is_blocked_without_the_owner_decisions(world: dict[str, Any]) -> None:
    with pytest.raises(EpisAlphaError, match="capacity"):
        run(world, RuntimeMode.HERMES)
    for path in world["labels"].glob("*.json"):
        label = json.loads(path.read_text())
        path.write_text(json.dumps({**label, "reviewed_by": None}))
    with pytest.raises(EpisAlphaError, match="human-validated"):
        run(world, RuntimeMode.HERMES, campaign_requests_per_day=1000)


def test_an_interrupted_trial_is_recorded_and_the_rerun_resumes(world: dict[str, Any]) -> None:
    calls: list[str] = []

    def failing(spec: TrialSpec) -> str:
        calls.append(f"{spec.phase}:{spec.variant}:{spec.attempt}")
        if spec.variant == "challenger":
            raise RuntimeError("worker lost")
        workbench = open_bench(world)
        try:
            return services_executor(workbench, lambda: NOW)(spec)
        finally:
            workbench.close()

    with pytest.raises(RuntimeError, match="worker lost"):
        run(world, executor=failing)
    _, ledger = run(world)  # the default executor: the rerun resumes from the ledger
    trials = [r for r in ledger if r["kind"] == "trial"]
    interrupted = [r for r in trials if r["status"] == "interrupted"]
    assert len(interrupted) == 1 and interrupted[0]["variant"] == "challenger"
    assert interrupted[0]["error"] == "worker lost"
    resumed = [r for r in trials if r["variant"] == "challenger" and r["status"] == "scored"]
    assert resumed[0]["attempt"] == 2  # a new attempt; the interrupted one stays recorded
    # Completed trials were never re-run.
    assert [r["phase"] for r in trials if r["variant"] == "baseline"] == [
        "development",
        "validation",
    ]
    assert ledger[-1]["kind"] == "decision"


def test_the_daily_cap_pauses_the_campaign_and_the_next_day_resumes(
    world: dict[str, Any],
) -> None:
    result, ledger = run(world, campaign_requests_per_day=10)  # one fake run spends 6
    assert result.status == "paused" and result.decision is None
    paused = [r for r in ledger if r["kind"] == "paused"]
    assert paused and paused[0]["spent_today"] == 6 and paused[0]["cap"] == 10
    later, ledger = run(world, now=NOW + timedelta(days=1), campaign_requests_per_day=10)
    assert later.campaign_id == result.campaign_id
    assert later.status == "paused"  # one more trial fits per day
    assert len([r for r in ledger if r["kind"] == "trial"]) == 2


def test_the_final_check_runs_only_after_validation_passes(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def all_pass(*args: Any) -> list[dict[str, Any]]:
        return [{"gate": "stub", "passed": True, "detail": "test"}]

    monkeypatch.setattr(campaigns, "validation_gates", all_pass)
    result, ledger = run(world)
    phases = [r["phase"] for r in ledger if r["kind"] == "trial"]
    assert phases == ["development", "validation", "validation", "final", "final"]
    assert kinds(ledger).index("validation_gates") < kinds(ledger).index("trial:final:baseline")
    assert result.gates[-1]["gate"] == "5 final check"
    # Even a pass does not replace the baseline: it is recorded for the owner.
    assert result.decision == "challenger_passed"
    assert ledger[-1]["note"].startswith("the baseline stays active")


def test_a_rejected_proposal_ends_the_campaign_with_the_baseline(world: dict[str, Any]) -> None:
    budget = json.loads((REPO / "tests/fixtures/candidates/budget.json").read_text())
    result, ledger = run(world, author=lambda inputs: budget)
    assert result.decision == "baseline_retained"
    assert "proposal_rejected" in kinds(ledger)
    assert not any(r.get("phase") == "validation" for r in ledger)


# --- the decision rule ---------------------------------------------------------------------


def score(case_id: str, found: tuple[str, ...] = (), requests: int = 6, **kw: Any) -> CaseScore:
    metrics = {name: Ratio(1, 1) for name in METRICS}
    return CaseScore(
        case_id=case_id,
        run_id=f"run-{case_id}",
        state=RunState.RESEARCH_COMPLETED,
        metrics=metrics,
        recovered_contradictions=found,
        model_requests=requests,
        latency_seconds=10,
        **kw,
    )


def gates(base: list[CaseScore], chal: list[CaseScore]) -> dict[str, bool]:
    return {g["gate"]: g["passed"] for g in validation_gates(base, chal, 8)}


def test_the_rule_passes_only_a_strict_contradiction_gain() -> None:
    base = [score("a", ("x1",)), score("b")]
    assert all(gates(base, [score("a", ("x1",)), score("b", ("x2",))]).values())
    assert not gates(base, [score("a"), score("b", ("x2",))])["3 contradiction gain"]  # lost x1
    assert not gates(base, [score("a", ("x1",)), score("b")])["3 contradiction gain"]  # no gain


def test_each_other_rule_can_fail_on_its_own() -> None:
    base = [score("a")]
    gain = ("x1",)
    assert not gates(base, [score("a", gain, requests=10)])["4 cost within 1.5x and hard budgets"]
    assert not gates(base, [score("a", gain, temporal_violations=1)])["1 zero violations"]
    worse = score("a", gain)
    worse.metrics["completion"] = Ratio(0, 1)
    assert not gates(base, [worse])["2 no quality loss"]
    unsupported = score("a", gain, unsupported_claims=("run-a.c9",))
    assert not gates(base, [unsupported])["2 no quality loss"]
    assert not gates([], [])["0 validation cases exist"]


def test_the_runner_adds_one_bounded_contradiction_search_to_the_critic_brief(
    world: dict[str, Any],
) -> None:
    workbench = open_bench(world, max_contradiction_queries=1)
    try:
        request, plan = services.plan_case(
            workbench, "supported", RuntimeMode.FAKE, now=NOW, nonce="brief"
        )
        services.submit(workbench, request, plan)
        claim(workbench.repo, request.run_id, "t", now=NOW)
        runner = ResearchRunner(
            workbench.repo,
            workbench.objects,
            workbench.settings,
            services.synthetic_loader(workbench),
            artifacts_root=workbench.runs_dir,
            now=lambda: NOW,
            harness_config={"contradiction_search": True},
        )
        runner.execute(request.run_id, FakeRuntime(workbench.objects, Scenario.COMPLETION))
    finally:
        workbench.close()
    runner.artifacts = RunArtifacts(world["tmp"] / "scratch", request.run_id)  # not the saved run
    context = SimpleNamespace(run_id=request.run_id, research_cutoff=NOW)
    brief = runner.brief_for(RunState.CRITIQUING, context)  # type: ignore[arg-type]
    assert "Contradiction search (host retrieval over this snapshot):" in brief
    hits = [line.split(": ") for line in brief.splitlines() if line.startswith("- against ")]
    first = next(iter(runner.claims))
    assert hits and all(hit[0] == f"- against {first}" for hit in hits)  # one query, bounded
    assert runner.view is not None
    assert all(hit[1] in runner.view.manifest.permitted_span_ids for hit in hits)
    assert runner.artifacts.read("contradiction_search") == {first: [hit[1] for hit in hits]}
    runner.harness_config, runner.counter_evidence = {}, None
    assert "Contradiction search" not in runner.brief_for(RunState.CRITIQUING, context)  # type: ignore[arg-type]
