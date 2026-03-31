#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, write_json


REPO_ROOT = repo_path()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# controller_automation_toolkit may have imported the stdlib platform module first.
# Drop that non-package entry so the repo's platform/ package can be imported.
loaded_platform = sys.modules.get("platform")
if loaded_platform is not None and not hasattr(loaded_platform, "__path__"):
    loaded_platform_file = getattr(loaded_platform, "__file__", "")
    if not str(loaded_platform_file).startswith(str(REPO_ROOT / "platform")):
        sys.modules.pop("platform", None)

from drift_lib import (
    isoformat,
    load_controller_context,
    nats_tunnel,
    publish_nats_events,
    resolve_nats_credentials,
    utc_now,
)
from mutation_audit import build_event, emit_event_best_effort
from glitchtip_event import emit_glitchtip_event
from platform_observation_tool import maybe_read_secret_path, post_json_webhook
from subdomain_catalog import load_public_edge_defaults, load_subdomain_catalog
DEFAULT_ENVIRONMENT = "production"
DEFAULT_POLICY_PATH = repo_path("config", "public-surface-scan-policy.json")
DEFAULT_RECEIPT_DIR = repo_path("receipts", "security-scan")
DEFAULT_ARTIFACTS_ROOT = repo_path(".local", "public-surface-scan")
DEFAULT_TESTSSL_IMAGE = "ghcr.io/testssl/testssl.sh:latest"
DEFAULT_NUCLEI_IMAGE = "projectdiscovery/nuclei:latest"
ALLOWED_ENVIRONMENTS = {"production", "staging"}
ALLOWED_HEADER_MATCHES = {"contains", "equals", "one_of"}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}
PUBLIC_HTTPS_EXPOSURES = {"edge-published", "informational-only"}
SEVERITY_ORDER = ("critical", "high", "medium", "low")
SEVERITY_CODES = {"clean": 0, "warn": 2, "high": 1, "critical": 1}


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def require_enum(value: Any, path: str, allowed: set[str]) -> str:
    value = require_str(value, path)
    if value not in allowed:
        raise ValueError(f"{path} must be one of {sorted(allowed)}")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    result: list[str] = []
    for index, item in enumerate(require_list(value, path)):
        result.append(require_str(item, f"{path}[{index}]"))
    return result


def load_public_surface_scan_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    payload = require_mapping(load_json(path), str(path))
    if payload.get("schema_version") != "1.0.0":
        raise ValueError("public surface scan policy must declare schema_version '1.0.0'")

    required_headers = require_list(payload.get("required_headers"), "required_headers")
    if not required_headers:
        raise ValueError("required_headers must not be empty")
    for index, item in enumerate(required_headers):
        item = require_mapping(item, f"required_headers[{index}]")
        require_str(item.get("id"), f"required_headers[{index}].id")
        require_str(item.get("name"), f"required_headers[{index}].name")
        match = require_enum(item.get("match"), f"required_headers[{index}].match", ALLOWED_HEADER_MATCHES)
        require_enum(item.get("severity"), f"required_headers[{index}].severity", ALLOWED_SEVERITIES)
        require_str(item.get("summary"), f"required_headers[{index}].summary")
        if match == "one_of":
            require_string_list(item.get("values"), f"required_headers[{index}].values")
        else:
            require_str(item.get("value"), f"required_headers[{index}].value")

    auth_redirect = require_mapping(payload.get("auth_redirect"), "auth_redirect")
    require_str(auth_redirect.get("expected_host"), "auth_redirect.expected_host")
    require_string_list(auth_redirect.get("forbidden_headers", []), "auth_redirect.forbidden_headers")
    require_string_list(auth_redirect.get("forbidden_body_patterns", []), "auth_redirect.forbidden_body_patterns")

    version_headers = require_mapping(payload.get("version_headers"), "version_headers")
    require_string_list(version_headers.get("exact", []), "version_headers.exact")
    require_string_list(version_headers.get("regex", []), "version_headers.regex")
    require_bool(
        version_headers.get("server_requires_version_pattern", False),
        "version_headers.server_requires_version_pattern",
    )

    nuclei = require_mapping(payload.get("nuclei"), "nuclei")
    require_str(nuclei.get("target"), "nuclei.target")
    require_string_list(nuclei.get("tags"), "nuclei.tags")
    severities = require_string_list(nuclei.get("severity"), "nuclei.severity")
    if not severities:
        raise ValueError("nuclei.severity must not be empty")
    for index, severity in enumerate(severities):
        require_enum(severity, f"nuclei.severity[{index}]", ALLOWED_SEVERITIES)

    return payload


