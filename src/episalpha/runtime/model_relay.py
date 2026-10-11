"""The single-route model relay (plan M3-T02; amendments A3, A9, A12).

The relay is the only component that holds the provider key. The Hermes worker talks to it with
a per-run token; it forwards to exactly one configured route and fails closed on anything else.

What pinned Hermes 0.21.3 actually sends (captured through a loopback stub, M3-T02 journal):
``POST /v1/chat/completions`` with ``model``, ``messages``, ``tools``, ``max_tokens``,
``stream: true`` and ``stream_options``, plus metadata probes (``GET /v1/models``,
``POST /api/show``) that it tolerates being refused. So the relay implements one path. It calls
the provider **without** streaming and, when the worker asked to stream, replays the finished
completion as server-sent events. Nothing else is emulated.

Request rules (M3 constitution articles 4-7 and 13):

- only allowlisted body fields; ``response_format``, ``plugins``, ``models``, ``provider``,
  ``route``, ``transforms`` and anything unknown are refused, never stripped silently;
- only the configured model, so a ``:online`` variant is refused;
- no tool that turns the relay into an internet channel (``openrouter:*``, ``web_search``);
- ``max_tokens`` clamped to ``max_output_tokens_per_call`` and always present;
- one upstream request at a time;
- every upstream attempt, retries included, spends one unit of the run-global request budget;
  the counter survives stages because the runner hands it back (``requests_used``);
- only connection resets and HTTP 502/503/504 are retried, at most ``max_transport_retries``
  times. A 429 waits for ``Retry-After`` only if that fits the remaining wall time; otherwise it
  is a provider failure, never an abstention.
"""

from __future__ import annotations

import hmac
import http.client
import json
import math
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol
from urllib.parse import urlsplit

from opentelemetry.trace import Status, StatusCode

from episalpha.contracts.errors import ErrorCode
from episalpha.contracts.research import Usage
from episalpha.observability import SpanKind, TraceHandle, annotate, restore, span
from episalpha.settings import Limits, ProviderRoute

