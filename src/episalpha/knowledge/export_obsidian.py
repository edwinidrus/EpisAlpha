"""One-way, byte-stable Obsidian vault for one run (plan M5-T03, acceptance row A15).

Layout under the chosen vault::

    generated/<run_id>/{thesis,claims,spans,documents,hypotheses,relations}/<stable_id>.md
    generated/<run_id>/manifest.json      every file's SHA-256
    annotations/                          the owner's notes: created once, never written again

- **Derived, never canonical.** Notes are rendered from :class:`RunKnowledge` (the verified
  replay); nothing is ever read back from the vault into the application.
- **Scope.** The run's thesis, claims, hypotheses and recorded relations, plus the snapshot
  claims, spans and documents they reach. Uncited snapshot passages are not exported.
- **Safe by construction.** Filenames are validated stable IDs; every write must resolve inside
  the vault, so neither an ID nor a symlink can move a file out of it. Source and model text is
  never put in properties and always sits in a fenced block longer than any backtick run inside
  it, so Obsidian shows it verbatim: no HTML, no links, no embeds, no tags.
- **Byte-stable.** Sorted keys and lists, ``\\n`` endings, and no clock: the export time is
  deliberately not recorded anywhere (the export span has it). The manifest carries the run's
  own ``ended_at`` instead, so an unchanged run always exports to identical bytes.
- **Never a silent overwrite.** A generated file whose hash matches neither the previous
  manifest nor the new content was edited by the owner. Its directory is then left untouched and
  the export goes to the first clean ``generated/<run_id>.<n>/``; the edits are reported.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from episalpha.contracts.errors import EpisAlphaError, ErrorCode
from episalpha.contracts.knowledge import Claim, EvidenceDocument, EvidenceSpan, Hypothesis
from episalpha.contracts.knowledge import Relation as RelationRecord
from episalpha.contracts.research import (
    RETROSPECTIVE_NOTICE,
    ResearchMode,
    RuntimeMode,
    ThesisSection,
)
from episalpha.knowledge.query import RunKnowledge, claim_passages, derivation_chain, load_run
from episalpha.observability import SpanKind, annotate, span
from episalpha.research.artifacts import _atomic_write
from episalpha.storage.repository import Repository

EXPORTER_VERSION = "1"
MANIFEST = "manifest.json"
FIXTURE_NOTICE = "[FIXTURE] fake runtime: scripted fixture output, not research"
_SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,127}")
_NOTE_PATH = re.compile(
    r"(thesis|claims|spans|documents|hypotheses|relations)/[a-z0-9][a-z0-9_.-]{0,127}\.md"
)


def safe_name(identifier: str) -> str:
    """The identifier itself, if it is safe as one path component; never a transformed title."""
    if not _SAFE_NAME.fullmatch(identifier):
        raise ValueError(f"{identifier!r} cannot name a file: stable IDs only")
    return identifier


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- Markdown and properties -------------------------------------------------------------------


def _scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        return json.dumps(value.isoformat())
    if isinstance(value, Decimal | str):
        return json.dumps(str(value), ensure_ascii=False)  # a JSON string is a YAML string
    raise TypeError(f"no property rendering for {type(value).__name__}")


def _front_matter(properties: Mapping[str, object]) -> list[str]:
    """Flat YAML properties: sorted keys, scalars or lists of quoted strings."""
    lines = ["---"]
    for key in sorted(properties):
        value = properties[key]
        if isinstance(value, list | tuple):
            lines.append(f"{key}:" if value else f"{key}: []")
            lines.extend(f"  - {_scalar(item)}" for item in value)
        else:
            lines.append(f"{key}: {_scalar(value)}")
    return [*lines, "---", ""]


def _fenced(text: str) -> list[str]:
    """Untrusted text, verbatim and inert: a fence longer than any backtick run inside it."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}text", text, fence, ""]


def _title(section: ThesisSection) -> str:
    return section.value.replace("_", " ").capitalize()


