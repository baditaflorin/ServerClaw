from __future__ import annotations

import json
from pathlib import Path
import urllib.request

import yaml

from platform.timeouts import (
    TimeoutContext,
    default_timeout,
    load_hierarchy_payload,
    resolve_timeout_seconds,
    timeout_limit,
    validate_timeout_hierarchy,
)
from scripts.api_gateway_catalog import validate_api_gateway_catalog
from scripts.check_hardcoded_timeouts import DEFAULT_TARGETS, iter_paths, scan
from scripts.netbox_inventory_sync import NetBoxClient


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_timeout_hierarchy_is_valid() -> None:
    payload = load_hierarchy_payload(REPO_ROOT / "config" / "timeout-hierarchy.yaml")
    hierarchy = validate_timeout_hierarchy(payload, path="config/timeout-hierarchy.yaml")

    assert hierarchy["workflow_execution"].default_timeout_s == 600
    assert hierarchy["workflow_execution"].timeout_s == 7200
    assert hierarchy["http_request"].default_timeout_s == 30


def test_timeout_context_caps_children_to_remaining_budget() -> None:
    timeout_ctx = TimeoutContext.for_layer("api_call_chain", 45)

    request_timeout = timeout_ctx.timeout_for("http_request", 60, reserve_seconds=1.0)

    assert 0 < request_timeout <= 44


def test_api_gateway_catalog_timeouts_fit_http_request_layer() -> None:
    catalog = json.loads((REPO_ROOT / "config" / "api-gateway-catalog.json").read_text(encoding="utf-8"))
    normalized = validate_api_gateway_catalog(catalog)

    assert normalized
    assert all(service["timeout_seconds"] <= timeout_limit("http_request") for service in normalized)
    assert {service["timeout_seconds"] for service in normalized} == {30}


def test_netbox_client_uses_hierarchy_timeout(monkeypatch) -> None:
    captured: dict[str, float] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"results":[]}'

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None):  # type: ignore[override]
        captured["timeout"] = float(timeout or 0)
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client = NetBoxClient("https://netbox.example.test", "token")
    client.request("GET", "/api/dcim/sites/")

    assert captured["timeout"] == resolve_timeout_seconds("http_request", default_timeout("http_request"))


def test_hardcoded_timeout_scan_passes_for_targeted_paths() -> None:
    violations = scan(iter_paths(list(DEFAULT_TARGETS)))

    assert violations == []


def test_windmill_defaults_seed_scheduler_watchdog() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text(
            encoding="utf-8"
        )
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedules = {entry["path"]: entry for entry in defaults["windmill_seed_schedules"]}

    assert "f/lv3/scheduler_watchdog_loop" in script_paths
    assert "f/lv3/scheduler_watchdog_loop_every_10s" in schedules
    assert schedules["f/lv3/scheduler_watchdog_loop_every_10s"]["enabled"] is True


def test_scheduler_watchdog_wrapper_exists_for_preflight() -> None:
    wrapper_path = REPO_ROOT / "config" / "windmill" / "scripts" / "scheduler-watchdog-loop.py"

    assert wrapper_path.exists()
