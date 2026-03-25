#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "nginx_edge_publication"
    / "defaults"
    / "main.yml"
)
PLATFORM_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"


@dataclass(frozen=True)
class AuditResult:
    hostname: str
    status_code: int
    passed: bool
    details: list[str]


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_role_defaults() -> dict:
    return load_yaml(ROLE_DEFAULTS_PATH)


def load_platform_vars() -> dict:
    return load_yaml(PLATFORM_VARS_PATH)


def derive_edge_hostnames(role_defaults: dict, platform_vars: dict) -> list[str]:
    hostnames = {
        service_data["public_hostname"]
        for service_data in platform_vars["platform_service_topology"].values()
        if isinstance(service_data, dict)
        and isinstance(service_data.get("edge"), dict)
        and service_data["edge"].get("enabled")
        and service_data.get("public_hostname")
    }
    hostnames.update(site["hostname"] for site in role_defaults["public_edge_extra_sites"])
    return sorted(hostnames)


def expected_headers_for_host(role_defaults: dict, hostname: str) -> dict[str, str]:
    headers = dict(role_defaults["public_edge_security_headers_default"])
    headers.update(role_defaults["public_edge_security_headers_overrides"].get(hostname, {}))
    return headers


def header_validators(expected_headers: dict[str, str]) -> dict[str, Callable[[str], bool]]:
    return {
        "strict-transport-security": lambda value: value == expected_headers["strict_transport_security"],
        "cross-origin-resource-policy": lambda value: value == expected_headers["cross_origin_resource_policy"],
        "x-content-type-options": lambda value: value == expected_headers["x_content_type_options"],
        "x-frame-options": lambda value: value == expected_headers["x_frame_options"],
        "referrer-policy": lambda value: value == expected_headers["referrer_policy"],
        "permissions-policy": lambda value: value == expected_headers["permissions_policy"],
        "content-security-policy": lambda value: value == expected_headers["content_security_policy"],
        "x-robots-tag": lambda value: value == expected_headers["x_robots_tag"],
    }


def fetch_headers(url: str, timeout: float) -> tuple[int, dict[str, str]]:
    opener = urllib.request.build_opener(NoRedirectHandler)
    request = urllib.request.Request(url, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:  # noqa: S310
            return response.getcode(), {key.lower(): value.strip() for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, {key.lower(): value.strip() for key, value in exc.headers.items()}


def audit_host(role_defaults: dict, hostname: str, timeout: float) -> AuditResult:
    status_code, headers = fetch_headers(f"https://{hostname}/", timeout)
    expected = expected_headers_for_host(role_defaults, hostname)
    validators = header_validators(expected)
    details: list[str] = []
    for header_name, validator in validators.items():
        observed = headers.get(header_name)
        if observed is None:
            details.append(f"missing {header_name}")
            continue
        if not validator(observed):
            details.append(f"unexpected {header_name}: {observed}")
    passed = not details
    return AuditResult(hostname=hostname, status_code=status_code, passed=passed, details=details)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the public edge for required HTTP security headers.")
    parser.add_argument(
        "--host",
        dest="hosts",
        action="append",
        help="Audit one hostname. Repeat to audit several hosts. Defaults to all edge-published hostnames.",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    role_defaults = load_role_defaults()
    platform_vars = load_platform_vars()
    hostnames = args.hosts or derive_edge_hostnames(role_defaults, platform_vars)
    results = [audit_host(role_defaults, hostname, args.timeout) for hostname in hostnames]
    for result in results:
        marker = "PASS" if result.passed else "FAIL"
        print(f"{marker} {result.hostname} [{result.status_code}]")
        for detail in result.details:
            print(f"  - {detail}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