def _when(moment: datetime | None) -> str:
    return moment.isoformat() if moment is not None else "unknown"


def _period(start: datetime | None, end: datetime | None) -> str:
    return f"{start.date()}..{end.date()}" if start and end else "unknown"


# --- notes -------------------------------------------------------------------------------------


class _Vault:
    """The notes for one run under ``base`` (``generated/<name>``, vault-relative)."""

    def __init__(self, knowledge: RunKnowledge, base: str) -> None:
        self.k = knowledge
        self.base = base
        cited = {s for c in knowledge.claims.values() for s in c.span_ids}
        cited |= {s for r in knowledge.relations for s in r.evidence_span_ids}
        self.spans = {i: knowledge.spans[i] for i in sorted(cited) if i in knowledge.spans}
        documents = sorted({s.document_id for s in self.spans.values()})
        self.documents = {i: knowledge.documents[i] for i in documents if i in knowledge.documents}
        self.claims = dict(sorted(knowledge.claims.items()))
        self.hypotheses = dict(sorted(knowledge.hypotheses.items()))
        self.relations = {r.relation_id: r for r in knowledge.relations}
        self.where: dict[str, str] = {}
        if knowledge.thesis is not None:
            self.where[knowledge.thesis.thesis_id] = "thesis"
        for folder, ids in (
            ("claims", self.claims),
            ("hypotheses", self.hypotheses),
            ("spans", self.spans),
            ("documents", self.documents),
            ("relations", self.relations),
        ):
            self.where |= dict.fromkeys(ids, folder)

    def path(self, record_id: str) -> str:
        return f"{self.where[record_id]}/{safe_name(record_id)}.md"

    def target(self, record_id: str) -> str | None:
        """A quoted-property link to an exported note, else the bare ID."""
        return (
            f"[[{self.base}/{self.path(record_id)}|{record_id}]]"
            if record_id in self.where
            else None
        )

    def prop(self, record_id: str) -> str:
        return self.target(record_id) or record_id

    def link(self, record_id: str) -> str:
        return self.target(record_id) or f"`{record_id}` (not in this export)"

    def links(self, ids: Iterable[str]) -> list[str]:
        return [self.prop(i) for i in ids]

    def common(self, record_id: str, kind: str) -> dict[str, object]:
        return {
            "id": record_id,
            "kind": kind,
            "run": self.k.run_id,
            "snapshot": self.k.manifest.snapshot_id,
            "snapshot_hash": self.k.manifest.snapshot_hash,
        }

    def notices(self) -> list[str]:
        lines = []
        if self.k.runtime is RuntimeMode.FAKE:
            lines += [f"> [!warning] {FIXTURE_NOTICE}", ""]
        if self.k.research_mode is ResearchMode.HISTORICAL_RECONSTRUCTION:
            lines += [f"> [!warning] {RETROSPECTIVE_NOTICE}", ""]
        if not self.k.persisted:
            lines += ["> [!danger] Validation rejected these records; never persisted.", ""]
        return lines

    def status_of(self, record_id: str) -> str:
        claim = self.k.claims.get(record_id)
        epistemic = claim.epistemic_status.value if claim else "hypothesized"
        return f"{epistemic} · {self.k.review(record_id)}"

    # --- one renderer per record kind ----------------------------------------------------------

    def thesis(self) -> str:
        thesis = self.k.thesis
        assert thesis is not None
        claims = sorted({i for a in thesis.assertions for i in a.claim_ids})
        hypotheses = sorted({i for a in thesis.assertions for i in a.hypothesis_ids})
        lines = _front_matter(
            self.common(thesis.thesis_id, "thesis")
            | {
                "status": self.k.state.value,
                "stance": thesis.stance.value,
                "research_mode": thesis.research_mode.value,
                "research_cutoff": thesis.research_cutoff,
                "horizon_trading_days": thesis.horizon_trading_days,
                "harness": thesis.harness_id,
                "model": thesis.model_identifier,
                "runtime": self.k.runtime.value,
                "created_at": thesis.created_at,
                "executed_at": self.k.executed_at,
                "ended_at": self.k.ended_at,
                "claims": self.links(claims),
                "hypotheses": self.links(hypotheses),
            }
        )
        lines += [f"# Thesis `{thesis.thesis_id}`", "", *self.notices()]
        lines += [f"Stance: **{thesis.stance.value}**", ""]
        for section in ThesisSection:
            assertions = [a for a in thesis.assertions if a.section is section]
            if not assertions:
                continue
            lines += [f"## {_title(section)}", ""]
            for assertion in assertions:
                lines += [f"### `{assertion.assertion_id}`", "", *_fenced(assertion.text)]
                lines += [
                    f"- {kind}: {self.link(i)} · {self.status_of(i)}"
                    for kind, ids in (
                        ("claim", assertion.claim_ids),
                        ("hypothesis", assertion.hypothesis_ids),
                    )
                    for i in ids
                ]
                lines.append("")
        lines += ["## Missing information", ""]
        for item in thesis.missing_information:
            lines += _fenced(item)
        lines += [] if thesis.missing_information else ["None recorded.", ""]
        lines += ["## Next inquiry", "", *_fenced(thesis.next_inquiry)]
        return "\n".join(lines)

    def claim(self, claim: Claim) -> str:
        contradictions = [r for r in self.relations.values() if r.predicate.value == "CONTRADICTS"]
        contradicts = [r.target_id for r in contradictions if r.source_id == claim.claim_id]
        contradicted_by = [r.source_id for r in contradictions if r.target_id == claim.claim_id]
        relations = [
            r.relation_id
            for r in self.relations.values()
            if claim.claim_id in (r.source_id, r.target_id)
        ]
        fact = claim.numeric_fact
        inputs = claim.derivation.input_claim_ids if claim.derivation else ()
        lines = _front_matter(
            self.common(claim.claim_id, "claim")
            | {
                "created_by_run": claim.run_id,
                "epistemic_status": claim.epistemic_status.value,
                "status": self.k.review(claim.claim_id),
                "created_at": claim.created_at,
                "value": fact.value if fact else None,
                "period_start": fact.period_start if fact else None,
                "period_end": fact.period_end if fact else None,
                "spans": self.links(claim.span_ids),
                "derived_from": self.links(inputs),
                "contradicts": self.links(contradicts),
                "contradicted_by": self.links(contradicted_by),
                "relations": self.links(relations),
            }
        )
        lines += [f"# Claim `{claim.claim_id}`", "", *self.notices()]
        lines += [
            f"Epistemic status: **{claim.epistemic_status.value}** · semantic review: "
            f"**{self.k.review(claim.claim_id)}**",
            "",
            "Statement:",
            "",
            *_fenced(claim.statement),
            "Attribution:",
            "",
            *_fenced(claim.attribution),
        ]
        if fact is not None:
            lines += ["## Numeric fact", ""]
            lines += _fenced(
                f"metric: {fact.metric}\nvalue: {fact.value}\nunit: {fact.unit}\n"
                f"period: {_period(fact.period_start, fact.period_end)}\n"
                f"accounting basis: {fact.accounting_basis}\nsource context: {fact.source_context}"
            )
        chain = derivation_chain(self.k, claim)
        if chain is not None:
            lines += ["## Derivation", ""]
            rows = [f"{chain.method}@{chain.method_version}"]
            rows += [
                f"input {i.claim_id} = {i.value if i.value is not None else 'unknown'} "
                f"{i.unit or ''} ({_period(i.period_start, i.period_end)})"
                for i in chain.inputs
            ]
            recomputed = f"{chain.value} {chain.unit}" if chain.value is not None else "unavailable"
            rows += [f"recomputed = {recomputed}", f"claimed = {chain.claimed}"]
            lines += _fenced("\n".join(rows))
            if chain.error is not None:
                lines += ["> [!danger] Cannot be recomputed by the registered derivation.", ""]
                lines += _fenced(chain.error)
            elif chain.matches is False:
                lines += ["> [!danger] The recomputed value does not match the claim.", ""]
            elif chain.matches:
                lines += ["The registry's recomputed value matches the claimed value.", ""]
            lines += [f"- input: {self.link(i)}" for i in inputs] + [""]
        lines += ["## Evidence", ""]
        passages = claim_passages(self.k, claim.claim_id)
        for passage in passages:
            via = (
                "" if passage.cited_by == claim.claim_id else f" via {self.link(passage.cited_by)}"
            )
            lines.append(
                f"- {self.link(passage.span.span_id)} in {self.link(passage.span.document_id)}{via}"
            )
        lines += [] if passages else ["- none: no passage cited"]
        lines.append("")
        for title, ids in (
            ("Contradicts", contradicts),
            ("Contradicted by", contradicted_by),
            ("Relations", relations),
        ):
            if ids:
                lines += [f"## {title}", "", *(f"- {self.link(i)}" for i in ids), ""]
        return "\n".join(lines)

    def span(self, span_: EvidenceSpan) -> str:
        cited_by = [i for i, c in self.claims.items() if span_.span_id in c.span_ids]
        lines = _front_matter(
            self.common(span_.span_id, "evidence_span")
            | {
                "document": self.prop(span_.document_id),
                "start_offset": span_.start_offset,
                "end_offset": span_.end_offset,
                "cited_by": self.links(cited_by),
            }
        )
        lines += [f"# Span `{span_.span_id}`", "", "Exact quote:", "", *_fenced(span_.exact_quote)]
        lines += ["Locator:", "", *_fenced(span_.section_locator or "none recorded")]
        lines += [f"Document: {self.link(span_.document_id)}", "", "## Cited by", ""]
        lines += [f"- {self.link(i)}" for i in cited_by] + [""]
        return "\n".join(lines)

    def document(self, document: EvidenceDocument) -> str:
        spans = [i for i, s in self.spans.items() if s.document_id == document.document_id]
        family = [
            i
            for i, d in self.documents.items()
            if d.source_family_id == document.source_family_id and i != document.document_id
        ]
        revises = document.revises_document_id
        lines = _front_matter(
            self.common(document.document_id, "evidence_document")
            | {
                "source_family": document.source_family_id,
                "availability_basis": document.availability_basis.value,
                "published_at": document.published_at,
                "public_available_at": document.public_available_at,
                "ingested_at": document.ingested_at,
                "payload_hash": document.payload_hash,
                "parsed_text_hash": document.parsed_text_hash,
                "revises": self.prop(revises) if revises else None,
                "spans": self.links(spans),
            }
        )
        lines += [f"# Document `{document.document_id}`", ""]
        lines += _fenced(
            f"type: {document.source_type}\nuri: {document.source_uri}\n"
            f"parser: {document.parser_version}"
        )
        lines += [
            f"- published: {_when(document.published_at)}",
            f"- publicly available: {_when(document.public_available_at)} "
            f"({document.availability_basis.value})",
            f"- captured: {_when(document.ingested_at)}",
            "",
        ]
        if family:
            lines += [
                f"> [!note] Common lineage: this document and "
                f"{', '.join(self.link(i) for i in family)} come from source family "
                f"`{document.source_family_id}`. They are one source, not independent "
                "confirmations.",
                "",
            ]
        lines += ["## Spans", "", *(f"- {self.link(i)}" for i in spans), ""]
        return "\n".join(lines)

    def hypothesis(self, hypothesis: Hypothesis) -> str:
        lines = _front_matter(
            self.common(hypothesis.hypothesis_id, "hypothesis")
            | {
                "epistemic_status": "hypothesized",
                "status": self.k.review(hypothesis.hypothesis_id),
                "created_at": hypothesis.created_at,
                "horizon_trading_days": hypothesis.horizon_trading_days,
                "supporting": self.links(hypothesis.supporting_claim_ids),
                "opposing": self.links(hypothesis.opposing_claim_ids),
            }
        )
        lines += [f"# Hypothesis `{hypothesis.hypothesis_id}`", "", *self.notices()]
        lines += [f"Semantic review: **{self.k.review(hypothesis.hypothesis_id)}**", ""]
        lines += ["Mechanism:", "", *_fenced(hypothesis.mechanism), "Assumptions:", ""]
        lines += _fenced("\n".join(f"- {item}" for item in hypothesis.assumptions))
        lines += ["Falsified if:", "", *_fenced(hypothesis.falsification_condition)]
        for title, ids in (
            ("Supporting claims", hypothesis.supporting_claim_ids),
            ("Opposing claims", hypothesis.opposing_claim_ids),
        ):
            lines += [f"## {title}", "", *(f"- {self.link(i)}" for i in ids or ())]
            lines += ["- none"] if not ids else []
            lines.append("")
        return "\n".join(lines)

    def relation(self, relation: RelationRecord) -> str:
        lines = _front_matter(
            self.common(relation.relation_id, "relation")
            | {
                "created_by_run": relation.run_id,
                "predicate": relation.predicate.value,
                "epistemic_status": relation.epistemic_status.value,
                "created_at": relation.created_at,
                "valid_from": relation.valid_from,
                "valid_to": relation.valid_to,
                "source": self.prop(relation.source_id),
                "target": self.prop(relation.target_id),
                "evidence": self.links(relation.evidence_span_ids),
            }
        )
        lines += [f"# Relation `{relation.relation_id}`", ""]
        lines += [
            f"{self.link(relation.source_id)} **{relation.predicate.value}** "
            f"{self.link(relation.target_id)}",
            "",
            f"Epistemic status: **{relation.epistemic_status.value}**",
            "",
            "## Evidence",
            "",
        ]
        lines += [f"- {self.link(i)}" for i in relation.evidence_span_ids] or ["- none recorded"]
        lines.append("")
        if relation.derivation is not None:
            derivation = relation.derivation
            lines += ["## Derivation", ""]
            lines += _fenced(f"{derivation.method}@{derivation.method_version}")
            lines += [f"- input: {self.link(i)}" for i in derivation.input_claim_ids] + [""]
        return "\n".join(lines)

    def notes(self) -> dict[str, str]:
        notes: dict[str, str] = {}
        if self.k.thesis is not None:
            notes[self.path(self.k.thesis.thesis_id)] = self.thesis()
        notes |= {self.path(i): self.claim(c) for i, c in self.claims.items()}
        notes |= {self.path(i): self.hypothesis(h) for i, h in self.hypotheses.items()}
        notes |= {self.path(i): self.span(s) for i, s in self.spans.items()}
        notes |= {self.path(i): self.document(d) for i, d in self.documents.items()}
        notes |= {self.path(i): self.relation(r) for i, r in self.relations.items()}
        return dict(sorted(notes.items()))


