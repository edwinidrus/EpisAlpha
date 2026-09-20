"""Validated application settings.

Every numeric limit from plan section 3.8 lives in :class:`Limits` and nowhere else. Loading
settings reads one TOML file and never touches the network; credentials are environment
references resolved lazily at use time, never literal values stored in configuration.
"""

from __future__ import annotations

import os
import re
import tomllib
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

# ponytail: pydantic's own ValidationError already names the exact field path
# (e.g. "limits.max_tool_calls"), which is more actionable than a flattened wrapper.
# A dedicated error type belongs to contracts/errors.py in M1, not here.

_ENV_PREFIX = "ENV:"
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{1,63}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_]{0,31}$")
_COMPANY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")

DEMO_COMPANY_COUNT = 3
"""Plan section 1.4 fixes the demo corpus at exactly three companies."""


def _env_ref(value: Any) -> Any:
    """Accept only ``ENV:NAME`` references and store the bare variable name."""
    if not isinstance(value, str):
        return value
    if not value.startswith(_ENV_PREFIX):
        raise ValueError(
            'credentials must be environment references like "ENV:OLLAMA_API_KEY", '
            "never a literal secret value"
        )
    name = value[len(_ENV_PREFIX) :]
    if not _ENV_NAME.match(name):
        raise ValueError(
            f"{value!r} is not a usable environment variable name; expected "
            'a form like "ENV:OLLAMA_API_KEY"'
        )
    return name


def _decimal_string(value: Any) -> Any:
    """Parse a quoted decimal string; reject binary floating-point input."""
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str):
        raise ValueError(
            'money must be a quoted decimal string such as "25.00", not a number, '
            "so the written value is preserved exactly"
        )
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f'{value!r} is not a decimal number; use a form like "25.00"') from None


EnvRef = Annotated[str, BeforeValidator(_env_ref)]
DecimalString = Annotated[Decimal, BeforeValidator(_decimal_string)]


class _Base(BaseModel):
    # extra="forbid" must sit on the shared base: pydantic does not inherit model config into
    # nested models, so configuring only Settings would let unknown nested keys pass silently.
    # protected_namespaces=() allows ProviderRoute.model_id without a pydantic warning.
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class PathsConfig(_Base):
    """Absolute local paths. Anchoring of relative entries happens in :func:`load_settings`."""

    project_root: Path
    data_root: Path

    @field_validator("project_root", "data_root")
    @classmethod
    def _must_be_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError(
                f"{value} must be absolute; load_settings() anchors relative entries against "
                "the configuration file's directory, so the working directory is never used"
            )
        return value


class ProviderRoute(_Base):
    """The single model route. Which route actually works is verified by M0-T03."""

    model_id: str | None = None
    endpoint_url: str | None = None
    api_key_env: EnvRef | None = None
    request_timeout_seconds: int = Field(default=60, ge=1, le=600)

    @field_validator("endpoint_url")
    @classmethod
    def _must_be_http(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError(f"{value!r} must start with http:// or https://")
        return value

    def credential(self) -> str | None:
        """Resolve the credential at use time.

        Returns ``None`` when no reference is configured or the variable is absent, so offline
        development and the default test suite never depend on a secret being present.
        """
        if self.api_key_env is None:
            return None
        return os.environ.get(self.api_key_env) or None


class DemoSelection(_Base):
    """Owner-selected demo corpus. Empty until the owner resolves plan section 1.4."""

    companies: tuple[str, ...] = ()
    theme: str | None = None

    @field_validator("companies")
    @classmethod
    def _check_companies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) not in (0, DEMO_COMPANY_COUNT):
            raise ValueError(
                f"plan section 1.4 requires exactly {DEMO_COMPANY_COUNT} companies, or an empty "
                f"list while the owner choice is unresolved; got {len(value)}"
            )
        if len(set(value)) != len(value):
            raise ValueError("companies must be unique")
        for company in value:
            if not _COMPANY.match(company):
                raise ValueError(
                    f"{company!r} is not a filesystem-safe identifier; use letters, digits, "
                    "dot, dash or underscore"
                )
        return value


