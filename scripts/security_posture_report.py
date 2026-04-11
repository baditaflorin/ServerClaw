#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, write_json
from drift_lib import (
    build_guest_ssh_command,
    isoformat,
    load_controller_context,
    nats_tunnel,
    publish_nats_events,
    resolve_nats_credentials,
    run_command,
    utc_now,
)
from environment_catalog import environment_choices, primary_environment
from mutation_audit import build_event, emit_event_best_effort
from parse_lynis_report import DEFAULT_SUPPRESSIONS_PATH, load_suppressions, parse_path
from glitchtip_event import emit_glitchtip_event
from platform_observation_tool import maybe_read_secret_path, post_json_webhook
from platform.repo import TOPOLOGY_HOST


REPO_ROOT = repo_path()
DEFAULT_RECEIPT_DIR = repo_path("receipts", "security-reports")
DEFAULT_PLAYBOOK = repo_path("playbooks", "tasks", "security-scan.yml")
DEFAULT_INVENTORY = repo_path("inventory", "hosts.yml")
DEFAULT_LYNIS_DIR = repo_path(".local", "security-posture", "lynis")
DEFAULT_TRIVY_SCRIPT = repo_path("scripts", "trivy_scan_running_images.sh")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
DEFAULT_ENVIRONMENT = primary_environment()
ENVIRONMENT_CHOICES = environment_choices()
DEFAULT_LYNIS_HOSTS = {
    "production": [
        TOPOLOGY_HOST,
        "docker-build-lv3",
        "docker-runtime-lv3",
        "backup-lv3",
        "coolify-lv3",
        "postgres-lv3",
        "nginx-lv3",
        "monitoring-lv3",
    ],
    "staging": [
        TOPOLOGY_HOST,
        "docker-runtime-staging-lv3",
        "postgres-staging-lv3",
        "nginx-staging-lv3",
        "monitoring-staging-lv3",
    ],
}
DEFAULT_TRIVY_HOSTS = {
    "production": ["docker-runtime-lv3", "docker-build-lv3"],
    "staging": ["docker-runtime-staging-lv3", "docker-build-staging-lv3"],
}


def default_lynis_hosts(environment: str) -> list[str]:
    if environment != "production":
        return DEFAULT_LYNIS_HOSTS[environment]

    payload = load_json(SERVICE_CATALOG_PATH)
    hosts = {
        str(service["vm"])
        for service in payload.get("services", [])
        if isinstance(service, dict)
        and isinstance(service.get("vm"), str)
        and (
            not isinstance(service.get("environments"), dict)
            or not isinstance(service["environments"].get("production"), dict)
            or service["environments"]["production"].get("status") == "active"
        )
    }
    return sorted(hosts) if hosts else DEFAULT_LYNIS_HOSTS[environment]


def run_ansible_security_scan(
    *,
    inventory: Path,
    playbook: Path,
    output_dir: Path,
    hosts: list[str],
    bootstrap_key: Path | None = None,
    jump_host_addr: str | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    limit = ",".join(hosts)
    env = os.environ.copy()
    command = [
        "ansible-playbook",
        "-i",
        str(inventory),
        str(playbook),
        "-l",
        limit,
        "-e",
        f"security_scan_output_dir={output_dir}",
        "-e",
        "proxmox_guest_ssh_connection_mode=proxmox_host_jump",
    ]
    if bootstrap_key is not None:
        command.extend(["--private-key", str(bootstrap_key)])
        env["LV3_BOOTSTRAP_SSH_PRIVATE_KEY"] = str(bootstrap_key)
    if jump_host_addr:
        env["LV3_PROXMOX_HOST_ADDR"] = jump_host_addr
    result = run_command(command, cwd=REPO_ROOT, env=env if bootstrap_key is not None else None)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "security scan playbook failed")