def maybe_load_controller_context() -> dict[str, Any] | None:
    try:
        return load_controller_context()
    except Exception:  # noqa: BLE001
        return None


def build_http_opener(*, follow_redirects: bool) -> urllib.request.OpenerDirector:
    handlers: list[Any] = []
    if not follow_redirects:
        handlers.append(NoRedirectHandler())
    return urllib.request.build_opener(*handlers)


def fetch_http_response(
    url: str,
    *,
    follow_redirects: bool = False,
    timeout: int = 20,
) -> dict[str, Any]:
    opener = build_http_opener(follow_redirects=follow_redirects)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "lv3-public-surface-scan/1.0",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(8192).decode("utf-8", errors="replace")
            return {
                "url": url,
                "status": response.getcode(),
                "final_url": response.geturl(),
                "headers": dict(response.headers.items()),
                "body": body,
            }
    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "status": exc.code,
            "final_url": exc.geturl(),
            "headers": dict(exc.headers.items()),
            "body": exc.read(8192).decode("utf-8", errors="replace"),
        }
    except urllib.error.URLError as exc:
        return {
            "url": url,
            "status": 0,
            "final_url": url,
            "headers": {},
            "body": "",
            "error": str(exc),
        }


def slugify_hostname(hostname: str) -> str:
    return hostname.replace(".", "-")


def relative_repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT.resolve()))


def normalize_header_name(name: str) -> str:
    return name.casefold()


def find_header_value(headers: dict[str, str], name: str) -> str | None:
    wanted = normalize_header_name(name)
    for key, value in headers.items():
        if normalize_header_name(key) == wanted:
            return value
    return None


def header_rule_matches(rule: dict[str, Any], value: str | None) -> bool:
    if value is None:
        return False
    match = rule["match"]
    if match == "contains":
        return str(rule["value"]).casefold() in value.casefold()
    if match == "equals":
        return value.strip().casefold() == str(rule["value"]).strip().casefold()
    if match == "one_of":
        allowed = {item.casefold() for item in rule["values"]}
        return value.strip().casefold() in allowed
    raise ValueError(f"unsupported header rule match: {match}")


def build_finding(
    *,
    scan_id: str,
    severity: str,
    component: str,
    target: str,
    finding_id: str,
    summary: str,
    observed: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scan_id": scan_id,
        "severity": severity,
        "component": component,
        "target": target,
        "finding_id": finding_id,
        "summary": summary,
        "observed": observed,
        "evidence": evidence or {},
    }


def discover_scan_targets(environment: str) -> list[dict[str, Any]]:
    catalog = load_subdomain_catalog()
    public_edge_defaults = load_public_edge_defaults()
    auth_sites = public_edge_defaults.get("public_edge_authenticated_sites", {})
    targets: list[dict[str, Any]] = []

    for entry in sorted(catalog["subdomains"], key=lambda item: item["fqdn"]):
        if entry.get("environment") != environment:
            continue
        if entry.get("status") != "active":
            continue
        if entry.get("target_port") != 443:
            continue
        if entry.get("exposure") not in PUBLIC_HTTPS_EXPOSURES:
            continue
        fqdn = entry["fqdn"]
        auth_entry = auth_sites.get(fqdn)
        unauthenticated_paths = []
        if isinstance(auth_entry, dict):
            raw_paths = auth_entry.get("unauthenticated_paths", [])
            if isinstance(raw_paths, list):
                unauthenticated_paths = [str(item) for item in raw_paths]
        targets.append(
            {
                "fqdn": fqdn,
                "exposure": entry["exposure"],
                "service_id": entry["service_id"],
                "requires_auth": fqdn in auth_sites and "/" not in unauthenticated_paths,
                "unauthenticated_paths": unauthenticated_paths,
                "url": f"https://{fqdn}",
            }
        )
    return targets


