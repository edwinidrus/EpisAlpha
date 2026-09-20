"""Live model-route checks for M0-T03.

These make real, paid model calls and are excluded from the default suite. Run them with::

    set -a; source .env; set +a
    uv run pytest -q -m live tests/integration/test_hermes_probe.py

They pin the route capabilities recorded in ``config/runtime.lock.json``. If one fails, the
recorded findings are stale and the runtime built on them needs re-checking — do not relax the
assertion.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from episalpha.settings import ProviderRoute, load_settings

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_FILE = REPO_ROOT / "config" / "runtime.lock.json"
CONFIG_CANDIDATES = (REPO_ROOT / "config" / "demo.toml", REPO_ROOT / "config" / "demo.example.toml")


def load_probe() -> ModuleType:
    """Import the probe script by path; scripts/ is not an importable package."""
    path = REPO_ROOT / "scripts" / "probe_hermes.py"
    spec = importlib.util.spec_from_file_location("probe_hermes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def route() -> ProviderRoute:
    config = next((path for path in CONFIG_CANDIDATES if path.exists()), None)
    if config is None:
        pytest.skip("no settings file found")
    provider = load_settings(config).provider
    if provider.credential() is None:
        pytest.skip(f"credential {provider.api_key_env} is not exported; source .env first")
    return provider


def test_recorded_capabilities_still_hold(route: ProviderRoute) -> None:
    """The probe script is the single source of truth for what this route can do."""
    probe = load_probe()
    recorded = json.loads(LOCK_FILE.read_text())["model_route"]["observed_capabilities"]

    tool_call = probe.probe_tool_call(route)
    assert tool_call["forced_tool_choice_honored"] is recorded["forced_tool_choice"]
    assert tool_call["arguments_parse_as_json"] is recorded["tool_arguments_parse_as_json"]
    assert tool_call["usage_reported"] is recorded["usage_reported"]

    # Recorded as False: the endpoint accepts response_format and silently ignores it. If this
    # ever starts passing, the relay may finally rely on provider-side structured output.
    response_format = probe.probe_response_format(route)
    expected = recorded["response_format_json_schema_honored"]
    assert response_format["json_schema_honored"] is expected


def test_configured_model_matches_the_probed_route(route: ProviderRoute) -> None:
    recorded = json.loads(LOCK_FILE.read_text())["model_route"]

    assert route.model_id == recorded["model_id"]
    assert route.endpoint_url == recorded["endpoint_url"]