CHAT_PATHS = frozenset({"/v1/chat/completions", "/chat/completions"})
FORWARDED_FIELDS = frozenset(
    {"model", "messages", "tools", "tool_choice", "max_tokens", "temperature", "top_p", "seed"}
)
"""Body fields forwarded upstream. ``reasoning`` is absent: M0-T04 did not verify it."""
RELAY_FIELDS = frozenset({"stream", "stream_options"})
"""Consumed by the relay itself (it streams the finished answer back), never forwarded."""
FORBIDDEN_TOOL_NAMES = frozenset({"web_search"})
TRANSIENT_STATUSES = frozenset({502, 503, 504})
CANCELLED_STATUS = 499


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    def __call__(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> TransportResponse: ...

    def close(self) -> None: ...


class HttpTransport:
    """Stdlib HTTP(S) client whose in-flight connection :meth:`close` can abort."""

    def __init__(self) -> None:
        self._connection: http.client.HTTPConnection | None = None

    def __call__(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> TransportResponse:
        parts = urlsplit(url)
        factory = (
            http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        )
        connection = factory(parts.netloc, timeout=timeout)
        self._connection = connection
        try:
            connection.request("POST", parts.path, body=body, headers=headers)
            response = connection.getresponse()
            return TransportResponse(
                status=response.status,
                headers={key: value for key, value in response.getheaders()},
                body=response.read(),
            )
        finally:
            connection.close()
            self._connection = None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()


@dataclass(frozen=True)
class RelayResponse:
    """What the worker receives. Relay-made errors never carry the provider's body."""

    status: int
    content_type: str
    body: bytes
    error_code: ErrorCode | None = None


@dataclass
class StagePolicy:
    """Per-stage request cap. The stage's last allowed request forces its submit tool.

    This is where structured output is forced (A3): the route honours a named ``tool_choice``
    (M0-T04) but not ``"required"`` (M3-T03 probe), so earlier turns explore with ``auto`` and
    the final turn must call ``final_tool``.
    """

    max_requests: int
    final_tool: str
    used: int = 0


class RelayRefusal(Exception):
    def __init__(self, code: ErrorCode, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def prepare(
    body: bytes, route: ProviderRoute, limits: Limits, *, no_fallbacks: bool
) -> tuple[dict[str, Any], bool]:
    """Validate a worker request. Returns the upstream body and whether to stream back."""
    if len(body) > limits.max_request_body_bytes:
        raise RelayRefusal(
            ErrorCode.BUDGET_EXCEEDED,
            f"request body is {len(body)} bytes; max_request_body_bytes is "
            f"{limits.max_request_body_bytes}",
        )
    try:
        request: Any = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RelayRefusal(ErrorCode.INVALID_REQUEST, "request body is not JSON") from None
    if not isinstance(request, dict):
        raise RelayRefusal(ErrorCode.INVALID_REQUEST, "request body must be a JSON object")
    unknown = sorted(set(request) - FORWARDED_FIELDS - RELAY_FIELDS)
    if unknown:
        raise RelayRefusal(
            ErrorCode.NOT_AUTHORIZED, f"fields {unknown} are not forwarded by this relay"
        )
    if request.get("model") != route.model_id:
        raise RelayRefusal(
            ErrorCode.NOT_AUTHORIZED,
            f"model {request.get('model')!r} is not the configured route {route.model_id!r}",
        )
    for tool in request.get("tools") or []:
        kind = str(tool.get("type", "")) if isinstance(tool, dict) else ""
        function = tool.get("function") if isinstance(tool, dict) else None
        name = str(function.get("name", "")) if isinstance(function, dict) else ""
        if kind != "function" or name.startswith("openrouter:") or name in FORBIDDEN_TOOL_NAMES:
            raise RelayRefusal(
                ErrorCode.NOT_AUTHORIZED, f"tool {kind or name!r} would reach the internet"
            )
    upstream = {key: value for key, value in request.items() if key in FORWARDED_FIELDS}
    asked = request.get("max_tokens")
    cap = limits.max_output_tokens_per_call
    upstream["max_tokens"] = min(asked, cap) if isinstance(asked, int) and asked > 0 else cap
    if no_fallbacks:
        upstream["provider"] = {"allow_fallbacks": False}
    return upstream, bool(request.get("stream"))


def to_sse(completion: Mapping[str, Any]) -> bytes:
    """Replay a finished chat completion as the chunk stream an OpenAI client expects."""
    choice = (completion.get("choices") or [{}])[0]
    message = dict(choice.get("message") or {})
    delta: dict[str, Any] = {"role": message.get("role", "assistant")}
    for key in ("content", "reasoning"):
        if message.get(key) is not None:
            delta[key] = message[key]
    if message.get("tool_calls"):
        delta["tool_calls"] = [
            {**call, "index": index} for index, call in enumerate(message["tool_calls"])
        ]
    base = {
        "id": completion.get("id", "relay"),
        "object": "chat.completion.chunk",
        "created": completion.get("created", 0),
        "model": completion.get("model", ""),
    }
    chunks = [
        {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {
            **base,
            "choices": [{"index": 0, "delta": {}, "finish_reason": choice.get("finish_reason")}],
            "usage": completion.get("usage"),
        },
    ]
    events = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    return (events + "data: [DONE]\n\n").encode()


def _offers(upstream: Mapping[str, Any], tool_name: str) -> bool:
    return any(
        isinstance(tool, dict) and (tool.get("function") or {}).get("name") == tool_name
        for tool in upstream.get("tools") or []
    )


def _error(code: ErrorCode, message: str, status: int = 400) -> RelayResponse:
    body = json.dumps({"error": {"code": code.value, "message": message}}).encode()
    return RelayResponse(status, "application/json", body, code)


def _refused(code: ErrorCode, message: str, status: int = 400) -> RelayResponse:
    """A refusal before any upstream call, logged as one metadata-only span (article 13)."""
    with span(
        "relay.refusal",
        SpanKind.CHAIN,
        **{
            "episalpha.error_code": code.value,
            "episalpha.reason": message[:200],
            "http.response.status_code": status,
        },
    ) as current:
        current.set_status(Status(StatusCode.ERROR, code.value))
    return _error(code, message, status)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    for key, value in headers.items():
        if key.lower() == "retry-after":
            try:
                return max(0.0, float(value))
            except ValueError:
                return None
    return None


class ModelRelay:
    """One run's relay: one route, one budget, one upstream request at a time."""

    def __init__(
        self,
        route: ProviderRoute,
        limits: Limits,
        run_token: str,
        *,
        transport: Transport | None = None,
        no_fallbacks: bool = False,
        requests_used: int = 0,
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if route.endpoint_url is None or route.model_id is None:
            raise ValueError("the relay needs provider.endpoint_url and provider.model_id")
        self.route = route
        self.limits = limits
        self._token = run_token
        self._transport: Transport = transport if transport is not None else HttpTransport()
        self._no_fallbacks = no_fallbacks
        self.requests_used = requests_used
        self._deadline = deadline
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self.cancelled = False
        self.failure: ErrorCode | None = None
        self._served_by: list[str] = []
        self.trace: TraceHandle | None = None
        self.stage_policy: StagePolicy | None = None
        """Where the current stage's spans live; set by the runtime, used by server threads."""
        self._prompt: int | None = 0
        self._completion: int | None = 0

    # --- accounting ------------------------------------------------------------------------

    @property
    def usage(self) -> Usage:
        return Usage(
            model_requests=self.requests_used,
            prompt_tokens=self._prompt,
            completion_tokens=self._completion,
        )

    @property
    def served_by(self) -> tuple[str, ...]:
        return tuple(self._served_by)

    def _record_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            self._prompt = self._completion = None
            return
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        self._prompt = (
            self._prompt + prompt if self._prompt is not None and isinstance(prompt, int) else None
        )
        self._completion = (
            self._completion + completion
            if self._completion is not None and isinstance(completion, int)
            else None
        )

    def _scrub(self, text: str) -> str:
        secret = self.route.credential()
        return text.replace(secret, "***") if secret else text

    # --- control ---------------------------------------------------------------------------

    def cancel(self) -> None:
        """Refuse further requests and abort the in-flight one."""
        self.cancelled = True
        self._transport.close()

    def _remaining(self) -> float | None:
        return None if self._deadline is None else self._deadline - self._clock()

    def _fail(self, code: ErrorCode, message: str) -> RelayResponse:
        self.failure = code
        return _error(code, message)

    # --- the one entry point ---------------------------------------------------------------

    def forward(self, path: str, body: bytes, presented_token: str) -> RelayResponse:
        with restore(self.trace):
            return self._forward(path, body, presented_token)

    def _forward(self, path: str, body: bytes, presented_token: str) -> RelayResponse:
        if not hmac.compare_digest(presented_token.encode(), self._token.encode()):
            return _refused(ErrorCode.NOT_AUTHORIZED, "invalid run token")
        if path not in CHAT_PATHS:
            return _refused(ErrorCode.NOT_AUTHORIZED, f"{path!r} is not served", status=404)
        if self.cancelled:
            return _refused(ErrorCode.INVALID_REQUEST, "run cancelled", status=CANCELLED_STATUS)
        try:
            upstream, stream = prepare(
                body, self.route, self.limits, no_fallbacks=self._no_fallbacks
            )
        except RelayRefusal as refusal:
            return _refused(refusal.code, str(refusal), refusal.status)
        credential = self.route.credential()
        if credential is None:
            return self._fail(ErrorCode.NOT_AUTHORIZED, "the route credential is not configured")
        with self._lock:
            return self._attempts(upstream, stream, credential)

    def _attempts(self, upstream: dict[str, Any], stream: bool, credential: str) -> RelayResponse:
        encoded = json.dumps(upstream).encode()
        url = f"{str(self.route.endpoint_url).rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {credential}", "Content-Type": "application/json"}
        retries_left = self.limits.max_transport_retries
        attempt = 0
        while True:
            if self.cancelled:
                return _error(ErrorCode.INVALID_REQUEST, "run cancelled", CANCELLED_STATUS)
            if self.requests_used >= self.limits.max_model_requests:
                self.failure = ErrorCode.BUDGET_EXCEEDED
                return _refused(
                    ErrorCode.BUDGET_EXCEEDED,
                    f"model request budget of {self.limits.max_model_requests} is spent",
                )
            remaining = self._remaining()
            if remaining is not None and remaining <= 0:
                self.failure = ErrorCode.BUDGET_EXCEEDED
                return _refused(ErrorCode.BUDGET_EXCEEDED, "run wall time is spent")
            policy = self.stage_policy
            if policy is not None:
                if policy.used >= policy.max_requests:
                    return _refused(
                        ErrorCode.BUDGET_EXCEEDED,
                        f"stage request cap of {policy.max_requests} is spent",
                    )
                policy.used += 1
                if policy.used >= policy.max_requests and _offers(upstream, policy.final_tool):
                    upstream = {
                        **upstream,
                        "tool_choice": {
                            "type": "function",
                            "function": {"name": policy.final_tool},
                        },
                    }
                    encoded = json.dumps(upstream).encode()
            self.requests_used += 1
            attempt += 1
            timeout = float(self.route.request_timeout_seconds)
            if remaining is not None:
                timeout = max(1.0, min(timeout, remaining))
            outcome = self._one_attempt(url, headers, encoded, timeout, attempt, upstream)
            if isinstance(outcome, RelayResponse):
                return outcome
            if outcome is None:  # transient: connection reset or 502/503/504
                if retries_left > 0:
                    retries_left -= 1
                    continue
                return self._fail(ErrorCode.SOURCE_FAILED, "provider unavailable after retry")
            if isinstance(outcome, float):  # 429 with Retry-After
                remaining = self._remaining()
                fits = math.isfinite(outcome) and (remaining is None or outcome < remaining)
                if retries_left > 0 and fits:
                    retries_left -= 1
                    self._sleep(outcome)
                    continue
                return self._fail(
                    ErrorCode.SOURCE_FAILED,
                    "provider rate limit (HTTP 429) does not clear within the run's wall time",
                )
            return self._respond(outcome, stream)

    def _one_attempt(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
        attempt: int,
        upstream: dict[str, Any],
    ) -> RelayResponse | dict[str, Any] | float | None:
        """One upstream call in one ``model.call`` span.

        Returns the parsed completion, ``None`` for a transient failure, the ``Retry-After``
        seconds for a 429, or a final error response.
        """
        attributes: dict[str, object] = {
            "llm.model_name": self.route.model_id,
            "llm.provider": urlsplit(url).hostname,
            "episalpha.request_index": self.requests_used,
            "episalpha.attempt": attempt,
            "input.mime_type": "application/json",
            "input.value": json.dumps(upstream),
        }
        with span("model.call", SpanKind.LLM, **attributes) as current:
            try:
                response = self._transport(url, headers, body, timeout)
            except OSError as error:
                current.set_status(Status(StatusCode.ERROR, f"transport: {type(error).__name__}"))
                annotate(current, **{"episalpha.outcome": "transient"})
                if self.cancelled:
                    return _error(ErrorCode.INVALID_REQUEST, "run cancelled", CANCELLED_STATUS)
                return None
            text = self._scrub(response.body.decode("utf-8", errors="replace"))
            annotate(
                current,
                **{"http.response.status_code": response.status, "output.value": text},
            )
            if response.status in TRANSIENT_STATUSES:
                current.set_status(Status(StatusCode.ERROR, f"HTTP {response.status}"))
                annotate(current, **{"episalpha.outcome": "transient"})
                return None
            if response.status == 429:
                current.set_status(Status(StatusCode.ERROR, "HTTP 429"))
                annotate(current, **{"episalpha.outcome": "rate_limited"})
                wait = _retry_after(response.headers)
                return wait if wait is not None else float("inf")
            if response.status != 200:
                current.set_status(Status(StatusCode.ERROR, f"HTTP {response.status}"))
                annotate(current, **{"episalpha.outcome": "SOURCE_FAILED"})
                return self._fail(
                    ErrorCode.SOURCE_FAILED, f"provider answered HTTP {response.status}"
                )
            try:
                completion: Any = json.loads(text)
            except json.JSONDecodeError:
                completion = None
            if not isinstance(completion, dict) or not completion.get("choices"):
                current.set_status(Status(StatusCode.ERROR, "malformed completion"))
                return self._fail(ErrorCode.SOURCE_FAILED, "provider returned no completion")
            usage = completion.get("usage")
            self._record_usage(usage)
            served_by = completion.get("provider")
            if isinstance(served_by, str):
                self._served_by.append(served_by)
            details = (usage or {}).get("completion_tokens_details") or {}
            annotate(
                current,
                **{
                    "episalpha.outcome": "ok",
                    "episalpha.served_by": served_by,
                    "llm.token_count.prompt": (usage or {}).get("prompt_tokens"),
                    "llm.token_count.completion": (usage or {}).get("completion_tokens"),
                    "llm.token_count.total": (usage or {}).get("total_tokens"),
                    "llm.token_count.completion_details.reasoning": details.get("reasoning_tokens"),
                },
            )
            return completion

    def _respond(self, completion: dict[str, Any], stream: bool) -> RelayResponse:
        if stream:
            return RelayResponse(200, "text/event-stream", to_sse(completion))
        return RelayResponse(200, "application/json", json.dumps(completion).encode())


class RelayServer:
    """The relay's HTTP front for the worker: ``Authorization: Bearer <run token>``.

    Bind it to an address only the worker network can reach (M3-T04). GET is always 404.
    """

    def __init__(self, relay: ModelRelay, *, host: str, port: int) -> None:
        self.relay = relay
        limit = relay.limits.max_request_body_bytes

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length") or 0)
                if length > limit:
                    result = _error(ErrorCode.BUDGET_EXCEEDED, "request body too large", 413)
                else:
                    body = self.rfile.read(length)
                    auth = self.headers.get("Authorization", "")
                    token = auth.removeprefix("Bearer ").strip()
                    result = relay.forward(self.path, body, token)
                self._send(result)

            def do_GET(self) -> None:  # noqa: N802
                self._send(_error(ErrorCode.NOT_AUTHORIZED, "not served", 404))

            def _send(self, result: RelayResponse) -> None:
                self.send_response(result.status)
                self.send_header("Content-Type", result.content_type)
                self.send_header("Content-Length", str(len(result.body)))
                self.end_headers()
                self.wfile.write(result.body)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return None

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
