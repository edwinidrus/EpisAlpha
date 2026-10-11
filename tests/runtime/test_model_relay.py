"""M3-T02 — the single-route model relay.

The provider is a scripted in-process transport: nothing here touches the network. Request
shapes come from what pinned Hermes 0.21.3 actually sent (captured in the M3-T02 journal):
``POST /v1/chat/completions`` with ``model``, ``messages``, ``tools``, ``max_tokens``,
``stream: true`` and ``stream_options``.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from episalpha.contracts.errors import ErrorCode
from episalpha.observability import configure_tracing, shutdown_tracing
from episalpha.runtime.model_relay import ModelRelay, RelayServer, StagePolicy, TransportResponse
from episalpha.settings import Limits, ProviderRoute, Settings

MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
TOKEN = "run-token-0123456789abcdef"
SECRET = "sk-or-v1-relay-test-secret-value"
ROUTE = ProviderRoute(
    model_id=MODEL,
    endpoint_url="https://openrouter.ai/api/v1",
    api_key_env="ENV:RELAY_TEST_KEY",
)
LOCK = Path(__file__).resolve().parents[2] / "config" / "runtime.lock.json"


def completion(content: str = "ok", usage: bool = True, provider: str = "Nvidia") -> bytes:
    body: dict[str, Any] = {
        "id": "gen-1",
        "object": "chat.completion",
        "model": MODEL,
        "provider": provider,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    if usage:
        body["usage"] = {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "completion_tokens_details": {"reasoning_tokens": 3},
        }
    return json.dumps(body).encode()


class Provider:
    """Scripted upstream: each call pops the next response (or raises it)."""

    def __init__(self, *responses: TransportResponse | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.delay = 0.0

    def __call__(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> TransportResponse:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            self.calls.append({"url": url, "headers": headers, "body": json.loads(body)})
            time.sleep(self.delay)
            item = self.responses.pop(0) if self.responses else ok()
            if isinstance(item, Exception):
                raise item
            return item
        finally:
            self.in_flight -= 1

    def close(self) -> None:
        return None


def ok(**kwargs: Any) -> TransportResponse:
    return TransportResponse(status=200, headers={}, body=completion(**kwargs))


def request(**overrides: Any) -> bytes:
    body: dict[str, Any] = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "mcp__episalpha__echo_span", "parameters": {"type": "object"}},
            }
        ],
        "max_tokens": 1500,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body.update(overrides)
    return json.dumps(body).encode()


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELAY_TEST_KEY", SECRET)


def relay(provider: Provider, limits: Limits | None = None, **kwargs: Any) -> ModelRelay:
    return ModelRelay(
        ROUTE, limits or Limits(), TOKEN, transport=provider, sleep=lambda _: None, **kwargs
    )


PATH = "/v1/chat/completions"


# --- fail closed ---------------------------------------------------------------------------


def test_wrong_token_unknown_model_and_path_are_refused() -> None:
    provider = Provider()
    r = relay(provider)
    assert r.forward(PATH, request(), "wrong-token").error_code is ErrorCode.NOT_AUTHORIZED
    assert r.forward(PATH, request(model="openai/gpt-x"), TOKEN).error_code is (
        ErrorCode.NOT_AUTHORIZED
    )
    assert r.forward("/v1/embeddings", request(), TOKEN).error_code is ErrorCode.NOT_AUTHORIZED
    assert r.forward("/api/v1/models", b"", TOKEN).status == 404
    assert provider.calls == []


@pytest.mark.parametrize(
    "override",
    [
        {"response_format": {"type": "json_object"}},
        {"plugins": [{"id": "web"}]},
        {"models": [MODEL, "other/model"]},
        {"provider": {"allow_fallbacks": True}},
        {"route": "fallback"},
        {"transforms": ["middle-out"]},
        {"model": "nvidia/nemotron-3-ultra-550b-a55b:online"},
        {"tools": [{"type": "function", "function": {"name": "openrouter:web_search"}}]},
        {"tools": [{"type": "function", "function": {"name": "web_search"}}]},
        {"tools": [{"type": "openrouter:web_search"}]},
    ],
)
def test_internet_channels_are_refused_before_any_upstream_call(override: dict[str, Any]) -> None:
    provider = Provider()
    result = relay(provider).forward(PATH, request(**override), TOKEN)
    assert result.status == 400
    assert result.error_code is ErrorCode.NOT_AUTHORIZED
    assert provider.calls == []


def test_upstream_body_is_the_allowlist_plus_the_relays_own_fields() -> None:
    provider = Provider()
    relay(provider, no_fallbacks=True).forward(PATH, request(temperature=0.2), TOKEN)
    (call,) = provider.calls
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert set(call["body"]) == {
        "model",
        "messages",
        "tools",
        "max_tokens",
        "temperature",
        "provider",
    }
    assert call["body"]["provider"] == {"allow_fallbacks": False}
    assert "response_format" not in call["body"]
    assert "stream" not in call["body"]
    assert call["headers"]["Authorization"] == f"Bearer {SECRET}"


def test_oversize_body_is_refused() -> None:
    provider = Provider()
    limits = Limits(max_request_body_bytes=1024, max_tool_result_bytes=512)
    big = request(messages=[{"role": "user", "content": "x" * 2000}])
    result = relay(provider, limits).forward(PATH, big, TOKEN)
    assert result.error_code is ErrorCode.BUDGET_EXCEEDED
    assert provider.calls == []


def test_max_tokens_is_clamped_and_always_present() -> None:
    provider = Provider()
    r = relay(provider, Limits(max_output_tokens_per_call=4000))
    r.forward(PATH, request(max_tokens=50_000), TOKEN)
    body = json.loads(request())
    del body["max_tokens"]
    r.forward(PATH, json.dumps(body).encode(), TOKEN)
    assert [call["body"]["max_tokens"] for call in provider.calls] == [4000, 4000]


# --- budgets -------------------------------------------------------------------------------


def test_request_budget_is_global_and_never_reset() -> None:
    provider = Provider()
    r = relay(provider, Limits(max_model_requests=3, max_transport_retries=1))
    for _stage in ("RESEARCHING", "CRITIQUING", "SYNTHESIZING"):
        assert r.forward(PATH, request(), TOKEN).status == 200
    exhausted = r.forward(PATH, request(), TOKEN)
    assert exhausted.error_code is ErrorCode.BUDGET_EXCEEDED
    assert len(provider.calls) == 3
    assert r.requests_used == 3


def test_relay_resumes_a_persisted_budget() -> None:
    provider = Provider()
    r = relay(provider, Limits(max_model_requests=3), requests_used=3)
    assert r.forward(PATH, request(), TOKEN).error_code is ErrorCode.BUDGET_EXCEEDED
    assert provider.calls == []


def test_transient_failures_retry_and_retries_count() -> None:
    provider = Provider(TransportResponse(status=503, headers={}, body=b"busy"), ok())
    r = relay(provider, Limits(max_model_requests=4, max_transport_retries=1))
    assert r.forward(PATH, request(), TOKEN).status == 200
    assert r.requests_used == 2


def test_connection_reset_is_transient() -> None:
    provider = Provider(ConnectionResetError("reset"), ok())
    assert relay(provider).forward(PATH, request(), TOKEN).status == 200


def test_retries_are_bounded() -> None:
    busy = TransportResponse(status=502, headers={}, body=b"bad gateway")
    provider = Provider(busy, busy, busy)
    r = relay(provider, Limits(max_model_requests=8, max_transport_retries=1))
    result = r.forward(PATH, request(), TOKEN)
    assert result.error_code is ErrorCode.SOURCE_FAILED
    assert len(provider.calls) == 2
    assert r.failure is ErrorCode.SOURCE_FAILED


def test_non_transient_upstream_error_is_not_retried() -> None:
    provider = Provider(TransportResponse(status=400, headers={}, body=b'{"error": "bad"}'))
    result = relay(provider).forward(PATH, request(), TOKEN)
    assert result.error_code is ErrorCode.SOURCE_FAILED
    assert len(provider.calls) == 1


def test_429_beyond_the_wall_time_is_a_provider_failure_not_an_abstention() -> None:
    limited = TransportResponse(status=429, headers={"Retry-After": "120"}, body=b"slow down")
    provider = Provider(limited, ok())
    r = relay(provider, deadline=time.monotonic() + 10)
    result = r.forward(PATH, request(), TOKEN)
    assert result.error_code is ErrorCode.SOURCE_FAILED
    assert len(provider.calls) == 1
    assert r.failure is ErrorCode.SOURCE_FAILED


def test_429_within_the_wall_time_waits_then_retries() -> None:
    limited = TransportResponse(status=429, headers={"Retry-After": "2"}, body=b"slow down")
    provider = Provider(limited, ok())
    waits: list[float] = []
    r = ModelRelay(
        ROUTE,
        Limits(),
        TOKEN,
        transport=provider,
        sleep=waits.append,
        deadline=time.monotonic() + 100,
    )
    assert r.forward(PATH, request(), TOKEN).status == 200
    assert waits == [2.0]
    assert r.requests_used == 2


# --- concurrency and cancellation ----------------------------------------------------------


def test_concurrent_forwards_never_run_in_parallel() -> None:
    provider = Provider()
    provider.delay = 0.05
    r = relay(provider)
    threads = [threading.Thread(target=r.forward, args=(PATH, request(), TOKEN)) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert provider.max_in_flight == 1
    assert len(provider.calls) == 3


def test_cancel_closes_the_transport_and_refuses_new_requests() -> None:
    closed: list[bool] = []
    provider = Provider()
    provider.close = lambda: closed.append(True)  # type: ignore[method-assign]
    r = relay(provider)
    r.cancel()
    assert closed == [True]
    result = r.forward(PATH, request(), TOKEN)
    assert result.status == 499
    assert provider.calls == []


# --- usage and responses -------------------------------------------------------------------


def test_usage_and_served_by_are_recorded() -> None:
    r = relay(Provider(ok()))
    r.forward(PATH, request(), TOKEN)
    assert r.usage.model_requests == 1
    assert (r.usage.prompt_tokens, r.usage.completion_tokens) == (11, 7)
    assert r.usage.cost_eur is None
    assert r.served_by == ("Nvidia",)


def test_missing_usage_is_none_not_zero() -> None:
    r = relay(Provider(ok(), ok(usage=False)))
    r.forward(PATH, request(), TOKEN)
    r.forward(PATH, request(), TOKEN)
    assert r.usage.model_requests == 2
    assert r.usage.prompt_tokens is None
    assert r.usage.completion_tokens is None


def test_streaming_request_gets_an_sse_replay() -> None:
    result = relay(Provider(ok(content="hello there"))).forward(PATH, request(), TOKEN)
    assert result.content_type == "text/event-stream"
    events = [line[6:] for line in result.body.decode().splitlines() if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(event) for event in events[:-1]]
    assert chunks[0]["choices"][0]["delta"]["content"] == "hello there"
    assert chunks[-1]["usage"]["prompt_tokens"] == 11


def test_streamed_tool_calls_carry_an_index() -> None:
    body = json.loads(completion())
    body["choices"][0]["message"] = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "mcp__episalpha__echo_span", "arguments": "{}"},
            }
        ],
    }
    body["choices"][0]["finish_reason"] = "tool_calls"
    provider = Provider(TransportResponse(status=200, headers={}, body=json.dumps(body).encode()))
    result = relay(provider).forward(PATH, request(), TOKEN)
    first = json.loads(result.body.decode().split("data: ")[1])
    assert first["choices"][0]["delta"]["tool_calls"][0]["index"] == 0


def test_non_streaming_request_gets_json() -> None:
    result = relay(Provider(ok())).forward(PATH, request(stream=False), TOKEN)
    assert result.content_type == "application/json"
    assert json.loads(result.body)["provider"] == "Nvidia"


def test_secret_never_returned_or_traced(tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    settings = Settings.model_validate(
        {"paths": {"project_root": tmp_path, "data_root": tmp_path / "data"}}
    )
    configure_tracing(settings, extra_exporter=exporter)
    try:
        echo = TransportResponse(status=401, headers={}, body=f"bad key {SECRET}".encode())
        result = relay(Provider(echo)).forward(PATH, request(), TOKEN)
        good = relay(Provider(ok())).forward(PATH, request(), TOKEN)
    finally:
        shutdown_tracing()
    assert SECRET not in result.body.decode()
    assert SECRET not in good.body.decode()
    traced = "".join(item.to_json() for item in exporter.get_finished_spans())
    assert SECRET not in traced
    assert SECRET not in (tmp_path / "data" / "logs" / "spans.jsonl").read_text()
    names = [item.name for item in exporter.get_finished_spans()]
    assert names == ["model.call", "model.call"]
    span = exporter.get_finished_spans()[1]
    assert span.attributes is not None
    assert span.attributes["openinference.span.kind"] == "LLM"
    assert span.attributes["llm.model_name"] == MODEL
    assert span.attributes["llm.token_count.prompt"] == 11
    assert span.attributes["llm.token_count.completion_details.reasoning"] == 3
    assert span.attributes["episalpha.served_by"] == "Nvidia"
    assert span.attributes["http.response.status_code"] == 200


def test_the_recorded_route_still_supports_the_relay_design() -> None:
    """If a re-probe changes these observations, the relay design must be revisited (A3)."""
    route = json.loads(LOCK.read_text())["model_route"]
    capabilities = route["observed_capabilities"]
    assert route["model_id"] == ROUTE.model_id
    assert capabilities["forced_tool_choice"] is True
    assert capabilities["tool_arguments_parse_as_json"] is True
    # response_format is never forwarded, whatever the provider does with it.
    provider = Provider()
    relay(provider).forward(PATH, request(response_format={"type": "json_schema"}), TOKEN)
    assert provider.calls == []


# --- HTTP front ----------------------------------------------------------------------------


@pytest.fixture
def server() -> Iterator[tuple[RelayServer, Provider]]:
    provider = Provider()
    front = RelayServer(relay(provider), host="127.0.0.1", port=0)
    front.start()
    yield front, provider
    front.stop()


def test_http_front_reads_the_bearer_token(server: tuple[RelayServer, Provider]) -> None:
    import urllib.error
    import urllib.request

    front, provider = server
    url = f"http://127.0.0.1:{front.port}{PATH}"
    good = urllib.request.Request(
        url,
        data=request(stream=False),
        method="POST",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(good, timeout=5) as response:
        assert json.loads(response.read())["provider"] == "Nvidia"
    bad = urllib.request.Request(
        url, data=request(), method="POST", headers={"Authorization": "Bearer nope"}
    )
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(bad, timeout=5)
    assert raised.value.code == 400
    assert len(provider.calls) == 1


def test_429_without_retry_after_and_no_deadline_fails_instead_of_waiting_forever() -> None:
    provider = Provider(TransportResponse(status=429, headers={}, body=b"slow"), ok())
    result = relay(provider).forward(PATH, request(), TOKEN)
    assert result.error_code is ErrorCode.SOURCE_FAILED
    assert len(provider.calls) == 1


def test_refusals_are_logged_without_content(tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    settings = Settings.model_validate(
        {"paths": {"project_root": tmp_path, "data_root": tmp_path / "data"}}
    )
    configure_tracing(settings, extra_exporter=exporter)
    try:
        r = relay(Provider(), Limits(max_model_requests=1, max_transport_retries=0))
        r.forward(PATH, request(plugins=[{"id": "web"}]), TOKEN)
        r.forward(PATH, request(), TOKEN)
        r.forward(PATH, request(), TOKEN)
    finally:
        shutdown_tracing()
    names = [item.name for item in exporter.get_finished_spans()]
    assert names == ["relay.refusal", "model.call", "relay.refusal"]
    codes = [
        (item.attributes or {}).get("episalpha.error_code")
        for item in exporter.get_finished_spans()
        if item.name == "relay.refusal"
    ]
    assert codes == ["NOT_AUTHORIZED", "BUDGET_EXCEEDED"]
    assert r.failure is ErrorCode.BUDGET_EXCEEDED


def test_stage_policy_forces_the_submit_tool_on_the_last_request() -> None:
    provider = Provider()
    r = relay(provider)
    r.stage_policy = StagePolicy(max_requests=2, final_tool="mcp__episalpha__echo_span")
    assert r.forward(PATH, request(), TOKEN).status == 200
    assert r.forward(PATH, request(), TOKEN).status == 200
    capped = r.forward(PATH, request(), TOKEN)
    assert capped.error_code is ErrorCode.BUDGET_EXCEEDED
    first, last = provider.calls
    assert "tool_choice" not in first["body"]
    assert last["body"]["tool_choice"] == {
        "type": "function",
        "function": {"name": "mcp__episalpha__echo_span"},
    }
    assert r.failure is None  # a stage cap is not a run failure


def test_stage_policy_never_forces_a_tool_the_request_does_not_offer() -> None:
    provider = Provider()
    r = relay(provider)
    r.stage_policy = StagePolicy(max_requests=1, final_tool="mcp__episalpha__submit_thesis")
    r.forward(PATH, request(), TOKEN)
    assert "tool_choice" not in provider.calls[0]["body"]
