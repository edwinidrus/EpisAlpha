"""Settings validation, path anchoring, and credential-reference tests."""

from __future__ import annotations

import socket
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from episalpha.settings import (
    Limits,
    ProvenanceStrength,
    Settings,
    SourceConfig,
    SourceFamily,
    SourcesConfig,
    load_settings,
)

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "demo.example.toml"

MINIMAL = """
[paths]
project_root = ".."
data_root = ".episalpha"
"""

RESOLVED = """
[paths]
project_root = ".."
data_root = ".episalpha"

[provider]
model_id = "glm-5.3"
endpoint_url = "https://ollama.com/v1"
api_key_env = "ENV:ollama_api_key"

[demo]
companies = ["ACME", "BETA", "GAMMA"]
theme = "guidance and demand changes"

[sources]
price_source_id = "local_eod"
"""


def write_config(tmp_path: Path, body: str) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    path = config_dir / "demo.toml"
    path.write_text(body)
    return path


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("settings load attempted network access")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def test_example_config_loads() -> None:
    settings = load_settings(EXAMPLE_CONFIG)

    assert settings.provider.model_id == "glm-5.3"
    assert settings.limits.max_tool_calls == 12


def test_load_makes_no_network_calls(tmp_path: Path, no_network: None) -> None:
    assert load_settings(write_config(tmp_path, MINIMAL)).paths.project_root == tmp_path


def test_missing_paths_table_is_actionable(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\[paths\].*project_root"):
        load_settings(write_config(tmp_path, "[limits]\nmax_tool_calls = 12\n"))


def test_relative_paths_resolve_from_config_dir_not_cwd(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = write_config(tmp_path, MINIMAL)
    monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))

    settings = load_settings(config_path)

    assert settings.paths.project_root == tmp_path
    assert settings.paths.data_root == tmp_path / ".episalpha"


def test_absolute_data_root_is_preserved(tmp_path: Path) -> None:
    elsewhere = tmp_path / "outside"
    body = f'[paths]\nproject_root = ".."\ndata_root = "{elsewhere}"\n'

    assert load_settings(write_config(tmp_path, body)).paths.data_root == elsewhere


def test_model_rejects_relative_path_directly() -> None:
    with pytest.raises(ValidationError, match="load_settings"):
        Settings.model_validate({"paths": {"project_root": "rel", "data_root": "/tmp"}})


def test_unknown_top_level_table_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="mystery"):
        load_settings(write_config(tmp_path, MINIMAL + "\n[mystery]\nkey = 1\n"))


def test_unknown_key_in_nested_table_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="limits.max_tokens"):
        load_settings(write_config(tmp_path, MINIMAL + "\n[limits]\nmax_tokens = 5\n"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_tool_calls", 0),
        ("run_wall_time_seconds", -1),
        ("max_model_requests", 0),
        ("max_output_tokens_per_call", 1_000_000),
        ("max_tool_result_bytes", 0),
        ("max_evidence_search_hits", 0),
        ("max_active_research_jobs", 2),
    ],
)
def test_invalid_limit_rejected(tmp_path: Path, field: str, value: int) -> None:
    with pytest.raises(ValidationError, match=field):
        load_settings(write_config(tmp_path, f"{MINIMAL}\n[limits]\n{field} = {value}\n"))


def test_retry_budget_must_fit_request_budget() -> None:
    with pytest.raises(ValidationError, match="retries count toward the request budget"):
        Limits(max_transport_retries=3, max_model_requests=3)


def test_tool_result_cannot_exceed_request_body() -> None:
    with pytest.raises(ValidationError, match="max_tool_result_bytes"):
        Limits(max_tool_result_bytes=262_144, max_request_body_bytes=131_072)


def test_limit_defaults_match_plan_section_3_8() -> None:
    limits = Limits()

    assert (
        limits.max_active_research_jobs,
        limits.run_wall_time_seconds,
        limits.max_model_requests,
        limits.max_tool_calls,
        limits.max_output_tokens_per_call,
        limits.max_request_body_bytes,
        limits.max_tool_result_bytes,
        limits.max_evidence_search_hits,
        limits.max_output_repairs,
        limits.max_transport_retries,
        limits.eur_cap,
    ) == (1, 300, 8, 12, 4000, 131_072, 32_768, 6, 1, 1, None)


def test_literal_secret_rejected(tmp_path: Path) -> None:
    body = f'{MINIMAL}\n[provider]\napi_key_env = "sk-live-abc123"\n'

    with pytest.raises(ValidationError, match="environment references"):
        load_settings(write_config(tmp_path, body))


def test_env_ref_stores_variable_name_not_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ollama_api_key", "super-secret-value")
    body = f'{MINIMAL}\n[provider]\napi_key_env = "ENV:ollama_api_key"\n'

    settings = load_settings(write_config(tmp_path, body))

    assert settings.provider.api_key_env == "ollama_api_key"
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.model_dump())
    assert settings.provider.credential() == "super-secret-value"