def run_remote_script(
    *,
    context: dict[str, Any],
    host: str,
    script_path: Path,
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    exports = " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted((env or {}).items()) if value)
    remote_command = f"{exports} bash -s --" if exports else "bash -s --"
    command = build_guest_ssh_command(context, host, remote_command)
    result = subprocess.run(
        command,
        input=script_path.read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{host}: {result.stderr.strip() or result.stdout.strip() or 'remote scan failed'}")
    payload = json.loads(result.stdout or "[]")
    if not isinstance(payload, list):
        raise ValueError(f"{host}: trivy scan did not return a JSON list")
    return payload


def load_previous_report(receipt_dir: Path) -> dict[str, Any] | None:
    paths = sorted(receipt_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            return load_json(path)
        except Exception:
            continue
    return None


def finding_fingerprint(finding: dict[str, Any]) -> str:
    return f"{finding.get('id', 'UNKNOWN')}|{finding.get('description', '')}"


def summarize_hosts(reports: list[dict[str, Any]], previous_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    previous_hosts = {
        host_report.get("host"): host_report
        for host_report in (previous_report or {}).get("hosts", [])
        if isinstance(host_report, dict) and host_report.get("host")
    }
    summarized: list[dict[str, Any]] = []
    for host_report in reports:
        previous = previous_hosts.get(host_report["host"], {})
        previous_findings = {
            finding_fingerprint(item) for item in previous.get("findings", []) if isinstance(item, dict)
        }
        current_findings = host_report.get("findings", [])
        new_findings = [item for item in current_findings if finding_fingerprint(item) not in previous_findings]
        previous_index = previous.get("hardening_index")
        current_index = host_report.get("hardening_index")
        delta = None
        if isinstance(previous_index, int) and isinstance(current_index, int):
            delta = current_index - previous_index
        summarized.append(
            {
                "host": host_report["host"],
                "hardening_index": current_index,
                "hardening_index_delta": delta,
                "finding_counts": host_report.get("finding_counts", {}),
                "new_findings_since_last_scan": len(new_findings),
                "findings": current_findings,
                "suppressed_findings": host_report.get("suppressed_findings", []),
            }
        )
    return summarized


def summarize_images(host_payloads: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for host, payload in sorted(host_payloads.items()):
        for image in payload:
            images.append(
                {
                    "host": host,
                    "image": image.get("image"),
                    "artifact_name": image.get("artifact_name"),
                    "severity_counts": image.get("severity_counts", {}),
                    "cves": image.get("vulnerabilities", []),
                }
            )
    return images


def build_summary(hosts: list[dict[str, Any]], images: list[dict[str, Any]]) -> dict[str, Any]:
    hardening_indexes = [host["hardening_index"] for host in hosts if isinstance(host.get("hardening_index"), int)]
    total_critical = sum(int(image.get("severity_counts", {}).get("CRITICAL", 0)) for image in images)
    total_high = sum(int(image.get("severity_counts", {}).get("HIGH", 0)) for image in images)
    new_lynis = sum(int(host.get("new_findings_since_last_scan", 0)) for host in hosts)
    return {
        "host_count": len(hosts),
        "image_count": len(images),
        "total_critical_cves": total_critical,
        "total_high_cves": total_high,
        "lowest_hardening_index": min(hardening_indexes) if hardening_indexes else None,
        "new_lynis_findings": new_lynis,
        "status": "critical"
        if total_critical > 0
        or any(
            (host.get("hardening_index_delta") or 0) <= -10
            for host in hosts
            if host.get("hardening_index_delta") is not None
        )
        else "warn"
        if total_high > 0 or new_lynis > 0
        else "clean",
        "status_code": 2
        if total_critical > 0
        or any(
            (host.get("hardening_index_delta") or 0) <= -10
            for host in hosts
            if host.get("hardening_index_delta") is not None
        )
        else 1
        if total_high > 0 or new_lynis > 0
        else 0,
    }


def build_report(
    *,
    environment: str,
    host_reports: list[dict[str, Any]],
    trivy_payloads: dict[str, list[dict[str, Any]]],
    previous_report: dict[str, Any] | None,
) -> dict[str, Any]:
    hosts = summarize_hosts(host_reports, previous_report)
    images = summarize_images(trivy_payloads)
    summary = build_summary(hosts, images)
    return {
        "schema_version": "1.0.0",
        "generated_at": isoformat(utc_now()),
        "environment": environment,
        "hosts": hosts,
        "images": images,
        "summary": summary,
    }


def build_security_events(report: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "event": "platform.security.report",
            "environment": report["environment"],
            "generated_at": report["generated_at"],
            "summary": report["summary"],
        }
    ]
    for host in report.get("hosts", []):
        delta = host.get("hardening_index_delta")
        if isinstance(delta, int) and delta <= -10:
            events.append(
                {
                    "event": "platform.security.critical-finding",
                    "kind": "hardening-regression",
                    "host": host["host"],
                    "hardening_index": host.get("hardening_index"),
                    "hardening_index_delta": delta,
                    "generated_at": report["generated_at"],
                }
            )
    for image in report.get("images", []):
        for cve in image.get("cves", []):
            if cve.get("severity") != "CRITICAL":
                continue
            events.append(
                {
                    "event": "platform.security.critical-finding",
                    "kind": "container-cve",
                    "host": image["host"],
                    "image": image["image"],
                    "cve": cve,
                    "generated_at": report["generated_at"],
                }
            )
    return events


def maybe_publish_nats(events: list[dict[str, Any]], *, publish: bool, context: dict[str, Any]) -> None:
    if not publish or not events:
        return
    nats_url = os.environ.get("LV3_NATS_URL", "").strip()
    credentials = resolve_nats_credentials(context)
    if nats_url:
        publish_nats_events(events, nats_url=nats_url, credentials=credentials)
        return
    with nats_tunnel(context) as local_port:
        publish_nats_events(events, nats_url=f"nats://127.0.0.1:{local_port}", credentials=credentials)


def maybe_write_metrics(report: dict[str, Any]) -> None:
    influx_url = os.environ.get("SECURITY_POSTURE_INFLUXDB_URL", "").strip()
    influx_bucket = os.environ.get("SECURITY_POSTURE_INFLUXDB_BUCKET", "").strip()
    influx_org = os.environ.get("SECURITY_POSTURE_INFLUXDB_ORG", "").strip()
    influx_token = os.environ.get("SECURITY_POSTURE_INFLUXDB_TOKEN", "").strip()
    if not all((influx_url, influx_bucket, influx_org, influx_token)):
        return

    lines = [
        (
            f"platform_security_posture_summary,environment={report['environment']} "
            f"status_code={report['summary']['status_code']}i,"
            f"total_critical_cves={report['summary']['total_critical_cves']}i,"
            f"total_high_cves={report['summary']['total_high_cves']}i,"
            f"new_lynis_findings={report['summary']['new_lynis_findings']}i,"
            f"lowest_hardening_index={report['summary']['lowest_hardening_index'] or 0}i"
        )
    ]
    for host in report.get("hosts", []):
        hardening_index = host.get("hardening_index")
        if hardening_index is None:
            continue
        delta = host.get("hardening_index_delta")
        delta_value = 0 if delta is None else delta
        lines.append(
            f"platform_security_posture_host,environment={report['environment']},host={host['host']} "
            f"hardening_index={hardening_index}i,"
            f"hardening_index_delta={delta_value}i,"
            f"new_findings_since_last_scan={host['new_findings_since_last_scan']}i"
        )
    request = urllib.request.Request(
        f"{influx_url.rstrip('/')}/api/v2/write?org={urllib.parse.quote(influx_org)}&bucket={urllib.parse.quote(influx_bucket)}&precision=s",
        data="\n".join(lines).encode("utf-8"),
        headers={"Authorization": f"Token {influx_token}", "Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            return
    except urllib.error.URLError as exc:
        raise RuntimeError(f"failed to write security posture metrics: {exc}") from exc


def write_receipt(receipt_dir: Path, report: dict[str, Any]) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    path = receipt_dir / f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
    write_json(path, report, indent=2, sort_keys=True)
    return path


def post_mattermost_summary(report: dict[str, Any], webhook_url: str) -> None:
    summary = report["summary"]
    post_json_webhook(
        webhook_url,
        {
            "text": (
                f"[security-posture] env={report['environment']} "
                f"critical={summary['total_critical_cves']} "
                f"high={summary['total_high_cves']} "
                f"lowest_hardening={summary['lowest_hardening_index']} "
                f"new_lynis={summary['new_lynis_findings']}"
            )
        },
    )


def post_glitchtip_events(events: list[dict[str, Any]], webhook_url: str) -> None:
    for event in events:
        if event.get("event") != "platform.security.critical-finding":
            continue
        kind = event.get("kind", "security-finding")
        emit_glitchtip_event(
            webhook_url,
            {
                "message": f"Security posture critical finding: {kind}",
                "level": "error",
                "tags": {
                    "kind": kind,
                    "host": event.get("host", ""),
                },
                "extra": event,
            },
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0102 security posture workflow and write a receipt.")
    parser.add_argument("--env", default=DEFAULT_ENVIRONMENT, choices=ENVIRONMENT_CHOICES)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--playbook", type=Path, default=DEFAULT_PLAYBOOK)
    parser.add_argument("--lynis-dir", type=Path, default=DEFAULT_LYNIS_DIR)
    parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--suppressions", type=Path, default=DEFAULT_SUPPRESSIONS_PATH)
    parser.add_argument("--trivy-script", type=Path, default=DEFAULT_TRIVY_SCRIPT)
    parser.add_argument("--skip-lynis", action="store_true")
    parser.add_argument("--skip-trivy", action="store_true")
    parser.add_argument("--publish-nats", action="store_true")
    parser.add_argument("--mattermost-webhook-url")
    parser.add_argument("--glitchtip-event-url")
    parser.add_argument("--print-report-json", action="store_true")
    parser.add_argument("--audit-surface", default="manual")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        suppressions = load_suppressions(args.suppressions)
        previous_report = load_previous_report(args.receipt_dir)
        context = load_controller_context()

        host_reports: list[dict[str, Any]] = []
        if not args.skip_lynis:
            run_ansible_security_scan(
                inventory=args.inventory,
                playbook=args.playbook,
                output_dir=args.lynis_dir,
                hosts=default_lynis_hosts(args.env),
                bootstrap_key=context["bootstrap_key"],
                jump_host_addr=context["host_addr"],
            )
            host_reports = parse_path(
                args.lynis_dir,
                suppressions=suppressions,
                include_suppressed=False,
            )
        elif any(args.lynis_dir.glob("*-lynis-report.dat")):
            host_reports = parse_path(
                args.lynis_dir,
                suppressions=suppressions,
                include_suppressed=False,
            )
        else:
            raise RuntimeError(f"skip-lynis requested but no cached Lynis reports were found in {args.lynis_dir}")

        trivy_payloads: dict[str, list[dict[str, Any]]] = {}
        if not args.skip_trivy:
            for host in DEFAULT_TRIVY_HOSTS[args.env]:
                trivy_payloads[host] = run_remote_script(
                    context=context,
                    host=host,
                    script_path=args.trivy_script,
                    env={
                        "TRIVY_SKIP_DB_UPDATE": os.environ.get("TRIVY_SKIP_DB_UPDATE", "false"),
                        "TRIVY_CACHE_DIR": os.environ.get("TRIVY_CACHE_DIR", "/var/tmp/lv3-trivy-cache"),
                    },
                )

        report = build_report(
            environment=args.env,
            host_reports=host_reports,
            trivy_payloads=trivy_payloads,
            previous_report=previous_report,
        )
        receipt_path = write_receipt(args.receipt_dir, report)
        events = build_security_events(report)
        maybe_publish_nats(events, publish=args.publish_nats, context=context)
        maybe_write_metrics(report)

        mattermost_url = args.mattermost_webhook_url or maybe_read_secret_path(
            context["secret_manifest"], "mattermost_platform_findings_webhook_url"
        )
        if mattermost_url:
            post_mattermost_summary(report, mattermost_url)

        glitchtip_url = args.glitchtip_event_url or maybe_read_secret_path(
            context["secret_manifest"], "glitchtip_platform_findings_event_url"
        )
        if glitchtip_url:
            post_glitchtip_events(events, glitchtip_url)

        emit_event_best_effort(
            build_event(
                actor_class="automation",
                actor_id="security-posture-report",
                surface=args.audit_surface,
                action="security-posture.scan",
                target=f"security-posture/{args.env}",
                outcome="success",
                evidence_ref=str(receipt_path),
            ),
            context="security posture report",
            stderr=sys.stderr,
        )

        print(f"Receipt: {receipt_path}")
        if args.print_report_json:
            print(f"REPORT_JSON={json.dumps(report, separators=(',', ':'))}")
        _publish_receipt_to_outline(receipt_path)
        return 0 if report["summary"]["status"] == "clean" else 2 if report["summary"]["status"] == "warn" else 1
    except Exception as exc:
        return emit_cli_error("security posture", exc)


def _publish_receipt_to_outline(receipt_path: Path) -> None:
    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = Path(__file__).resolve().parents[1] / ".local" / "outline" / "api-token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return
    outline_tool = Path(__file__).resolve().parent / "outline_tool.py"
    if not outline_tool.exists() or not receipt_path.exists():
        return
    try:
        subprocess.run(
            [sys.executable, str(outline_tool), "receipt.publish", "--file", str(receipt_path)],
            capture_output=True,
            check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
