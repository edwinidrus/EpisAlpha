"""The Hermes runtime: host side of one research stage (plan M3-T03; A3, A5, A12, A13).

Hermes is never imported here. It exact-pins its dependencies and lives in its own
environment, so each stage runs ``worker/hermes_stage.py`` with Hermes' interpreter (a venv now,
the container in M3-T04). This module is the host half:

1. start the stage's MCP tool server (snapshot-bound tools plus ``submit_<stage>``);
2. arm the relay's stage policy: a request cap, with the last request forcing the submit tool;
3. spawn the worker with a fresh ``HERMES_HOME``, the relay URL, a per-run relay token and the
   MCP token, and **no provider key** in its environment;
4. read the worker's result file as hostile input (regular file, no symlink, size cap);
5. parse the submission host-side. Malformed output is ``invalid_output``, never accepted.

Each stage starts fresh: a new Hermes session and only the brief the host writes. No
conversation carries over from one stage to the next.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import signal
import sqlite3
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from episalpha.contracts.research import RunState, RuntimeContext, StageResult, Usage
from episalpha.observability import SpanKind, annotate, capture, span
from episalpha.runtime.candidates import SUBMIT_TOOLS, parse_candidate
from episalpha.runtime.mcp_server import McpToolServer, SubmissionSink, stage_tools
from episalpha.runtime.model_relay import ModelRelay, StagePolicy
from episalpha.runtime.port import ExitReason
from episalpha.runtime.sandbox import LaunchOutcome
from episalpha.runtime.tools import SkillProposal, ToolHost
from episalpha.settings import Limits
from episalpha.storage.objects import ObjectStore

MCP_PREFIX = "mcp__episalpha__"
MAX_WORKER_RESULT_BYTES = 65_536
STAGE_PROMPTS = {
    RunState.RESEARCHING: "researcher.md",
    RunState.CRITIQUING: "critic.md",
    RunState.SYNTHESIZING: "synthesizer.md",
}
EMPTY_SKILL_SET = hashlib.sha256(b"[]").hexdigest()


# --- the frozen harness ----------------------------------------------------------------------


@dataclass(frozen=True)
class Harness:
    """Prompts and configuration, hashed. The hash covers the skill set (A13)."""

    harness_id: str
    root: Path
    config: Mapping[str, Any]
    prompts: Mapping[RunState, str]
    harness_hash: str
    skill_set_hash: str


def skill_set_hash(skills_dir: Path | None) -> str:
    """SHA-256 over the promoted skills' names and contents; the empty set in v0.1."""
    if skills_dir is None or not skills_dir.is_dir():
        return EMPTY_SKILL_SET
    entries = [
        [path.relative_to(skills_dir).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()]
        for path in sorted(skills_dir.rglob("*"))
        if path.is_file()
    ]
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


def load_harness(root: Path, *, skills_dir: Path | None = None) -> Harness:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    config = json.loads((root / "config.json").read_text())
    prompts = {stage: (root / name).read_text() for stage, name in STAGE_PROMPTS.items()}
    if config.get("contradiction_search"):
        prompts[RunState.CRITIQUING] += (root / "contradiction_search.md").read_text()
    skills = skill_set_hash(skills_dir)
    material = [
        [path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()]
        for path in files
    ] + [["skill_set", skills]]
    return Harness(
        harness_id=f"harness.{root.name}",
        root=root,
        config=config,
        prompts=prompts,
        harness_hash=hashlib.sha256(json.dumps(material).encode()).hexdigest(),
        skill_set_hash=skills,
    )


# --- hostile worker output -------------------------------------------------------------------


