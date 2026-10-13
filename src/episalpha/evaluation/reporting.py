"""The experiment report (plan section 12.3, M6-T04): measured, complete, and not a score.

Built from a campaign's frozen ``manifest.json`` and append-only ``ledger.jsonl`` only, so every
number in it was measured by a trial, and every trial is in it: interrupted and failed ones too.
Each decision-rule gate is shown on its own, in the manifest's order; there is no weighted or
aggregate score. A rejected challenger is reported as the complete, valid result it is
(M6 article 8). Usage that was not reported stays ``unknown``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from episalpha.evolution.candidates import Ledger

DISCLAIMER = (
    "Research-quality experiment on a small engineering sample; not evidence of investment "
    "performance or statistical generalization."
)
UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrialRow:
    phase: str
    variant: str
    case_id: str
    attempt: int
    status: str
    """``scored`` or ``interrupted``."""
    state: str | None
    run_id: str | None
    execution_id: str
    model_requests: int | None
    latency_seconds: int | None
    metrics: dict[str, tuple[int, int]]
    error: str | None = None


@dataclass(frozen=True)
class Aggregate:
    """Pooled numerators and denominators for one phase and variant."""

    phase: str
    variant: str
    trials: int
    interrupted: int
    metrics: dict[str, tuple[int, int]]
    model_requests: int
    tokens: str
    cost: str
    latencies: tuple[int, ...]


@dataclass(frozen=True)
class Report:
    campaign_id: str
    name: str
    runtime: str
    model: str
    status: str
    """``decided``, ``paused`` or ``in progress``."""
    decision: str | None
    gates: tuple[dict[str, Any], ...]
    candidate_id: str | None
    candidate_diff: dict[str, Any] | None
    parent_harness_hash: str | None
    child_harness_hash: str | None
    trials: tuple[TrialRow, ...]
    aggregates: tuple[Aggregate, ...]
    exposed_final_cases: tuple[str, ...]
    reuse_warnings: tuple[str, ...]
    manifest: dict[str, Any]
    paused_reason: str | None = None


def list_campaigns(root: Path) -> list[Path]:
    """Campaign directories, newest frozen first (ties: campaign ID, descending)."""
    if not root.is_dir():
        return []
    found = [d for d in root.iterdir() if (d / "manifest.json").is_file()]

    def frozen(directory: Path) -> tuple[str, str]:
        records = Ledger(directory / "ledger.jsonl").records()
        return (records[0]["at"] if records else "", directory.name)

    return sorted(found, key=frozen, reverse=True)


def _final_trials(records: list[dict[str, Any]]) -> list[str]:
    return [r["case_id"] for r in records if r["kind"] == "trial" and r.get("phase") == "final"]


def build_report(directory: Path) -> Report:
    manifest = json.loads((directory / "manifest.json").read_text())
    records = Ledger(directory / "ledger.jsonl").records()
    trials = tuple(_row(r) for r in records if r["kind"] == "trial")
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_kind.setdefault(record["kind"], []).append(record)

    def first(kind: str) -> dict[str, Any] | None:
        return by_kind[kind][0] if by_kind.get(kind) else None

    decision, accepted = first("decision"), first("proposal_accepted")
    rejected, made = first("proposal_rejected"), first("materialized")
    paused = by_kind.get("paused") or []
    gates = tuple(decision["gates"]) if decision else ()
    if not gates and by_kind.get("validation_gates"):
        gates = tuple(by_kind["validation_gates"][-1]["gates"])
    status = "decided" if decision else "paused" if paused else "in progress"
    final_cases = set(manifest.get("partitions", {}).get("final", []))
    earlier = []
    for other in list_campaigns(directory.parent):
        if other == directory:
            continue
        other_records = Ledger(other / "ledger.jsonl").records()
        exposed = set(_final_trials(other_records)) & final_cases
        mine = records[0]["at"] if records else ""
        if exposed and other_records and other_records[0]["at"] <= mine:
            earlier += [
                f"{case}: final-check case already exposed in {other.name}" for case in exposed
            ]
    return Report(
        campaign_id=directory.name,
        name=manifest.get("name", directory.name),
        runtime=manifest.get("runtime", UNKNOWN),
        model=manifest.get("model") or UNKNOWN,
        status=status,
        decision=decision["decision"] if decision else None,
        gates=gates,
        candidate_id=(accepted or {}).get("candidate_id"),
        candidate_diff=(accepted or rejected or {}).get("proposal"),
        parent_harness_hash=(made or accepted or {}).get("parent_harness_hash"),
        child_harness_hash=(made or {}).get("child_harness_hash"),
        trials=trials,
        aggregates=_aggregates(trials),
        exposed_final_cases=tuple(sorted(set(_final_trials(records)))),
        reuse_warnings=tuple(sorted(earlier)),
        manifest=manifest,
        paused_reason=paused[-1]["reason"] if paused and not decision else None,
    )


def _row(record: dict[str, Any]) -> TrialRow:
    score = record.get("score") or {}
    return TrialRow(
        phase=record["phase"],
        variant=record["variant"],
        case_id=record["case_id"],
        attempt=record.get("attempt", 1),
        status=record["status"],
        state=record.get("state"),
        run_id=record.get("run_id"),
        execution_id=record["execution_id"],
        model_requests=record.get("model_requests"),
        latency_seconds=score.get("latency_seconds"),
        metrics={
            name: (value["numerator"], value["denominator"])
            for name, value in (score.get("metrics") or {}).items()
        },
        error=record.get("error"),
    )


def _aggregates(trials: tuple[TrialRow, ...]) -> tuple[Aggregate, ...]:
    keys = list(dict.fromkeys((t.phase, t.variant) for t in trials))
    out = []
    for phase, variant in keys:
        rows = [t for t in trials if (t.phase, t.variant) == (phase, variant)]
        scored = [t for t in rows if t.status == "scored"]
        names = list(dict.fromkeys(name for t in scored for name in t.metrics))
        out.append(
            Aggregate(
                phase=phase,
                variant=variant,
                trials=len(rows),
                interrupted=len(rows) - len(scored),
                metrics={
                    name: (
                        sum(t.metrics.get(name, (0, 0))[0] for t in scored),
                        sum(t.metrics.get(name, (0, 0))[1] for t in scored),
                    )
                    for name in names
                },
                model_requests=sum(t.model_requests or 0 for t in scored),
                # The ledger does not carry token counts or prices: never estimated (article 13).
                tokens=UNKNOWN,
                cost=UNKNOWN,
                latencies=tuple(t.latency_seconds for t in scored if t.latency_seconds is not None),
            )
        )
    return tuple(out)


def _ratio(pair: tuple[int, int]) -> str:
    return f"{pair[0]}/{pair[1]}" if pair[1] else "N/A"


def render_markdown(report: Report) -> str:
    """The report as Markdown. The disclaimer comes first, always."""
    lines = [
        f"> {DISCLAIMER}",
        "",
        f"# Experiment `{report.name}` — campaign `{report.campaign_id}`",
        "",
        f"- Runtime: {report.runtime}"
        + (" ([FIXTURE] scripted output, not research)" if report.runtime == "fake" else ""),
        f"- Model: {report.model}",
        f"- Evaluator hash: `{report.manifest.get('evaluator_hash', UNKNOWN)}`",
        f"- Labels hash: `{report.manifest.get('labels_hash', UNKNOWN)}`"
        + ("" if report.manifest.get("labels_reviewed") else " (labels NOT human-validated)"),
        f"- Status: {report.status}"
        + (f" ({report.paused_reason}; re-run to resume)" if report.paused_reason else ""),
    ]
    lines += [f"- Limitation: {item}" for item in report.manifest.get("limitations", [])]
    lines += ["", "## Decision", ""]
    if report.decision == "baseline_retained":
        lines.append(
            "Challenger rejected; the baseline is retained. This is a complete, valid result."
        )
    elif report.decision == "challenger_passed":
        lines.append(
            "The challenger cleared every gate. The baseline stays active: promotion is an "
            "explicit owner action, versioned and linked to this report."
        )
    else:
        lines.append(f"No decision yet: the campaign is {report.status}.")
    lines += ["", "## Gates (frozen rule, in order; no weighted score)", ""]
    lines += [
        f"- {gate['gate']}: {'PASS' if gate['passed'] else 'FAIL'} ({gate['detail']})"
        for gate in report.gates
    ] or ["- No gate evaluated yet."]
    lines += ["", "## Candidate", ""]
    if report.candidate_diff is None:
        lines.append("No proposal recorded.")
    else:
        lines += [
            f"- Candidate: `{report.candidate_id or 'rejected at validation'}`",
            f"- Parent harness: `{report.parent_harness_hash or UNKNOWN}`",
            f"- Child harness: `{report.child_harness_hash or 'not materialized'}`",
            "",
            "```json",
            json.dumps(report.candidate_diff, indent=2, sort_keys=True),
            "```",
        ]
    lines += ["", "## Aggregates (numerator/denominator)", ""]
    for aggregate in report.aggregates:
        metrics = ", ".join(f"{k} {_ratio(v)}" for k, v in aggregate.metrics.items())
        lines.append(
            f"- {aggregate.phase} / {aggregate.variant}: {aggregate.trials} trials "
            f"({aggregate.interrupted} interrupted); {metrics or 'no scored trial'}; "
            f"model requests {aggregate.model_requests}; tokens {aggregate.tokens}; "
            f"cost {aggregate.cost}; latency s {list(aggregate.latencies)}"
        )
    lines += [
        "",
        "## Every trial",
        "",
        "| Phase | Variant | Case | Attempt | Status | State | "
        "Requests | Latency s | Metrics | Run |",
        "|---|---|---|---:|---|---|---:|---:|---|---|",
    ]
    for t in report.trials:
        metrics = "; ".join(f"{k} {_ratio(v)}" for k, v in t.metrics.items())
        status = t.status + (f": {t.error}" if t.error else "")
        lines.append(
            f"| {t.phase} | {t.variant} | {t.case_id} | {t.attempt} | {status} | "
            f"{t.state or '-'} | {t.model_requests if t.model_requests is not None else UNKNOWN} | "
            f"{t.latency_seconds if t.latency_seconds is not None else UNKNOWN} | {metrics} | "
            f"{t.run_id or '-'} |"
        )
    lines += ["", "## Final-check exposure", ""]
    lines.append(
        "Exposed (never reuse for tuning): " + ", ".join(report.exposed_final_cases)
        if report.exposed_final_cases
        else "No final-check case has been run in this campaign."
    )
    lines += [f"- WARNING {item}" for item in report.reuse_warnings]
    return "\n".join(lines) + "\n"