def test_credential_resolves_lazily(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ollama_api_key", raising=False)
    body = f'{MINIMAL}\n[provider]\napi_key_env = "ENV:ollama_api_key"\n'

    settings = load_settings(write_config(tmp_path, body))
    assert settings.provider.credential() is None

    monkeypatch.setenv("ollama_api_key", "later-value")
    assert settings.provider.credential() == "later-value"


@pytest.mark.parametrize("endpoint", ["ftp://example.invalid", "ollama.com/v1"])
def test_endpoint_url_must_be_http(tmp_path: Path, endpoint: str) -> None:
    body = f'{MINIMAL}\n[provider]\nendpoint_url = "{endpoint}"\n'

    with pytest.raises(ValidationError, match="http"):
        load_settings(write_config(tmp_path, body))


def test_example_config_has_no_unresolved_owner_inputs() -> None:
    """Every plan section 1.4 input is now decided; the example config proves it."""
    assert load_settings(EXAMPLE_CONFIG).unresolved_owner_inputs == ()


def test_unresolved_owner_inputs_are_listed_when_absent(tmp_path: Path) -> None:
    settings = load_settings(write_config(tmp_path, MINIMAL))

    assert settings.unresolved_owner_inputs == (
        "provider.model_id",
        "provider.endpoint_url",
        "demo.companies",
        "demo.theme",
        "sources.price_source_id",
    )


def test_fully_resolved_config_has_no_unresolved_inputs(tmp_path: Path) -> None:
    assert load_settings(write_config(tmp_path, RESOLVED)).unresolved_owner_inputs == ()


@pytest.mark.parametrize("companies", ['["ACME", "BETA"]', '["ACME", "ACME", "BETA"]'])
def test_demo_companies_must_be_three_and_unique(tmp_path: Path, companies: str) -> None:
    body = f"{MINIMAL}\n[demo]\ncompanies = {companies}\n"

    with pytest.raises(ValidationError, match="companies"):
        load_settings(write_config(tmp_path, body))


def test_company_identifier_must_be_filesystem_safe(tmp_path: Path) -> None:
    body = f'{MINIMAL}\n[demo]\ncompanies = ["../etc/passwd", "BETA", "GAMMA"]\n'

    with pytest.raises(ValidationError, match="filesystem-safe"):
        load_settings(write_config(tmp_path, body))


def test_eur_cap_float_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="quoted decimal string"):
        load_settings(write_config(tmp_path, f"{MINIMAL}\n[limits]\neur_cap = 25.0\n"))


def test_eur_cap_blocked_until_reservation_exists(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="M3-T02"):
        load_settings(write_config(tmp_path, f'{MINIMAL}\n[limits]\neur_cap = "25.00"\n'))


def test_eur_cap_parses_as_exact_decimal_before_rejection() -> None:
    from episalpha.settings import _decimal_string

    assert _decimal_string("25.10") == Decimal("25.10")


# --- source families and provenance ------------------------------------------------------


def source(**overrides: Any) -> SourceConfig:
    base: dict[str, Any] = {
        "source_id": "sec_edgar",
        "family": SourceFamily.FUNDAMENTALS,
        "provenance": ProvenanceStrength.PRIMARY,
    }
    base.update(overrides)
    return SourceConfig(**base)


def test_example_config_carries_the_full_source_set() -> None:
    sources = load_settings(EXAMPLE_CONFIG).sources

    assert {s.source_id for s in sources.sources} >= {
        "sec_edgar",
        "alpha_vantage",
        "alpha_vantage_news",
        "reddit",
        "stocktwits",
        "fred",
    }
    assert sources.by_id("sec_edgar") is not None


def test_social_sources_ship_disabled() -> None:
    """Unverified commentary cannot establish anything; it is opt-in, never default."""
    sources = load_settings(EXAMPLE_CONFIG).sources

    assert sources.enabled_in(SourceFamily.SOCIAL) == ()
    assert sources.unverified_source_ids == ()


def test_enabling_a_social_source_surfaces_it_as_unverified() -> None:
    sources = SourcesConfig(
        sources=(
            source(),
            source(
                source_id="reddit",
                family=SourceFamily.SOCIAL,
                provenance=ProvenanceStrength.UNVERIFIED,
            ),
        ),
    )

    assert sources.unverified_source_ids == ("reddit",)


def test_the_filings_source_must_be_primary() -> None:
    """A report about a filing is not the filing."""
    with pytest.raises(ValidationError, match="must be primary"):
        SourcesConfig(
            filings_source_id="newswire",
            sources=(
                source(
                    source_id="newswire",
                    family=SourceFamily.NEWS,
                    provenance=ProvenanceStrength.SECONDARY,
                ),
            ),
        )


def test_a_named_source_must_actually_be_configured() -> None:
    with pytest.raises(ValidationError, match="is not among the configured sources"):
        SourcesConfig(price_source_id="ghost_feed", sources=(source(),))


def test_duplicate_source_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        SourcesConfig(sources=(source(), source()))


def test_missing_credentials_are_reported_without_failing_the_load() -> None:
    """Offline development must not require every provider key to exist."""
    sources = SourcesConfig(
        sources=(
            source(),
            source(
                source_id="alpha_vantage",
                family=SourceFamily.MARKET,
                api_key_env="ENV:EPISALPHA_ABSENT_KEY",
            ),
        ),
    )

    assert sources.missing_credentials == ("alpha_vantage",)


def test_a_source_credential_is_a_reference_not_a_value() -> None:
    with pytest.raises(ValidationError, match="environment references"):
        source(api_key_env="av-live-secret")