def read_worker_json(path: Path, max_bytes: int = MAX_WORKER_RESULT_BYTES) -> dict[str, Any]:
    """Read one worker-written JSON file: regular file only, never through a symlink, capped."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{path.name} is not a regular file")
        if info.st_size > max_bytes:
            raise ValueError(f"{path.name} is {info.st_size} bytes; the cap is {max_bytes}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(max_bytes + 1)
    finally:
        os.close(descriptor)
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError(f"{path.name} does not hold a JSON object")
    return parsed


# --- the runtime -----------------------------------------------------------------------------


def stage_cap(limits: Limits, stage: RunState) -> int:
    return {
        RunState.RESEARCHING: limits.max_researcher_requests,
        RunState.CRITIQUING: limits.max_critic_requests,
        RunState.SYNTHESIZING: limits.max_synthesizer_requests,
    }[stage]


@dataclass
class StageReport:
    """What the host observed about one stage, for the run artifacts and the journal."""

    stage: RunState
    session_id: str
    exit_reason: str
    worker: dict[str, Any] = field(default_factory=dict)
    requests: int = 0
    tool_calls: int = 0
    seconds: float = 0.0


class HermesRuntime:
    """:class:`~episalpha.runtime.port.ResearchRuntimePort` on pinned Hermes."""

    def __init__(
        self,
        *,
        harness: Harness,
        relay: ModelRelay,
        relay_port: int,
        relay_token: str,
        model_id: str,
        limits: Limits,
        object_store: ObjectStore,
        tools_for: Callable[[RunState, RuntimeContext], ToolHost],
        brief_for: Callable[[RunState, RuntimeContext], str],
        launcher: WorkerLauncher,
        work_dir: Path,
        worker_env: Mapping[str, str] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.harness = harness
        self.relay = relay
        self.relay_port = relay_port
        self._relay_token = relay_token
        self.model_id = model_id
        self.limits = limits
        self.object_store = object_store
        self._tools_for = tools_for
        self._brief_for = brief_for
        self.launcher = launcher
        self.work_dir = work_dir
        self._worker_env = dict(worker_env or {})
        self._now = now
        self._cancelled = False
        self.reports: list[StageReport] = []
        self.proposals: list[SkillProposal] = []

    def cancel(self) -> None:
        self._cancelled = True
        self.relay.cancel()
        self.launcher.cancel()

    def run_stage(self, stage: RunState, context: RuntimeContext) -> StageResult:
        started = self._now()
        session_id = f"{context.run_id}-{stage.value.lower()}-{secrets.token_hex(4)}"
        with span(
            "sandbox.run",
            SpanKind.CHAIN,
            **{
                "episalpha.stage": stage.value,
                "episalpha.session_id": session_id,
                "episalpha.harness_id": self.harness.harness_id,
                "episalpha.harness_hash": self.harness.harness_hash,
                "episalpha.skill_set_hash": self.harness.skill_set_hash,
            },
        ) as current:
            result, report = self._run(stage, context, session_id, started)
            annotate(
                current,
                **{
                    "episalpha.exit_reason": result.exit_reason,
                    "episalpha.completed": result.completed,
                    "episalpha.requests": report.requests,
                    "episalpha.tool_calls": report.tool_calls,
                },
            )
        self.reports.append(report)
        return result

    def _run(
        self, stage: RunState, context: RuntimeContext, session_id: str, started: datetime
    ) -> tuple[StageResult, StageReport]:
        report = StageReport(stage=stage, session_id=session_id, exit_reason="")
        if self._cancelled:
            report.exit_reason = ExitReason.CANCELLED.value
            cancelled = StageResult(
                stage=stage,
                completed=False,
                exit_reason=ExitReason.CANCELLED.value,
                started_at=started,
                ended_at=self._now(),
            )
            return cancelled, report
        host = self._tools_for(stage, context)
        sink = SubmissionSink(stage)
        tools = stage_tools(host, stage, sink)
        token = secrets.token_hex(16)
        server = McpToolServer(
            tools, token=token, host=self.launcher.bind_host, port=0, trace=capture()
        )
        cap = min(stage_cap(self.limits, stage), context.remaining_model_requests)
        submit = MCP_PREFIX + SUBMIT_TOOLS[stage]
        before_requests = self.relay.requests_used
        before_usage = self.relay.usage
        failure_before = self.relay.failure
        self.relay.stage_policy = StagePolicy(max_requests=max(cap, 1), final_tool=submit)
        self.relay.trace = capture()
        server.start()
        try:
            worker, worker_exit = self._spawn(stage, context, session_id, server, token, cap)
        finally:
            server.stop()
            self.relay.stage_policy = None
            self.relay.trace = None
        self.proposals.extend(host.proposals)
        after = self.relay.usage
        usage = Usage(
            model_requests=self.relay.requests_used - before_requests,
            tool_calls=host.tool_calls_used,
            prompt_tokens=_delta(before_usage.prompt_tokens, after.prompt_tokens),
            completion_tokens=_delta(before_usage.completion_tokens, after.completion_tokens),
        )
        report.worker = worker
        report.requests = usage.model_requests
        report.tool_calls = usage.tool_calls
        report.seconds = round((self._now() - started).total_seconds(), 2)

        payload_hash = None
        if sink.payload is not None:
            encoded = json.dumps(sink.payload, sort_keys=True, separators=(",", ":")).encode()
            payload_hash = self.object_store.put(encoded)

        reason: str
        completed = False
        if worker_exit is not None:
            reason = worker_exit
        elif sink.payload is not None:
            try:
                parse_candidate(stage, sink.payload)
            except ValidationError as error:
                first = error.errors()[0]
                where = ".".join(str(part) for part in first["loc"])
                reason = f"{ExitReason.INVALID_OUTPUT.value}: {where}: {first['msg']}"
            else:
                reason, completed = ExitReason.COMPLETED.value, True
        elif self.relay.failure is not None and self.relay.failure != failure_before:
            code = self.relay.failure.value
            kind = (
                ExitReason.BUDGET_EXCEEDED
                if code == "BUDGET_EXCEEDED"
                else ExitReason.PROVIDER_FAILURE
            )
            reason = f"{kind.value}: {code}"
        elif worker.get("error"):
            reason = f"{ExitReason.INVALID_OUTPUT.value}: {worker['error']}"
        else:
            reason = f"{ExitReason.INVALID_OUTPUT.value}: no submission"
        report.exit_reason = reason
        result = StageResult(
            stage=stage,
            completed=completed,
            exit_reason=reason,
            candidate_payload_hash=payload_hash,
            tool_event_hashes=tuple(host.result_hashes),
            usage=usage,
            started_at=started,
            ended_at=self._now(),
        )
        return result, report

    def _spawn(
        self,
        stage: RunState,
        context: RuntimeContext,
        session_id: str,
        server: McpToolServer,
        token: str,
        cap: int,
    ) -> tuple[dict[str, Any], str | None]:
        """Run the worker. Returns its result file and an exit reason when it did not finish."""
        stage_dir = self.work_dir / context.run_id / stage.value.lower()
        out_dir = stage_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        # The containerised worker runs as an unprivileged uid that does not exist on the host;
        # it may write only this per-stage directory.
        out_dir.chmod(0o777)
        spec = {
            "stage": stage.value,
            "session_id": session_id,
            "system_prompt": self.harness.prompts[stage],
            "user_prompt": self._brief_for(stage, context),
            "relay_url": self.launcher.relay_url(self.relay_port),
            "relay_token": self._relay_token,
            "mcp_url": self.launcher.mcp_url(server.port),
            "mcp_token": token,
            "model": self.model_id,
            "max_iterations": max(cap, 1),
            "max_tokens": self.limits.max_output_tokens_per_call,
            "allowed_tools": sorted(MCP_PREFIX + spec.name for spec in server.tools),
            "submit_tool": MCP_PREFIX + SUBMIT_TOOLS[stage],
        }
        spec_path = stage_dir / "spec.json"
        spec_path.write_text(json.dumps(spec))
        spec_path.chmod(0o644)
        result_path = out_dir / "result.json"
        try:
            outcome = self.launcher.launch(
                stage_dir=stage_dir,
                spec_path=spec_path,
                result_path=result_path,
                relay_port=self.relay_port,
                mcp_port=server.port,
                timeout=float(max(1, context.remaining_wall_time_seconds)),
                extra_env=self._worker_env,
            )
        except (OSError, RuntimeError) as error:
            return {"error": f"WORKER_START_FAILED: {error}"}, (
                f"{ExitReason.PROVIDER_FAILURE.value}: worker did not start"
            )
        exit_reason: str | None = None
        if outcome.timed_out:
            exit_reason = ExitReason.TIMEOUT.value
        if outcome.cancelled or self._cancelled:
            exit_reason = ExitReason.CANCELLED.value
        try:
            worker = read_worker_json(result_path)
        except (OSError, ValueError) as error:
            worker = {"error": f"RESULT_UNREADABLE: {type(error).__name__}"}
        home = outcome.home_report or {
            "home_files": worker.get("worker_home_files", []),
            "state_db_rows": worker.get("worker_state_db_rows"),
        }
        files = [str(name) for name in home.get("home_files", [])]
        rows = home.get("state_db_rows")
        worker["home_files"] = files[:50]
        worker["state_db_rows"] = rows
        worker["learning_writes"] = [
            name for name in files if name.startswith(("skills/", "memories/"))
        ] + (["state.db"] if rows else [])
        worker["exit_code"] = outcome.exit_code
        worker["stop_seconds"] = outcome.stop_seconds
        return worker, exit_reason


class WorkerLauncher(Protocol):
    """Where and how a stage worker runs: a local venv or the hardened container."""

    bind_host: str
    """The host address the relay and MCP servers listen on for this launcher."""

    def relay_url(self, relay_port: int) -> str: ...

    def mcp_url(self, mcp_port: int) -> str: ...

    def launch(
        self,
        *,
        stage_dir: Path,
        spec_path: Path,
        result_path: Path,
        relay_port: int,
        mcp_port: int,
        timeout: float,
        extra_env: Mapping[str, str],
    ) -> LaunchOutcome: ...

    def cancel(self) -> None: ...


class LocalLauncher:
    """Runs the worker with a local interpreter (Hermes' venv). Development and live tests only:
    no container boundary. ``HERMES_HOME`` is a fresh host directory, inspected and removed."""

    bind_host = "127.0.0.1"

    def __init__(self, command: Sequence[str], *, cwd: Path | None = None) -> None:
        self._command = list(command)
        self._cwd = cwd
        self._process: subprocess.Popen[bytes] | None = None
        self._cancelled = False

    def relay_url(self, relay_port: int) -> str:
        return f"http://127.0.0.1:{relay_port}/v1"

    def mcp_url(self, mcp_port: int) -> str:
        return f"http://127.0.0.1:{mcp_port}/mcp"

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process is not None and process.poll() is None:
            _kill(process)

    def launch(
        self,
        *,
        stage_dir: Path,
        spec_path: Path,
        result_path: Path,
        relay_port: int,
        mcp_port: int,
        timeout: float,
        extra_env: Mapping[str, str],
    ) -> LaunchOutcome:
        home = Path(tempfile.mkdtemp(prefix="hermes-home-", dir=stage_dir))
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "HERMES_HOME": str(home),
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            **extra_env,
        }
        started = time.monotonic()
        process = subprocess.Popen(
            [*self._command, str(spec_path), str(result_path)],
            cwd=self._cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._process = process
        timed_out = False
        stop_seconds: float | None = None
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stopping = time.monotonic()
            _kill(process)
            stop_seconds = round(time.monotonic() - stopping, 2)
        finally:
            self._process = None
        files = sorted(
            path.relative_to(home).as_posix() for path in home.rglob("*") if path.is_file()
        )
        report = {"home_files": files, "state_db_rows": _state_rows(home / "state.db")}
        shutil.rmtree(home, ignore_errors=True)
        return LaunchOutcome(
            exit_code=process.returncode,
            timed_out=timed_out,
            cancelled=self._cancelled,
            seconds=round(time.monotonic() - started, 2),
            stop_seconds=stop_seconds,
            home_report=report,
        )


def _state_rows(path: Path) -> int | None:
    """Session and message rows in a worker's ``state.db``; ``None`` when absent or unreadable.

    Pinned Hermes creates an empty ``state.db`` on import. Rows would mean it persisted a
    conversation, which the lockdown forbids.
    """
    if not path.is_file() or path.is_symlink():
        return None
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            total = 0
            for table in ("sessions", "messages"):
                total += int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            return total
    except sqlite3.Error:
        return None


def _kill(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=10)


def _delta(before: int | None, after: int | None) -> int | None:
    return after - before if before is not None and after is not None else None
