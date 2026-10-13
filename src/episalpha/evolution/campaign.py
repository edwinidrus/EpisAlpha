"""One offline campaign: baseline against one challenger (plan sections 12.2-12.3, M6-T03).

Order, each step in the campaign's append-only ledger:

1. **Freeze the manifest** before any trial: decision rule, partitions, evaluator and label
   hashes, budgets, runtime mode, provider/model, baseline harness hash. The campaign ID hashes
   it, so a fake and a live campaign named ``demo-v1`` never share an ID, and a changed label or
   evaluator is a different campaign (acceptance row A24).
2. **Development:** the baseline runs the development cases.
3. **Proposal:** the candidate author sees only a development failure summary (case IDs, states,
   metric counts) and the patch schema: never labels, never a validation or final case. The
   proposal is validated and materialized by :mod:`episalpha.evolution.candidates`.
4. **Validation:** baseline, then challenger on the baseline's *own frozen snapshot*, per case.
   The section 12.3 rule is applied gate by gate.
5. **Final check**, only when every validation gate passed.
6. **Decision.** Passing never replaces the baseline: promotion is an owner action (article 8).

Every trial is recorded, scored or interrupted. A completed trial is never re-run (no searching
for a better result); a campaign re-run resumes where the ledger stops. When the owner's daily
request cap would be crossed, the campaign records ``paused`` and stops; it never trims cases.
Only this module's evaluator side loads labels.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.research import RunState, RuntimeMode
from episalpha.evaluation.cases import (
    EVALUATOR,
    EvalCase,
    Labels,
    Partition,
    check_partitions,
    evaluator_hash,
    labels_hash,
    load_cases,
    load_labels,
)
from episalpha.evaluation.scoring import CaseScore, Ratio, as_json, load_outcome, pool, score_case
from episalpha.evolution.candidates import (
    ALLOWED_PATH,
    CandidateRejected,
    Ledger,
    ValidatedCandidate,
    materialize,
    propose,
)
from episalpha.observability import SpanKind, annotate, span
from episalpha.research import services
from episalpha.runtime.hermes import load_harness

CAMPAIGNS = Path("eval_cases") / "campaigns"
RULE: Mapping[str, Any] = {
    "version": "1",
    "max_violations": 0,
    "min_new_contradictions": 1,
    "max_request_ratio": "1.5",
    "max_latency_ratio": "1.5",
    "quality_metrics": [
        "supported_claim_precision",
        "required_fact_recall",
        "correct_abstention",
        "completion",
    ],
}
"""Plan section 12.3 defaults. Frozen into each manifest; a change is a new campaign."""
PATCH_SCHEMA: Mapping[str, Any] = {
    "parent_harness_id": services.HARNESS_ID,
    "hypothesis": "<one sentence>",
    "rationale": "<why, from the development failures>",
    "patch": [{"op": "replace", "path": ALLOWED_PATH, "value": "<boolean>"}],
}
FIXTURE_MODEL = "fixture"


class CampaignPaused(EpisAlphaError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.BUDGET_EXCEEDED, message)


@dataclass(frozen=True)
class TrialSpec:
    campaign_id: str
    phase: str
    variant: str
    case: EvalCase
    harness_id: str
    snapshot: str
    """``synthetic`` / the case's snapshot for a fresh run, or the baseline run's snapshot ID."""
    attempt: int
    execution_id: str
    runtime: RuntimeMode


Executor = Callable[[TrialSpec], str]
"""Runs one trial to a terminal state and returns its run ID."""
Author = Callable[[Mapping[str, Any]], Mapping[str, Any]]
"""Turns the author inputs into one proposal."""


@dataclass(frozen=True)
class CampaignResult:
    campaign_id: str
    status: str
    """``decided`` or ``paused``."""
    directory: Path
    decision: str | None = None
    gates: tuple[dict[str, Any], ...] = ()
    candidate_id: str | None = None


def execution_id(**identity: Any) -> str:
    """Hash of everything a result depends on (M6 article 9)."""
    return "exec-" + _hash(identity)[:16]


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def services_executor(workbench: services.Workbench, now: Callable[[], datetime]) -> Executor:
    """Admit and execute a trial through the same services as ``research run``."""

    def run(spec: TrialSpec) -> str:
        case = spec.case
        fresh = spec.snapshot == case.snapshot_ref
        if fresh and case.snapshot_ref != "synthetic":
            plan: dict[str, Any] = {"evidence": "snapshot", "snapshot_id": case.snapshot_ref}
        elif fresh:
            plan = {"evidence": "synthetic"}
        else:
            plan = {"evidence": "snapshot", "snapshot_id": spec.snapshot}
        plan["fake_scenario"] = services.FAKE_SCENARIOS["supported"].value
        plan["campaign_trial"] = spec.execution_id
        request = services.new_request(
            workbench,
            source=f"campaign:{spec.execution_id}",
            instrument_id=case.instrument_id,
            question=case.question,
            research_cutoff=case.research_cutoff,
            research_mode=case.research_mode,
            runtime_mode=spec.runtime,
            now=now(),
            harness_id=spec.harness_id,
        )
        services.submit(workbench, request, plan)
        services.execute(workbench, request.run_id, worker_id="campaign", now=now)
        return request.run_id

    return run


def file_author(directory: Path) -> Author:
    """The scripted author: the proposal written in the campaign directory, used as is."""

    def author(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        return json.loads((directory / "proposal.json").read_text())  # type: ignore[no-any-return]

    return author


def compare(
    workbench: services.Workbench,
    name: str,
    mode: RuntimeMode,
    *,
    now: Callable[[], datetime],
    executor: Executor | None = None,
    author: Author | None = None,
    source: Path | None = None,
) -> CampaignResult:
    """Run (or resume) campaign ``name`` with ``mode``. Refuses when its inputs are not sound.

    ``source`` defaults to ``eval_cases/campaigns/<name>/`` (cases and the scripted proposal).
    """
    settings = workbench.settings
    source = source or workbench.project_root / CAMPAIGNS / name
    labels = load_labels(settings, caller=EVALUATOR)
    cases = load_cases(source / "cases")
    check_partitions(cases)
    unlabelled = sorted(case.case_id for case in cases if case.case_id not in labels)
    if unlabelled:
        raise _refuse(f"cases without sealed labels: {unlabelled}")
    labels_dir = settings.evaluation.labels_dir
    assert labels_dir is not None  # load_labels refused otherwise
    reviewed = all(labels[case.case_id].reviewed_by for case in cases)
    if mode is RuntimeMode.HERMES:
        if settings.limits.campaign_requests_per_day is None:
            raise _refuse(
                "BLOCKED: no owner decision on free-tier capacity; set "
                "limits.campaign_requests_per_day (M6 article 11)"
            )
        if not reviewed:
            raise _refuse("BLOCKED: labels are not human-validated (reviewed_by unset)")
    baseline_root = workbench.harness_root(services.HARNESS_ID)
    baseline = load_harness(baseline_root)
    manifest = {
        "name": name,
        "runtime": mode.value,
        "model": FIXTURE_MODEL if mode is RuntimeMode.FAKE else settings.provider.model_id,
        "rule": dict(RULE),
        "partitions": {
            partition.value: [c.case_id for c in cases if c.partition is partition]
            for partition in Partition
        },
        "evaluator_hash": evaluator_hash(labels_dir),
        "labels_hash": labels_hash(labels_dir),
        "labels_reviewed": reviewed,
        "budgets": settings.limits.model_dump(mode="json"),
        "baseline_harness_id": baseline.harness_id,
        "baseline_harness_hash": baseline.harness_hash,
        "runs_per_variant": 1,
        "limitations": ["one run per variant and case: single-run variability is not measured"],
    }
    campaign_id = "camp-" + _hash(manifest)[:16]
    directory = workbench.data_root / "campaigns" / campaign_id
    ledger = Ledger(directory / "ledger.jsonl")
    run = _Campaign(
        workbench,
        campaign_id,
        mode,
        manifest,
        labels,
        ledger,
        executor or services_executor(workbench, now),
        now,
    )
    run.freeze(directory)
    try:
        return run.drive(cases, baseline_root, author or file_author(source), directory)
    except CampaignPaused:
        return CampaignResult(campaign_id=campaign_id, status="paused", directory=directory)


def _refuse(message: str) -> EpisAlphaError:
    return EpisAlphaError(ErrorCode.INVALID_REQUEST, message)


@dataclass
class _Campaign:
    workbench: services.Workbench
    campaign_id: str
    mode: RuntimeMode
    manifest: dict[str, Any]
    labels: Mapping[str, Labels]
    ledger: Ledger
    executor: Executor
    now: Callable[[], datetime]
    scores: dict[tuple[str, str, str], CaseScore] = field(default_factory=dict)

    def record(self, kind: str, **fields: Any) -> None:
        self.ledger.append(kind, campaign_id=self.campaign_id, now=self.now(), **fields)

    def freeze(self, directory: Path) -> None:
        path = directory / "manifest.json"
        text = json.dumps(self.manifest, indent=2, sort_keys=True) + "\n"
        if path.exists() and path.read_text() != text:
            raise EpisAlphaError(ErrorCode.INTEGRITY_ERROR, f"{path} changed after freezing")
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if not any(r["kind"] == "manifest_frozen" for r in self.ledger.records()):
            self.record("manifest_frozen", manifest_hash=_hash(self.manifest))

    def drive(
        self, cases: Sequence[EvalCase], baseline_root: Path, author: Author, directory: Path
    ) -> CampaignResult:
        by_partition = {p: [c for c in cases if c.partition is p] for p in Partition}
        baseline_id = self.manifest["baseline_harness_id"]
        development = [
            self.trial("development", "baseline", case, baseline_id, case.snapshot_ref)
            for case in by_partition[Partition.DEVELOPMENT]
        ]
        candidate = self.candidate(development, baseline_root, author)
        if candidate is None:
            rejected = {"gate": "candidate", "passed": False, "detail": "proposal rejected"}
            return self.decide(directory, (rejected,), None)
        made = materialize(
            candidate,
            baseline_root,
            self.workbench.candidates_dir,
            self.ledger,
            now=self.now(),
            campaign_id=self.campaign_id,
        )
        validation = self.paired("validation", by_partition[Partition.VALIDATION], made.harness_id)
        gates = validation_gates(*validation, self.workbench.settings.limits.max_model_requests)
        self.record("validation_gates", gates=gates)
        if all(gate["passed"] for gate in gates):
            final = self.paired("final", by_partition[Partition.FINAL], made.harness_id)
            gates = [*gates, final_gate(*final)]
        return self.decide(directory, tuple(gates), made.candidate_id)

    def candidate(
        self, development: Sequence[CaseScore], baseline_root: Path, author: Author
    ) -> ValidatedCandidate | None:
        records = self.ledger.records()
        if any(r["kind"] == "proposal_rejected" for r in records):
            return None  # one proposal per campaign; never search for a better one
        inputs = {
            "development_failures": [
                {
                    "case_id": score.case_id,
                    "state": score.state.value,
                    "metrics": {k: str(v) for k, v in score.metrics.items()},
                }
                for score in development
                if any(
                    r.denominator and r.numerator < r.denominator for r in score.metrics.values()
                )
                or score.state is not RunState.RESEARCH_COMPLETED
            ],
            "patch_schema": dict(PATCH_SCHEMA),
        }
        accepted = [r for r in records if r["kind"] == "proposal_accepted"]
        raw = accepted[0]["proposal"] if accepted else author(inputs)
        if not accepted:
            self.record("author_inputs", inputs=inputs)
        try:
            return propose(
                raw, baseline_root, self.ledger, campaign_id=self.campaign_id, now=self.now()
            )
        except CandidateRejected:
            return None

    def paired(
        self, phase: str, cases: Sequence[EvalCase], challenger_id: str
    ) -> tuple[list[CaseScore], list[CaseScore]]:
        baseline_id = self.manifest["baseline_harness_id"]
        base, chal = [], []
        for case in cases:
            first = self.trial(phase, "baseline", case, baseline_id, case.snapshot_ref)
            record = self.workbench.repo.get_run(first.run_id)
            snapshot = record.snapshot_id if record and record.snapshot_id else case.snapshot_ref
            base.append(first)
            chal.append(self.trial(phase, "challenger", case, challenger_id, snapshot))
        return base, chal

    def trial(
        self, phase: str, variant: str, case: EvalCase, harness_id: str, snapshot: str
    ) -> CaseScore:
        key = (phase, variant, case.case_id)
        trials = [
            r
            for r in self.ledger.records()
            if r["kind"] == "trial" and (r["phase"], r["variant"], r["case_id"]) == key
        ]
        scored = [r for r in trials if r["status"] == "scored"]
        if scored:  # a completed trial is never re-run
            outcome = load_outcome(
                self.workbench.repo, self.workbench.runs_dir, scored[0]["run_id"]
            )
            return score_case(outcome, self.labels[case.case_id], self._assessments(outcome))
        self.check_budget(key)
        harness_hash = load_harness(self.workbench.harness_root(harness_id)).harness_hash
        attempt = len(trials) + 1
        spec = TrialSpec(
            campaign_id=self.campaign_id,
            phase=phase,
            variant=variant,
            case=case,
            harness_id=harness_id,
            snapshot=snapshot,
            attempt=attempt,
            runtime=self.mode,
            execution_id=execution_id(
                campaign_id=self.campaign_id,
                runtime=self.mode.value,
                model=self.manifest["model"],
                snapshot=snapshot,
                harness_hash=harness_hash,
                evaluator_hash=self.manifest["evaluator_hash"],
                labels_hash=self.manifest["labels_hash"],
                case_id=case.case_id,
                attempt=attempt,
            ),
        )
        common = {
            "phase": phase,
            "variant": variant,
            "case_id": case.case_id,
            "execution_id": spec.execution_id,
            "attempt": attempt,
            "harness_id": harness_id,
            "harness_hash": harness_hash,
            "snapshot": snapshot,
        }
        attributes = {f"episalpha.{k}": v for k, v in common.items()}
        with span("eval.trial", SpanKind.EVALUATOR, **attributes) as current:
            try:
                run_id = self.executor(spec)
            except Exception as error:
                self.record("trial", status="interrupted", error=str(error)[:500], **common)
                raise
            outcome = load_outcome(self.workbench.repo, self.workbench.runs_dir, run_id)
            score = score_case(outcome, self.labels[case.case_id], self._assessments(outcome))
            annotate(
                current,
                **{
                    "episalpha.run_id": run_id,
                    "episalpha.state": outcome.state.value,
                    **{f"episalpha.metric.{k}": str(v) for k, v in score.metrics.items()},
                },
            )
        record = self.workbench.repo.get_run(run_id)
        self.record(
            "trial",
            status="scored",
            run_id=run_id,
            state=outcome.state.value,
            snapshot_id=record.snapshot_id if record else None,
            model_requests=outcome.model_requests,
            score=as_json(score),
            **common,
        )
        return score

    def _assessments(self, outcome: Any) -> dict[str, str]:
        found = {}
        for claim in outcome.claims:
            current = self.workbench.repo.current_assessment(claim.claim_id)
            if current is not None:
                found[claim.claim_id] = current.judgment.value
        return found

    def check_budget(self, key: tuple[str, str, str]) -> None:
        cap = self.workbench.settings.limits.campaign_requests_per_day
        if cap is None:
            return
        today = self.now().date().isoformat()
        spent = sum(
            r.get("model_requests", 0)
            for r in self.ledger.records()
            if r["kind"] == "trial" and r["at"].startswith(today)
        )
        if spent + self.workbench.settings.limits.max_model_requests > cap:
            self.record(
                "paused",
                reason="the daily request cap would be crossed by the next trial",
                spent_today=spent,
                cap=cap,
                next_trial=list(key),
            )
            raise CampaignPaused(f"paused: {spent} of {cap} requests spent today")

    def decide(
        self, directory: Path, gates: tuple[dict[str, Any], ...], candidate_id: str | None
    ) -> CampaignResult:
        passed = bool(gates) and all(gate["passed"] for gate in gates)
        decision = "challenger_passed" if passed else "baseline_retained"
        with span(
            "eval.decision",
            SpanKind.EVALUATOR,
            **{"episalpha.campaign_id": self.campaign_id, "episalpha.decision": decision},
        ):
            if not any(r["kind"] == "decision" for r in self.ledger.records()):
                self.record(
                    "decision",
                    decision=decision,
                    candidate_id=candidate_id,
                    gates=list(gates),
                    note="the baseline stays active; promotion is an explicit owner action",
                )
        return CampaignResult(
            campaign_id=self.campaign_id,
            status="decided",
            directory=directory,
            decision=decision,
            gates=gates,
            candidate_id=candidate_id,
        )


# --- the decision rule, gate by gate --------------------------------------------------------


def _worse(before: Ratio, after: Ratio) -> bool:
    if before.value is None and after.value is None:
        return False
    if before.value is None or after.value is None:
        return True  # not comparable: never counted as "no loss"
    return after.value < before.value


def _quality(base: Sequence[CaseScore], chal: Sequence[CaseScore]) -> tuple[bool, str]:
    b, c = pool(base), pool(chal)
    lost = [m for m in RULE["quality_metrics"] if _worse(b.metrics[m], c.metrics[m])]
    more_unsupported = c.unsupported_claims > b.unsupported_claims
    detail = ", ".join(f"{m} {b.metrics[m]} -> {c.metrics[m]}" for m in RULE["quality_metrics"])
    return not lost and not more_unsupported, (
        f"{detail}; unsupported claims {b.unsupported_claims} -> {c.unsupported_claims}"
    )


def _violations(scores: Sequence[CaseScore]) -> int:
    return sum(
        s.temporal_violations + s.boundary_violations + s.reference_violations for s in scores
    )


def validation_gates(
    base: Sequence[CaseScore], chal: Sequence[CaseScore], hard_budget: int
) -> list[dict[str, Any]]:
    """Plan section 12.3 rules 1-4, each reported on its own. No weighted score."""
    gates: list[dict[str, Any]] = []

    def gate(name: str, passed: bool, detail: str) -> None:
        gates.append({"gate": name, "passed": passed, "detail": detail})

    gate("0 validation cases exist", bool(base), f"{len(base)} paired cases")
    vb, vc = _violations(base), _violations(chal)
    gate("1 zero violations", vb == vc == 0, f"baseline {vb}, challenger {vc}")
    gate("2 no quality loss", *_quality(base, chal))
    found_b = {(s.case_id, x) for s in base for x in s.recovered_contradictions}
    found_c = {(s.case_id, x) for s in chal for x in s.recovered_contradictions}
    new, lost = sorted(found_c - found_b), sorted(found_b - found_c)
    gate(
        "3 contradiction gain",
        len(new) >= RULE["min_new_contradictions"] and not lost,
        f"new {len(new)}, lost {len(lost)}",
    )
    ratio = Decimal(RULE["max_request_ratio"])
    requests_ok = latency_ok = True
    detail = "no cases"
    if base and chal:
        mean_b = Decimal(sum(s.model_requests for s in base)) / len(base)
        mean_c = Decimal(sum(s.model_requests for s in chal)) / len(chal)
        lat_b = [s.latency_seconds for s in base]
        lat_c = [s.latency_seconds for s in chal]
        known = None not in lat_b and None not in lat_c
        med_b = Decimal(str(statistics.median(lat_b))) if known else None  # type: ignore[type-var]
        med_c = Decimal(str(statistics.median(lat_c))) if known else None  # type: ignore[type-var]
        requests_ok = mean_c <= ratio * mean_b
        latency_ok = med_b is not None and med_c is not None and med_c <= ratio * med_b
        detail = f"mean requests {mean_b} -> {mean_c}; median latency {med_b} -> {med_c} s"
    within = all(
        s.model_requests <= hard_budget and s.state is not RunState.TIMED_OUT
        for s in [*base, *chal]
    )
    gate("4 cost within 1.5x and hard budgets", requests_ok and latency_ok and within, detail)
    return gates


def final_gate(base: Sequence[CaseScore], chal: Sequence[CaseScore]) -> dict[str, Any]:
    """Rule 5: on the final-check cases, valid and no quality regression."""
    passed, detail = _quality(base, chal)
    violations = _violations(chal)
    return {
        "gate": "5 final check",
        "passed": bool(base) and passed and violations == 0,
        "detail": f"{len(base)} cases; challenger violations {violations}; {detail}",
    }