def evaluate_header_findings(
    *,
    scan_id: str,
    target: dict[str, Any],
    response: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rule in policy["required_headers"]:
        observed = find_header_value(response["headers"], rule["name"])
        if header_rule_matches(rule, observed):
            continue
        findings.append(
            build_finding(
                scan_id=scan_id,
                severity=rule["severity"],
                component="headers",
                target=target["fqdn"],
                finding_id=f"headers.{rule['id']}",
                summary=rule["summary"],
                observed=f"{rule['name']}={observed or '<missing>'}",
                evidence={
                    "expected_match": rule["match"],
                    "expected_value": rule.get("value", rule.get("values")),
                    "status": response["status"],
                },
            )
        )
    return findings


def evaluate_version_disclosure_findings(
    *,
    scan_id: str,
    target: dict[str, Any],
    response: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    exact_names = {item.casefold() for item in policy["version_headers"]["exact"]}
    regexes = [re.compile(pattern) for pattern in policy["version_headers"]["regex"]]
    for header_name, header_value in response["headers"].items():
        normalized = header_name.casefold()
        if normalized in exact_names and header_value.strip():
            findings.append(
                build_finding(
                    scan_id=scan_id,
                    severity="low",
                    component="version-disclosure",
                    target=target["fqdn"],
                    finding_id=f"version.{slugify_hostname(header_name)}",
                    summary="Response discloses an application version header.",
                    observed=f"{header_name}={header_value}",
                )
            )
            continue
        if any(pattern.fullmatch(header_name) for pattern in regexes):
            findings.append(
                build_finding(
                    scan_id=scan_id,
                    severity="low",
                    component="version-disclosure",
                    target=target["fqdn"],
                    finding_id=f"version.{slugify_hostname(header_name)}",
                    summary="Response discloses an application version header.",
                    observed=f"{header_name}={header_value}",
                )
            )
            continue
        if normalized == "server" and policy["version_headers"]["server_requires_version_pattern"]:
            if re.search(r"\d", header_value):
                findings.append(
                    build_finding(
                        scan_id=scan_id,
                        severity="low",
                        component="version-disclosure",
                        target=target["fqdn"],
                        finding_id="version.server",
                        summary="Response discloses a versioned Server header.",
                        observed=f"{header_name}={header_value}",
                    )
                )
    return findings


def evaluate_auth_findings(
    *,
    scan_id: str,
    target: dict[str, Any],
    response: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    if not target["requires_auth"]:
        return []

    findings: list[dict[str, Any]] = []
    location = find_header_value(response["headers"], "Location") or ""
    expected_host = policy["auth_redirect"]["expected_host"]
    redirect_host = urllib.parse.urlparse(location).hostname or ""
    if response["status"] not in {301, 302, 303, 307, 308} or redirect_host != expected_host:
        findings.append(
            build_finding(
                scan_id=scan_id,
                severity="high",
                component="auth",
                target=target["fqdn"],
                finding_id="auth.redirect",
                summary="Protected surface did not redirect unauthenticated traffic to Keycloak.",
                observed=f"status={response['status']} location={location or '<missing>'}",
            )
        )

    body_lower = response["body"].casefold()
    for pattern in policy["auth_redirect"]["forbidden_body_patterns"]:
        if pattern.casefold() in body_lower:
            findings.append(
                build_finding(
                    scan_id=scan_id,
                    severity="high",
                    component="auth",
                    target=target["fqdn"],
                    finding_id=f"auth.body.{slugify_hostname(pattern)}",
                    summary="Protected surface returned portal content before authentication.",
                    observed=f"body contains '{pattern}'",
                )
            )

    for header_name in policy["auth_redirect"]["forbidden_headers"]:
        observed = find_header_value(response["headers"], header_name)
        if observed:
            findings.append(
                build_finding(
                    scan_id=scan_id,
                    severity="high",
                    component="auth",
                    target=target["fqdn"],
                    finding_id=f"auth.header.{slugify_hostname(header_name)}",
                    summary="Protected surface exposed a sensitive auth proxy header.",
                    observed=f"{header_name}={observed}",
                )
            )
    return findings


def ensure_docker_image(image: str, *, pull: bool) -> None:
    if not pull:
        return
    completed = subprocess.run(
        ["docker", "pull", image],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"failed to pull {image}")


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}[{index}] must be a JSON object")
        result.append(payload)
    return result


def classify_testssl_findings(
    *,
    scan_id: str,
    target: dict[str, Any],
    raw_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    target_name = str(target.get("finding_target") or target.get("display_name") or target["fqdn"])
    for item in raw_findings:
        item = require_mapping(item, f"testssl[{target['fqdn']}]")
        finding_text = str(item.get("finding", "")).strip()
        finding_lower = finding_text.casefold()
        item_id = str(item.get("id", "unknown"))
        severity: str | None = None
        summary = ""

        if "certificate" in finding_lower and "expired" in finding_lower:
            severity = "critical"
            summary = "TLS certificate is expired."
        elif ("tls 1 " in finding_lower or "tls 1.0" in finding_lower or "tls 1.1" in finding_lower) and "offered" in finding_lower:
            severity = "high"
            summary = "Deprecated TLS protocol is still accepted."
        elif "weak cipher" in finding_lower or "3des" in finding_lower or "null cipher" in finding_lower:
            severity = "high"
            summary = "Weak cipher suite is still accepted."
        elif "cbc" in finding_lower and ("preferred" in finding_lower or "offered" in finding_lower):
            severity = "low"
            summary = "CBC cipher preference is still visible."

        if not severity:
            continue

        fingerprint = (severity, item_id)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        findings.append(
            build_finding(
                scan_id=scan_id,
                severity=severity,
                component="tls",
                target=target_name,
                finding_id=f"tls.{item_id}",
                summary=summary,
                observed=finding_text or item_id,
                evidence={"tool_severity": item.get("severity"), "tool_id": item_id},
            )
        )
    return findings


def run_testssl_scans(
    *,
    scan_id: str,
    targets: list[dict[str, Any]],
    artifacts_dir: Path,
    image: str,
    pull_images: bool,
    timeout_seconds: int,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    ensure_docker_image(image, pull=pull_images)
    raw_dir = artifacts_dir / "testssl"
    raw_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for target in targets:
        scan_slug = str(target.get("scan_slug") or target["fqdn"])
        output_name = f"{slugify_hostname(scan_slug)}.json"
        output_path = raw_dir / output_name
        command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{raw_dir.resolve()}:/out",
            image,
            "--quiet",
            "--warnings",
            "batch",
            "--jsonfile",
            f"/out/{output_name}",
            "--severity",
            "LOW",
            "--protocols",
            "--cipher-per-proto",
            "--headers",
            "--vulnerabilities",
        ]
        ip_override = str(target.get("testssl_ip") or "").strip()
        if ip_override:
            command.extend(["--ip", ip_override])
        command.append(str(target.get("testssl_url") or target["url"]))
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            raw_payload = load_json(output_path, default=[])
            if not isinstance(raw_payload, list):
                raise ValueError(f"{output_path} must contain a JSON list")
            results[target["fqdn"]] = {
                "artifact": relative_repo_path(output_path),
                "returncode": completed.returncode,
                "duration_seconds": round(time.monotonic() - started, 2),
                "raw_findings": len(raw_payload),
            }
            findings.extend(
                classify_testssl_findings(
                    scan_id=scan_id,
                    target=target,
                    raw_findings=raw_payload,
                )
            )
        except subprocess.TimeoutExpired:
            results[target["fqdn"]] = {
                "artifact": relative_repo_path(output_path),
                "returncode": 124,
                "duration_seconds": round(time.monotonic() - started, 2),
                "raw_findings": 0,
            }
            findings.append(
                build_finding(
                    scan_id=scan_id,
                    severity="medium",
                    component="tls",
                    target=target["fqdn"],
                    finding_id="tls.scan_timeout",
                    summary="TLS scan timed out before producing a result.",
                    observed=f"timeout={timeout_seconds}s image={image}",
                )
            )
    return results, findings


def classify_nuclei_findings(
    *,
    scan_id: str,
    raw_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, item in enumerate(raw_findings):
        info = require_mapping(item.get("info", {}), f"nuclei[{index}].info")
        severity = require_enum(info.get("severity"), f"nuclei[{index}].info.severity", ALLOWED_SEVERITIES)
        findings.append(
            build_finding(
                scan_id=scan_id,
                severity=severity,
                component="open-redirect",
                target=str(item.get("host") or item.get("matched-at") or "https://lv3.org"),
                finding_id=f"open-redirect.{item.get('template-id', 'unknown')}",
                summary=str(info.get("name") or "Nuclei finding"),
                observed=str(item.get("matcher-name") or item.get("template-id") or "nuclei-match"),
                evidence={
                    "template_id": item.get("template-id"),
                    "matcher_name": item.get("matcher-name"),
                },
            )
        )
    return findings


def run_nuclei_scan(
    *,
    scan_id: str,
    policy: dict[str, Any],
    artifacts_dir: Path,
    image: str,
    pull_images: bool,
    timeout_seconds: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ensure_docker_image(image, pull=pull_images)
    output_path = artifacts_dir / "nuclei.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{artifacts_dir.resolve()}:/out",
        image,
        "-target",
        policy["nuclei"]["target"],
        "-tags",
        ",".join(policy["nuclei"]["tags"]),
        "-severity",
        ",".join(policy["nuclei"]["severity"]),
        "-json-export",
        "/out/nuclei.json",
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        raw_findings = load_ndjson(output_path)
        return (
            {
                "artifact": relative_repo_path(output_path),
                "returncode": completed.returncode,
                "duration_seconds": round(time.monotonic() - started, 2),
                "raw_findings": len(raw_findings),
                "target": policy["nuclei"]["target"],
            },
            classify_nuclei_findings(scan_id=scan_id, raw_findings=raw_findings),
        )
    except subprocess.TimeoutExpired:
        return (
            {
                "artifact": relative_repo_path(output_path),
                "returncode": 124,
                "duration_seconds": round(time.monotonic() - started, 2),
                "raw_findings": 0,
                "target": policy["nuclei"]["target"],
            },
            [
                build_finding(
                    scan_id=scan_id,
                    severity="medium",
                    component="open-redirect",
                    target=policy["nuclei"]["target"],
                    finding_id="open-redirect.scan_timeout",
                    summary="Open redirect scan timed out before producing a result.",
                    observed=f"timeout={timeout_seconds}s image={image}",
                )
            ],
        )


def summarize_findings(findings: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in findings:
        counter[str(item["severity"])] += 1
    return {severity: counter.get(severity, 0) for severity in SEVERITY_ORDER}


def component_summary(findings: list[dict[str, Any]], component: str) -> dict[str, Any]:
    relevant = [item for item in findings if item["component"] == component]
    counts = summarize_findings(relevant)
    status = "pass"
    if counts["critical"] or counts["high"]:
        status = "fail"
    elif counts["medium"] or counts["low"]:
        status = "warn"
    return {
        "status": status,
        "finding_counts": counts,
    }


def build_report(
    *,
    scan_id: str,
    environment: str,
    targets: list[dict[str, Any]],
    http_observations: dict[str, dict[str, Any]],
    tls_results: dict[str, dict[str, Any]],
    nuclei_result: dict[str, Any],
    findings: list[dict[str, Any]],
    started_at: float,
    artifacts_dir: Path,
) -> dict[str, Any]:
    counts = summarize_findings(findings)
    if counts["critical"]:
        status = "critical"
    elif counts["high"]:
        status = "high"
    elif counts["medium"] or counts["low"]:
        status = "warn"
    else:
        status = "clean"

    target_rows = []
    for target in targets:
        host_findings = [item for item in findings if item["target"] == target["fqdn"]]
        target_rows.append(
            {
                "fqdn": target["fqdn"],
                "service_id": target["service_id"],
                "exposure": target["exposure"],
                "requires_auth": target["requires_auth"],
                "status_code": http_observations[target["fqdn"]]["status"],
                "finding_counts": summarize_findings(host_findings),
            }
        )

    return {
        "schema_version": "1.0.0",
        "scan_id": scan_id,
        "generated_at": isoformat(utc_now()),
        "environment": environment,
        "artifacts_dir": relative_repo_path(artifacts_dir),
        "targets": target_rows,
        "http_observations": http_observations,
        "tls_scans": tls_results,
        "nuclei_scan": nuclei_result,
        "findings": sorted(
            findings,
            key=lambda item: (
                SEVERITY_ORDER.index(item["severity"]),
                item["component"],
                item["target"],
                item["finding_id"],
            ),
        ),
        "summary": {
            "target_count": len(targets),
            "requires_auth_count": sum(1 for target in targets if target["requires_auth"]),
            "duration_seconds": round(time.monotonic() - started_at, 2),
            "status": status,
            "status_code": SEVERITY_CODES[status],
            "finding_counts": counts,
            "components": {
                "tls": component_summary(findings, "tls"),
                "headers": component_summary(findings, "headers"),
                "auth": component_summary(findings, "auth"),
                "version_disclosure": component_summary(findings, "version-disclosure"),
                "open_redirect": component_summary(findings, "open-redirect"),
            },
        },
    }


def build_security_events(report: dict[str, Any], receipt_ref: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "event": "platform.security.report",
            "environment": report["environment"],
            "generated_at": report["generated_at"],
            "summary": report["summary"],
            "receipt_ref": receipt_ref,
        }
    ]
    for finding in report["findings"]:
        if finding["severity"] == "critical":
            events.append(
                {
                    "event": "platform.security.critical-finding",
                    "generated_at": report["generated_at"],
                    "environment": report["environment"],
                    "receipt_ref": receipt_ref,
                    **finding,
                }
            )
        elif finding["severity"] == "high":
            events.append(
                {
                    "event": "platform.security.high-finding",
                    "generated_at": report["generated_at"],
                    "environment": report["environment"],
                    "receipt_ref": receipt_ref,
                    **finding,
                }
            )
    return events


def maybe_publish_nats(events: list[dict[str, Any]], *, publish: bool, context: dict[str, Any] | None) -> None:
    if not publish or not events:
        return
    if context is None:
        raise RuntimeError("cannot publish NATS events without controller context")
    nats_url = os.environ.get("LV3_NATS_URL", "").strip()
    credentials = resolve_nats_credentials(context)
    if nats_url:
        publish_nats_events(events, nats_url=nats_url, credentials=credentials)
        return
    with nats_tunnel(context) as local_port:
        publish_nats_events(events, nats_url=f"nats://127.0.0.1:{local_port}", credentials=credentials)


def format_mattermost_summary(report: dict[str, Any], receipt_ref: str) -> str:
    summary = report["summary"]
    components = summary["components"]
    return "\n".join(
        [
            f"Weekly security scan: {report['environment']}",
            "",
            f"Scanned: {summary['target_count']} hostnames | Duration: {summary['duration_seconds']}s",
            f"TLS: {components['tls']['status']} | Headers: {components['headers']['status']}",
            f"Auth: {components['auth']['status']} | Versions: {components['version_disclosure']['status']}",
            f"Redirects: {components['open_redirect']['status']}",
            "",
            f"CRITICAL findings: {summary['finding_counts']['critical']}",
            f"HIGH findings: {summary['finding_counts']['high']}",
            f"MEDIUM findings: {summary['finding_counts']['medium']}",
            f"LOW findings: {summary['finding_counts']['low']}",
            f"Receipt: {receipt_ref}",
        ]
    )


def post_mattermost_summary(report: dict[str, Any], *, receipt_ref: str, webhook_url: str) -> None:
    post_json_webhook(webhook_url, {"text": format_mattermost_summary(report, receipt_ref)})


def post_glitchtip_events(events: list[dict[str, Any]], webhook_url: str) -> None:
    for event in events:
        if event.get("event") != "platform.security.critical-finding":
            continue
        emit_glitchtip_event(
            webhook_url,
            {
                "message": f"Public surface security critical finding: {event['finding_id']}",
                "level": "error",
                "tags": {
                    "component": event.get("component", ""),
                    "target": event.get("target", ""),
                },
                "extra": event,
            },
        )


def write_receipt(receipt_dir: Path, report: dict[str, Any]) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    path = receipt_dir / f"{report['scan_id']}.json"
    write_json(path, report, indent=2, sort_keys=True)
    return path


def run_scan(
    *,
    environment: str,
    policy_path: Path,
    receipt_dir: Path,
    artifacts_root: Path,
    testssl_image: str,
    nuclei_image: str,
    pull_images: bool,
    skip_testssl: bool,
    skip_nuclei: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    if environment not in ALLOWED_ENVIRONMENTS:
        raise ValueError(f"environment must be one of {sorted(ALLOWED_ENVIRONMENTS)}")

    scan_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    started_at = time.monotonic()
    policy = load_public_surface_scan_policy(policy_path)
    targets = discover_scan_targets(environment)
    artifacts_dir = artifacts_root / scan_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    findings: list[dict[str, Any]] = []
    http_observations: dict[str, dict[str, Any]] = {}
    for target in targets:
        response = fetch_http_response(target["url"], follow_redirects=False)
        http_observations[target["fqdn"]] = {
            "status": response["status"],
            "final_url": response["final_url"],
            "error": response.get("error"),
            "headers": {
                key: value
                for key, value in response["headers"].items()
                if normalize_header_name(key)
                in {
                    "strict-transport-security",
                    "x-content-type-options",
                    "x-frame-options",
                    "referrer-policy",
                    "x-robots-tag",
                    "server",
                    "x-powered-by",
                    "location",
                    "x-grafana-version",
                    "x-windmill-version",
                }
            },
        }
        if response.get("error"):
            findings.append(
                build_finding(
                    scan_id=scan_id,
                    severity="critical",
                    component="tls",
                    target=target["fqdn"],
                    finding_id="tls.http_probe_failure",
                    summary="HTTPS probe failed before headers could be evaluated.",
                    observed=str(response["error"]),
                )
            )
            continue
        findings.extend(
            evaluate_header_findings(
                scan_id=scan_id,
                target=target,
                response=response,
                policy=policy,
            )
        )
        findings.extend(
            evaluate_version_disclosure_findings(
                scan_id=scan_id,
                target=target,
                response=response,
                policy=policy,
            )
        )
        findings.extend(
            evaluate_auth_findings(
                scan_id=scan_id,
                target=target,
                response=response,
                policy=policy,
            )
        )

    if skip_testssl:
        tls_results = {}
    else:
        tls_results, tls_findings = run_testssl_scans(
            scan_id=scan_id,
            targets=targets,
            artifacts_dir=artifacts_dir,
            image=testssl_image,
            pull_images=pull_images,
            timeout_seconds=timeout_seconds,
        )
        findings.extend(tls_findings)

    if skip_nuclei:
        nuclei_result = {
            "artifact": "",
            "returncode": 0,
            "duration_seconds": 0,
            "raw_findings": 0,
            "target": policy["nuclei"]["target"],
        }
    else:
        nuclei_result, nuclei_findings = run_nuclei_scan(
            scan_id=scan_id,
            policy=policy,
            artifacts_dir=artifacts_dir,
            image=nuclei_image,
            pull_images=pull_images,
            timeout_seconds=timeout_seconds,
        )
        findings.extend(nuclei_findings)

    report = build_report(
        scan_id=scan_id,
        environment=environment,
        targets=targets,
        http_observations=http_observations,
        tls_results=tls_results,
        nuclei_result=nuclei_result,
        findings=findings,
        started_at=started_at,
        artifacts_dir=artifacts_dir,
    )
    receipt_path = write_receipt(receipt_dir, report)
    report["receipt_path"] = relative_repo_path(receipt_path)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the ADR 0142 public-surface security scan and write a receipt."
    )
    parser.add_argument("--env", default=DEFAULT_ENVIRONMENT, choices=sorted(ALLOWED_ENVIRONMENTS))
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--artifacts-root", type=Path, default=DEFAULT_ARTIFACTS_ROOT)
    parser.add_argument("--testssl-image", default=os.environ.get("PUBLIC_SURFACE_TESTSSL_IMAGE", DEFAULT_TESTSSL_IMAGE))
    parser.add_argument("--nuclei-image", default=os.environ.get("PUBLIC_SURFACE_NUCLEI_IMAGE", DEFAULT_NUCLEI_IMAGE))
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--skip-testssl", action="store_true")
    parser.add_argument("--skip-nuclei", action="store_true")
    parser.add_argument("--no-pull-images", action="store_true")
    parser.add_argument("--publish-nats", action="store_true")
    parser.add_argument("--mattermost-webhook-url")
    parser.add_argument("--glitchtip-event-url")
    parser.add_argument("--print-report-json", action="store_true")
    parser.add_argument("--audit-surface", default="manual")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_scan(
            environment=args.env,
            policy_path=args.policy,
            receipt_dir=args.receipt_dir,
            artifacts_root=args.artifacts_root,
            testssl_image=args.testssl_image,
            nuclei_image=args.nuclei_image,
            pull_images=not args.no_pull_images,
            skip_testssl=args.skip_testssl,
            skip_nuclei=args.skip_nuclei,
            timeout_seconds=args.timeout_seconds,
        )
        receipt_ref = report["receipt_path"]
        context = maybe_load_controller_context()
        events = build_security_events(report, receipt_ref)
        maybe_publish_nats(events, publish=args.publish_nats, context=context)

        secret_manifest = context["secret_manifest"] if context else None
        mattermost_url = args.mattermost_webhook_url
        if mattermost_url is None and secret_manifest is not None:
            mattermost_url = maybe_read_secret_path(
                secret_manifest,
                "mattermost_platform_findings_webhook_url",
            )
        if mattermost_url:
            post_mattermost_summary(report, receipt_ref=receipt_ref, webhook_url=mattermost_url)

        glitchtip_url = args.glitchtip_event_url
        if glitchtip_url is None and secret_manifest is not None:
            glitchtip_url = maybe_read_secret_path(
                secret_manifest,
                "glitchtip_platform_findings_event_url",
            )
        if glitchtip_url:
            post_glitchtip_events(events, glitchtip_url)

        emit_event_best_effort(
            build_event(
                actor_class="automation",
                actor_id="public-surface-scan",
                surface=args.audit_surface,
                action="public-surface-security.scan",
                target=f"public-surface/{args.env}",
                outcome="success",
                evidence_ref=receipt_ref,
            ),
            context="public surface security scan",
            stderr=sys.stderr,
        )

        print(f"Receipt: {receipt_ref}")
        if args.print_report_json:
            print(f"REPORT_JSON={json.dumps(report, separators=(',', ':'))}")
        return report["summary"]["status_code"]
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("public surface security scan", exc)


if __name__ == "__main__":
    raise SystemExit(main())
