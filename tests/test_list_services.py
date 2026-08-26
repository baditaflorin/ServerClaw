"""Tests for scripts/list_services.py — ADR 0481.

All tests use synthetic in-memory registries so they don't depend on the
live config/subdomain-exposure-registry.json. A small set of integration
tests exercises the real registry to catch schema drift.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "list_services.py"


def _load():
    spec = importlib.util.spec_from_file_location("list_services", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["list_services"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ls():
    return _load()


# ---------------------------------------------------------------------------
# Minimal synthetic registry helpers
# ---------------------------------------------------------------------------


def _pub(
    fqdn: str,
    service_id: str,
    *,
    status: str = "active",
    audience: str = "operator",
    delivery_model: str = "shared-edge",
    access_model: str = "platform-sso",
) -> dict:
    return {
        "fqdn": fqdn,
        "service_id": service_id,
        "status": status,
        "environment": "production",
        "publication": {
            "delivery_model": delivery_model,
            "access_model": access_model,
            "audience": audience,
        },
    }


def _registry(
    *pubs,
    primary: str = "example.com",
    deployments: dict | None = None,
) -> dict:
    if deployments is None:
        deployments = {
            primary: {
                "platform_domain": primary,
                "environment": "production",
                "infrastructure": {"provider": "proxmox", "description": "test"},
                "service_exclusions": [],
                "feature_flags": {},
            }
        }
    return {
        "schema_version": "3.0.0",
        "zone_name": "localhost",
        "primary_deployment": primary,
        "deployments": deployments,
        "publications": list(pubs),
        "summary": {},
    }


def _fork_deployments(
    primary: str = "example.com",
    fork: str = "example.org",
    exclusions: list[str] | None = None,
) -> dict:
    return {
        primary: {
            "platform_domain": primary,
            "environment": "production",
            "infrastructure": {"provider": "proxmox", "description": "primary"},
            "service_exclusions": [],
            "feature_flags": {},
        },
        fork: {
            "platform_domain": fork,
            "environment": "production",
            "forked_from": primary,
            "infrastructure": {"provider": "hetzner", "description": "fork"},
            "service_exclusions": exclusions or [],
            "feature_flags": {},
        },
    }


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_rejects_v2_registry(self, ls) -> None:
        reg = _registry(_pub("api.example.com", "api_gateway"))
        reg["schema_version"] = "2.0.0"
        with pytest.raises(SystemExit):
            ls.get_view(reg, "example.com")

    def test_rejects_unknown_deployment(self, ls) -> None:
        reg = _registry(_pub("api.example.com", "api_gateway"))
        with pytest.raises(SystemExit):
            ls.get_view(reg, "nonexistent.com")


# ---------------------------------------------------------------------------
# Primary deployment view
# ---------------------------------------------------------------------------


class TestPrimaryView:
    def test_returns_all_publications(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            _pub("git.example.com", "gitea"),
        )
        view = ls.get_view(reg, "example.com")
        assert len(view.services) == 2

    def test_service_entry_fields(self, ls) -> None:
        reg = _registry(_pub("api.example.com", "api_gateway", audience="public"))
        view = ls.get_view(reg, "example.com")
        svc = view.services[0]
        assert svc.fqdn == "api.example.com"
        assert svc.service_id == "api_gateway"
        assert svc.audience == "public"
        assert svc.deployment == "example.com"

    def test_active_filter(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway", status="active"),
            _pub("future.example.com", "future_svc", status="planned"),
        )
        view = ls.get_view(reg, "example.com")
        assert len(view.active()) == 1
        assert view.active()[0].service_id == "api_gateway"


# ---------------------------------------------------------------------------
# Fork deployment view
# ---------------------------------------------------------------------------


class TestForkView:
    def test_excludes_disabled_services(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            _pub("errors.example.com", "glitchtip"),
            deployments=_fork_deployments(exclusions=["glitchtip"]),
        )
        view = ls.get_view(reg, "example.org")
        service_ids = {s.service_id for s in view.services}
        assert "api_gateway" in service_ids
        assert "glitchtip" not in service_ids

    def test_rewrites_fqdns_to_fork_domain(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            _pub("git.example.com", "gitea"),
            deployments=_fork_deployments(),
        )
        view = ls.get_view(reg, "example.org")
        fqdns = {s.fqdn for s in view.services}
        assert "api.example.org" in fqdns
        assert "git.example.org" in fqdns
        assert "api.example.com" not in fqdns

    def test_apex_fqdn_becomes_fork_apex(self, ls) -> None:
        reg = _registry(
            _pub("example.com", "nginx_edge"),
            deployments=_fork_deployments(),
        )
        view = ls.get_view(reg, "example.org")
        assert view.services[0].fqdn == "example.org"

    def test_fork_deployment_slug_on_entries(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            deployments=_fork_deployments(),
        )
        view = ls.get_view(reg, "example.org")
        assert all(s.deployment == "example.org" for s in view.services)

    def test_no_exclusions_returns_all_services(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            _pub("git.example.com", "gitea"),
            deployments=_fork_deployments(exclusions=[]),
        )
        primary_view = ls.get_view(reg, "example.com")
        fork_view = ls.get_view(reg, "example.org")
        assert len(fork_view.services) == len(primary_view.services)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class TestDiff:
    def test_only_left_contains_excluded_service(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            _pub("errors.example.com", "glitchtip"),
            deployments=_fork_deployments(exclusions=["glitchtip"]),
        )
        diff = ls.diff_deployments(reg, "example.com", "example.org")
        assert len(diff.only_left) == 1
        assert diff.only_left[0].service_id == "glitchtip"

    def test_only_right_empty_for_pure_fork(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            deployments=_fork_deployments(),
        )
        diff = ls.diff_deployments(reg, "example.com", "example.org")
        assert diff.only_right == []

    def test_both_has_correct_count(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            _pub("git.example.com", "gitea"),
            _pub("errors.example.com", "glitchtip"),
            deployments=_fork_deployments(exclusions=["glitchtip"]),
        )
        diff = ls.diff_deployments(reg, "example.com", "example.org")
        assert len(diff.both) == 2
        assert len(diff.only_left) == 1

    def test_diff_is_symmetric_sides(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            deployments=_fork_deployments(),
        )
        diff = ls.diff_deployments(reg, "example.com", "example.org")
        left_ids = {l.service_id for l, _ in diff.both}
        right_ids = {r.service_id for _, r in diff.both}
        assert left_ids == right_ids


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


class TestFormatList:
    def test_table_format_contains_fqdn(self, ls) -> None:
        reg = _registry(_pub("api.example.com", "api_gateway"))
        view = ls.get_view(reg, "example.com")
        out = ls.format_list(view, status=None, fmt="table")
        assert "api.example.com" in out
        assert "api_gateway" in out

    def test_json_format_is_valid_json(self, ls) -> None:
        reg = _registry(_pub("api.example.com", "api_gateway"))
        view = ls.get_view(reg, "example.com")
        out = ls.format_list(view, status=None, fmt="json")
        data = json.loads(out)
        assert data["deployment"] == "example.com"
        assert len(data["services"]) == 1

    def test_csv_format_has_header(self, ls) -> None:
        reg = _registry(_pub("api.example.com", "api_gateway"))
        view = ls.get_view(reg, "example.com")
        out = ls.format_list(view, status=None, fmt="csv")
        lines = out.splitlines()
        assert "fqdn" in lines[0]
        assert "api.example.com" in lines[1]

    def test_status_filter_in_table(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway", status="active"),
            _pub("beta.example.com", "beta_svc", status="planned"),
        )
        view = ls.get_view(reg, "example.com")
        out = ls.format_list(view, status="active", fmt="table")
        assert "api.example.com" in out
        assert "beta.example.com" not in out


class TestFormatDiff:
    def test_table_diff_shows_exclusion(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            _pub("errors.example.com", "glitchtip"),
            deployments=_fork_deployments(exclusions=["glitchtip"]),
        )
        diff = ls.diff_deployments(reg, "example.com", "example.org")
        out = ls.format_diff(diff, status=None, fmt="table")
        assert "only on example.com" in out
        assert "glitchtip" in out

    def test_json_diff_is_valid(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            deployments=_fork_deployments(),
        )
        diff = ls.diff_deployments(reg, "example.com", "example.org")
        out = ls.format_diff(diff, status=None, fmt="json")
        data = json.loads(out)
        assert data["left"] == "example.com"
        assert data["right"] == "example.org"
        assert "summary" in data


# ---------------------------------------------------------------------------
# List deployments
# ---------------------------------------------------------------------------


class TestListDeployments:
    def test_returns_both_deployments(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            deployments=_fork_deployments(),
        )
        metas = ls.list_deployments(reg)
        slugs = [m.slug for m in metas]
        assert "example.com" in slugs
        assert "example.org" in slugs

    def test_primary_is_first(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            deployments=_fork_deployments(),
        )
        metas = ls.list_deployments(reg)
        assert metas[0].slug == "example.com"

    def test_format_json(self, ls) -> None:
        reg = _registry(
            _pub("api.example.com", "api_gateway"),
            deployments=_fork_deployments(),
        )
        out = ls.format_list_deployments(reg, fmt="json")
        data = json.loads(out)
        assert any(d["primary"] for d in data)


# ---------------------------------------------------------------------------
# CLI integration (uses real registry)
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_list_primary(self, ls) -> None:
        rc = ls.main(["--status", "active", "--format", "json"])
        assert rc == 0

    def test_cli_list_fork(self, ls) -> None:
        rc = ls.main(["--deployment", "example.org", "--status", "active"])
        assert rc == 0

    def test_cli_diff(self, ls, capsys) -> None:
        rc = ls.main(["--diff", "example.com", "example.org"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "summary" in captured.out

    def test_cli_list_deployments(self, ls, capsys) -> None:
        rc = ls.main(["--list-deployments"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "example.com" in captured.out
        assert "example.org" in captured.out

    def test_cli_unknown_deployment_returns_2(self, ls) -> None:
        rc = ls.main(["--deployment", "nonexistent.com"])
        assert rc == 2

    def test_cli_diff_json_is_parseable(self, ls, capsys) -> None:
        rc = ls.main(["--diff", "example.com", "example.org", "--format", "json"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["left"] == "example.com"
        assert data["right"] == "example.org"
        assert data["summary"]["only_left"] >= 1