class SourceFamily(StrEnum):
    """The source families, following the TradingAgents reference architecture."""

    MARKET = "market"
    NEWS = "news"
    SOCIAL = "social"
    FUNDAMENTALS = "fundamentals"
    MACRO = "macro"


class ProvenanceStrength(StrEnum):
    """How much a source can be relied on to establish that something is true.

    This is not a quality score. It records what *kind* of thing the source is, so the
    research validator can refuse to let a forum post carry the same weight as a filing.
    """

    PRIMARY = "primary"
    """The issuer's or regulator's own document. The thing itself."""

    SECONDARY = "secondary"
    """A report *about* a primary source. An article about a filing is not the filing."""

    UNVERIFIED = "unverified"
    """Public commentary with no availability guarantee and no accountable publisher."""


class SourceConfig(_Base):
    """One configured source."""

    source_id: str
    family: SourceFamily
    provenance: ProvenanceStrength
    base_url: str | None = None
    api_key_env: EnvRef | None = None
    enabled: bool = True

    @field_validator("source_id")
    @classmethod
    def _check_slug(cls, value: str) -> str:
        if not _SLUG.match(value):
            raise ValueError(f"{value!r} must be a lowercase identifier such as 'sec_edgar'")
        return value

    def credential(self) -> str | None:
        """Resolve at use time; an absent variable yields ``None``, never an exception."""
        if self.api_key_env is None:
            return None
        return os.environ.get(self.api_key_env) or None


class SourcesConfig(_Base):
    """The configured source set across all families.

    ``filings_source_id`` and ``price_source_id`` name the two sources the v0.1 research
    workflow actually requires; the rest are additional evidence families.
    """

    filings_source_id: str = "sec_edgar"
    price_source_id: str | None = None
    sources: tuple[SourceConfig, ...] = ()

    @field_validator("filings_source_id", "price_source_id")
    @classmethod
    def _check_required_slug(cls, value: str | None) -> str | None:
        if value is not None and not _SLUG.match(value):
            raise ValueError(f"{value!r} must be a lowercase identifier such as 'sec_edgar'")
        return value

    @model_validator(mode="after")
    def _named_sources_are_configured(self) -> Self:
        known = {source.source_id for source in self.sources}
        if len(known) != len(self.sources):
            raise ValueError("source_id values must be unique")
        if self.sources and self.filings_source_id not in known:
            raise ValueError(
                f"filings_source_id {self.filings_source_id!r} is not among the configured "
                f"sources {sorted(known)}"
            )
        if self.sources and self.price_source_id is not None and self.price_source_id not in known:
            raise ValueError(
                f"price_source_id {self.price_source_id!r} is not among the configured "
                f"sources {sorted(known)}"
            )
        filings = self.by_id(self.filings_source_id)
        if filings is not None and filings.provenance is not ProvenanceStrength.PRIMARY:
            raise ValueError(
                f"filings_source_id {self.filings_source_id!r} has provenance "
                f"{filings.provenance.value!r}; the filings source must be primary, because a "
                "report about a filing is not the filing"
            )
        return self

    def by_id(self, source_id: str) -> SourceConfig | None:
        return next((s for s in self.sources if s.source_id == source_id), None)

    def enabled_in(self, family: SourceFamily) -> tuple[SourceConfig, ...]:
        return tuple(s for s in self.sources if s.family is family and s.enabled)

    @property
    def unverified_source_ids(self) -> tuple[str, ...]:
        """Sources that may never be the sole support for a material assertion."""
        return tuple(
            s.source_id
            for s in self.sources
            if s.enabled and s.provenance is ProvenanceStrength.UNVERIFIED
        )

    @property
    def missing_credentials(self) -> tuple[str, ...]:
        """Enabled sources whose credential reference resolves to nothing right now."""
        return tuple(
            s.source_id
            for s in self.sources
            if s.enabled and s.api_key_env is not None and s.credential() is None
        )