def render_notes(knowledge: RunKnowledge, base: str) -> dict[str, str]:
    """Every note of the run, by path inside its destination; links are relative to the vault."""
    return _Vault(knowledge, base).notes()


# --- writing -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportResult:
    destination: Path
    files: int
    """Notes plus the manifest."""
    manifest_hash: str
    conflicts: tuple[str, ...]
    """Owner-edited files, relative to ``generated/``, that moved the export elsewhere."""


def _inside(root: Path, path: Path) -> Path:
    if not path.resolve().is_relative_to(root):
        raise EpisAlphaError(
            ErrorCode.NOT_AUTHORIZED, f"{path} resolves outside the vault; nothing was written"
        )
    return path


def _previous(destination: Path) -> dict[str, str] | None:
    """The previous export's file hashes, or ``None`` when its manifest is missing or invalid."""
    try:
        files = json.loads((destination / MANIFEST).read_text())["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    valid = isinstance(files, dict) and all(isinstance(v, str) for v in files.values())
    return files if valid else None


def _conflicts(root: Path, destination: Path, files: Mapping[str, bytes]) -> list[str]:
    """Generated paths that the owner edited: their hash is neither the old nor the new one."""
    _inside(root, destination)
    if not destination.exists():
        return []
    previous = _previous(destination) or {}
    found = []
    manifest = destination / MANIFEST
    if manifest.is_symlink() or (manifest.exists() and not manifest.is_file()):
        found.append(MANIFEST)
    for name, data in files.items():
        path = destination / name
        _inside(root, path.parent)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            found.append(name)
        elif path.exists():
            if _digest(path.read_bytes()) not in {previous.get(name), _digest(data)}:
                found.append(name)
    return sorted(found)


def export_knowledge(knowledge: RunKnowledge, vault: Path) -> ExportResult:
    """Write the run's notes and manifest into ``vault``; see the module docstring."""
    with span(
        "export.obsidian", SpanKind.CHAIN, **{"episalpha.run_id": knowledge.run_id}
    ) as current:
        root = vault.resolve()
        generated = _inside(root, root / "generated")
        skipped: list[str] = []
        for attempt in itertools.count(1):
            name = safe_name(knowledge.run_id if attempt == 1 else f"{knowledge.run_id}.{attempt}")
            destination = generated / name
            base = f"generated/{name}"
            files = {k: v.encode() for k, v in render_notes(knowledge, base).items()}
            conflicts = _conflicts(root, destination, files)
            if not conflicts:
                break
            skipped += [f"{name}/{conflict}" for conflict in conflicts]
        annotations = _inside(root, root / "annotations")
        if not annotations.exists():
            annotations.mkdir(parents=True)
        previous = _previous(destination) or {}
        for file_name, data in files.items():
            path = destination / file_name
            if not (path.is_file() and path.read_bytes() == data):  # unchanged keeps its mtime
                _atomic_write(_inside(root, path), data)
        for file_name, digest in previous.items():  # our own files the run no longer produces
            if file_name in files or not _NOTE_PATH.fullmatch(file_name):
                continue  # the manifest is editable: only ever delete a generated note path
            stale = destination / file_name
            if stale.is_file() and not stale.is_symlink():
                if _digest(stale.read_bytes()) == digest:
                    _inside(root, stale).unlink()
        manifest = {
            "exporter": "episalpha.obsidian",
            "exporter_version": EXPORTER_VERSION,
            "run_id": knowledge.run_id,
            "destination": base,
            "state": knowledge.state.value,
            "runtime": knowledge.runtime.value,
            "research_mode": knowledge.research_mode.value,
            "run_ended_at": knowledge.ended_at.isoformat() if knowledge.ended_at else None,
            "snapshot_id": knowledge.manifest.snapshot_id,
            "snapshot_hash": knowledge.manifest.snapshot_hash,
            "files": {file_name: _digest(data) for file_name, data in files.items()},
        }
        data = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
        if not (
            (destination / MANIFEST).is_file() and (destination / MANIFEST).read_bytes() == data
        ):
            _atomic_write(_inside(root, destination / MANIFEST), data)
        result = ExportResult(destination, len(files) + 1, _digest(data), tuple(skipped))
        annotate(
            current,
            **{
                "episalpha.destination": base,
                "episalpha.files": result.files,
                "episalpha.manifest_hash": result.manifest_hash,
                "episalpha.conflicts": len(result.conflicts),
            },
        )
    return result


def export_run(repo: Repository, runs_root: Path, run_id: str, vault: Path) -> ExportResult:
    """Export a finished run. Refuses unknown or unfinished runs; integrity errors propagate."""
    knowledge = load_run(repo, runs_root, run_id)
    if knowledge is None:
        raise EpisAlphaError(
            ErrorCode.INVALID_REQUEST,
            f"run {run_id!r} does not exist or has not finished; only finished runs are exported",
        )
    return export_knowledge(knowledge, vault)
