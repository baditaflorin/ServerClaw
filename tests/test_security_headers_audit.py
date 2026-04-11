from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import security_headers_audit as audit


def test_derive_edge_hostnames_includes_service_topology_and_extra_sites() -> None:
    role_defaults = {
        "public_edge_extra_sites": [
            {"hostname": "docs.example.com"},
            {"hostname": "changelog.example.com"},
        ]
    }
    platform_vars = {
        "platform_service_topology": {
            "grafana": {"public_hostname": "grafana.example.com", "edge": {"enabled": True}},
            "windmill": {"public_hostname": "windmill.example.com", "edge": {"enabled": False}},
            "uptime": {"public_hostname": "uptime.example.com", "edge": {"enabled": True}},
        }
    }

    assert audit.derive_edge_hostnames(role_defaults, platform_vars) == [
        "changelog.example.com",
        "docs.example.com",
        "grafana.example.com",
        "uptime.example.com",
    ]


def test_expected_headers_for_host_merges_override_over_default() -> None:
    role_defaults = {
        "public_edge_security_headers_default": {
            "x_frame_options": "DENY",
            "content_security_policy": "default-src 'self'",
        },
        "public_edge_security_headers_overrides": {
            "ops.example.com": {
                "content_security_policy": "default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' https://unpkg.com"
            }
        },
    }

    assert audit.expected_headers_for_host(role_defaults, "ops.example.com") == {
        "x_frame_options": "DENY",
        "content_security_policy": "default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' https://unpkg.com",
    }


def test_audit_host_reports_missing_and_mismatched_headers(monkeypatch) -> None:
    role_defaults = {
        "public_edge_security_headers_default": {
            "strict_transport_security": "max-age=63072000; includeSubDomains; preload",
            "cross_origin_resource_policy": "same-origin",
            "x_content_type_options": "nosniff",
            "x_frame_options": "DENY",
            "referrer_policy": "strict-origin-when-cross-origin",
            "permissions_policy": "camera=()",
            "content_security_policy": "default-src 'self'",
            "x_robots_tag": "noindex, nofollow",
        },
        "public_edge_security_headers_overrides": {},
    }
    monkeypatch.setattr(
        audit,
        "fetch_headers",
        lambda url, timeout: (
            200,
            {
                "strict-transport-security": "max-age=63072000; includeSubDomains; preload",
                "x-content-type-options": "nosniff",
                "x-frame-options": "SAMEORIGIN",
            },
        ),
    )

    result = audit.audit_host(role_defaults, "grafana.example.com", timeout=5.0)

    assert result.passed is False
    assert "missing cross-origin-resource-policy" in result.details
    assert "unexpected x-frame-options: SAMEORIGIN" in result.details
    assert "missing content-security-policy" in result.details