class Limits(_Base):
    """Plan section 3.8. Proposed engineering limits, not measured performance.

    These are the only copies of these numbers in the application; enforcing code reads them
    from here rather than defining its own constants.
    """

    max_active_research_jobs: int = Field(default=1, ge=1, le=1)
    run_wall_time_seconds: int = Field(default=300, ge=1, le=3600)
    max_model_requests: int = Field(default=8, ge=1, le=64)
    max_tool_calls: int = Field(default=12, ge=1, le=128)
    max_output_tokens_per_call: int = Field(default=4000, ge=1, le=32_000)
    max_request_body_bytes: int = Field(default=131_072, ge=1024, le=1_048_576)
    max_tool_result_bytes: int = Field(default=32_768, ge=256, le=1_048_576)
    max_evidence_search_hits: int = Field(default=6, ge=1, le=50)
    max_output_repairs: int = Field(default=1, ge=0, le=3)
    max_transport_retries: int = Field(default=1, ge=0, le=3)
    eur_cap: DecimalString | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.max_transport_retries >= self.max_model_requests:
            raise ValueError(
                f"max_transport_retries ({self.max_transport_retries}) must be below "
                f"max_model_requests ({self.max_model_requests}): retries count toward the "
                "request budget (plan section 3.8), so an equal budget is unsatisfiable"
            )
        if self.max_tool_result_bytes > self.max_request_body_bytes:
            raise ValueError(
                f"max_tool_result_bytes ({self.max_tool_result_bytes}) must not exceed "
                f"max_request_body_bytes ({self.max_request_body_bytes}): tool results are fed "
                "back into the next model request body"
            )
        # ponytail: v0.1 has no cost reservation or verified pricing, so accepting this field
        # would present a cap the system cannot honour. Delete this block at M3-T02 once the
        # relay can reserve spend.
        if self.eur_cap is not None:
            raise ValueError(
                "eur_cap is set but v0.1 cannot enforce it: conservative cost reservation and "
                "verified pricing are not implemented (plan section 3.8). Leave it unset; the "
                "request, output and time limits apply and cost is reported as unknown. Record "
                "the required cap in docs/implementation/progress.md, where it blocks live runs "
                "until M3-T02."
            )
        return self


class Settings(_Base):
    """The whole validated configuration."""

    paths: PathsConfig
    provider: ProviderRoute = ProviderRoute()
    demo: DemoSelection = DemoSelection()
    sources: SourcesConfig = SourcesConfig()
    limits: Limits = Limits()

    @property
    def unresolved_owner_inputs(self) -> tuple[str, ...]:
        """Plan section 1.4 inputs still awaiting an owner decision.

        ``provider.api_key_env`` is absent by design: a signed-in local route carries no key,
        so an unset reference is not evidence of an unresolved decision.
        """
        unresolved: list[str] = []
        if self.provider.model_id is None:
            unresolved.append("provider.model_id")
        if self.provider.endpoint_url is None:
            unresolved.append("provider.endpoint_url")
        if not self.demo.companies:
            unresolved.append("demo.companies")
        if self.demo.theme is None:
            unresolved.append("demo.theme")
        if self.sources.price_source_id is None:
            unresolved.append("sources.price_source_id")
        return tuple(unresolved)


def _anchor(base: Path, value: object) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"expected a path string, got {value!r}")
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else base / candidate).resolve()


def load_settings(config_path: Path) -> Settings:
    """Load and validate settings from a TOML file.

    Relative ``project_root`` resolves against the configuration file's own directory and
    relative ``data_root`` against ``project_root``; the process working directory is never
    consulted. Makes no network calls and creates no directories.
    """
    resolved_config = config_path.resolve()
    with resolved_config.open("rb") as handle:
        raw: dict[str, Any] = tomllib.load(handle)

    paths = raw.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(
            f"{resolved_config}: missing required [paths] table declaring project_root"
        )
    project_root = _anchor(resolved_config.parent, paths.get("project_root", ".."))
    paths["project_root"] = project_root
    paths["data_root"] = _anchor(project_root, paths.get("data_root", ".episalpha"))
    return Settings.model_validate(raw)
