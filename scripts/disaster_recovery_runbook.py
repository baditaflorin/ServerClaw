#!/usr/bin/env python3
"""Render the ADR 0100 disaster-recovery execution plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from controller_automation_toolkit import REPO_ROOT, repo_path
from generate_dr_report import load_targets


DEFAULT_TARGETS_PATH = repo_path("config", "disaster-recovery-targets.json")


def _repo_key_path(repo_root: Path) -> Path:
    candidates = [repo_root, *repo_root.parents]
    for candidate in candidates:
        key_path = candidate / ".local" / "ssh" / "hetzner_llm_agents_ed25519"
        if key_path.exists():
            return key_path
    return repo_root / ".local" / "ssh" / "hetzner_llm_agents_ed25519"


def build_runbook_plan(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    key_path = _repo_key_path(repo_root)
    host_ssh = f"ssh -i {key_path} -o IdentitiesOnly=yes ops@100.118.189.95"
    guest_jump = (
        f"ssh -i {key_path} -o IdentitiesOnly=yes "
        f'-o ProxyCommand="ssh -i {key_path} -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p"'
    )
    targets = load_targets(DEFAULT_TARGETS_PATH)

    tiers = [
        {
            "id": "tier_0",
            "title": "Host reprovision",
            "deadline_minutes": 45,
            "steps": [
                {
                    "id": "inspect_witness_bundle",
                    "kind": "manual",
                    "summary": "Inspect the latest off-host witness bundle before restoring infrastructure state.",
                    "command": (
                        "LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT=${LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT:?set LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT} "
                        f"python3 {repo_root / 'scripts' / 'control_metadata_witness.py'} verify "
                        '--archive-root "$LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT"'
                    ),
                },
                {
                    "id": "reinstall_host",
                    "kind": "manual",
                    "summary": "Reinstall Debian 13 on replacement Hetzner hardware and restore Proxmox VE.",
                    "command": "Follow docs/runbooks/bootstrap-host.md and docs/adr/0003-0004 bootstrap path.",
                },
                {
                    "id": "verify_proxmox",
                    "kind": "verify",
                    "summary": "Verify the replacement host can answer Proxmox API requests.",
                    "command": f"{host_ssh} 'sudo pvesh get /version --output-format json-pretty'",
                },
            ],
        },
        {
            "id": "tier_1",
            "title": "Restore backup-lv3 from off-site storage",
            "deadline_minutes": 90,
            "steps": [
                {
                    "id": "list_offsite_backup_vm",
                    "kind": "manual",
                    "summary": "Locate the latest off-site backup for VM 160 on the external storage target.",
                    "command": f"{host_ssh} 'sudo pvesm list lv3-backup-offsite --vmid 160'",
                },
                {
                    "id": "restore_backup_vm",
                    "kind": "manual",
                    "summary": "Restore the backup-lv3 PBS VM from the off-site backup target.",
                    "command": (
                        f'{host_ssh} \'latest=$(sudo pvesm list lv3-backup-offsite --vmid 160 | awk "NR==2 {{print $1}}"); '
                        'sudo qmrestore "$latest" 160 --storage local --unique 0\''
                    ),
                },
                {
                    "id": "verify_pbs_api",
                    "kind": "verify",
                    "summary": "Verify PBS is answering on backup-lv3 after the restore.",
                    "command": (
                        f"{guest_jump} ops@10.10.10.60 "
                        "'sudo proxmox-backup-manager datastore list --output-format json'"
                    ),
                },
            ],
        },
        {
            "id": "tier_2",
            "title": "Restore stateful data services",
            "deadline_minutes": 150,
            "steps": [
                {
                    "id": "restore_postgres_vm",
                    "kind": "manual",
                    "summary": "Restore postgres-lv3 from PBS.",
                    "command": (
                        f'{host_ssh} \'latest=$(sudo pvesm list lv3-backup-pbs --vmid 150 | awk "NR==2 {{print $1}}"); '
                        'sudo qmrestore "$latest" 150 --storage local --unique 0\''
                    ),
                },
                {
                    "id": "restore_docker_runtime_vm",
                    "kind": "manual",
                    "summary": "Restore docker-runtime-lv3 from PBS.",
                    "command": (
                        f'{host_ssh} \'latest=$(sudo pvesm list lv3-backup-pbs --vmid 120 | awk "NR==2 {{print $1}}"); '
                        'sudo qmrestore "$latest" 120 --storage local --unique 0\''
                    ),
                },
                {
                    "id": "verify_step_ca",
                    "kind": "verify",
                    "summary": "Verify step-ca responds on the private control-plane path.",
                    "command": "curl -skf https://100.118.189.95:9443/health",
                },
                {
                    "id": "verify_openbao",
                    "kind": "verify",
                    "summary": "Verify OpenBao health after docker-runtime-lv3 is back.",
                    "command": "curl -skf https://100.118.189.95:8200/v1/sys/health",
                },
            ],
        },
        {
            "id": "tier_3",
            "title": "Restore edge and observability guests",
            "deadline_minutes": 195,
            "steps": [
                {
                    "id": "restore_monitoring_vm",
                    "kind": "manual",
                    "summary": "Restore monitoring-lv3 from PBS.",
                    "command": (
                        f'{host_ssh} \'latest=$(sudo pvesm list lv3-backup-pbs --vmid 140 | awk "NR==2 {{print $1}}"); '
                        'sudo qmrestore "$latest" 140 --storage local --unique 0\''
                    ),
                },
                {
                    "id": "restore_nginx_vm",
                    "kind": "manual",
                    "summary": "Restore nginx-lv3 from PBS.",
                    "command": (
                        f'{host_ssh} \'latest=$(sudo pvesm list lv3-backup-pbs --vmid 110 | awk "NR==2 {{print $1}}"); '
                        'sudo qmrestore "$latest" 110 --storage local --unique 0\''
                    ),
                },
                {
                    "id": "verify_grafana",
                    "kind": "verify",
                    "summary": "Verify Grafana responds through the public edge.",
                    "command": "curl -skf https://grafana.localhost/api/health",
                },
                {
                    "id": "verify_keycloak",
                    "kind": "verify",
                    "summary": "Verify Keycloak readiness through the public edge.",
                    "command": "curl -skf https://sso.localhost/health/ready",
                },
            ],
        },
        {
            "id": "tier_4",
            "title": "Restore build infrastructure",
            "deadline_minutes": 225,
            "steps": [
                {
                    "id": "restore_build_vm",
                    "kind": "manual",
                    "summary": "Restore docker-build-lv3 from PBS.",
                    "command": (
                        f'{host_ssh} \'latest=$(sudo pvesm list lv3-backup-pbs --vmid 130 | awk "NR==2 {{print $1}}"); '
                        'sudo qmrestore "$latest" 130 --storage local --unique 0\''
                    ),
                },
                {
                    "id": "verify_remote_build_gateway",
                    "kind": "verify",
                    "summary": "Verify the remote build gateway remains reachable.",
                    "command": f"{host_ssh} 'curl -sf http://10.10.10.30:8080/health || true'",
                },
            ],
        },
        {
            "id": "tier_5",
            "title": "Platform verification sweep",
            "deadline_minutes": 240,
            "steps": [
                {
                    "id": "dr_status",
                    "kind": "verify",
                    "summary": "Review repo-managed DR readiness and evidence.",
                    "command": f"python3 {repo_root / 'scripts' / 'generate_dr_report.py'}",
                },
                {
                    "id": "service_status",
                    "kind": "verify",
                    "summary": "Run the operator CLI status sweep against the restored platform.",
                    "command": f"python3 {repo_root / 'scripts' / 'lv3_cli.py'} status",
                },
                {
                    "id": "validate_runtime_backups",
                    "kind": "verify",
                    "summary": "Confirm PBS still exposes the expected protected VMs.",
                    "command": f"{host_ssh} 'sudo pvesh get /cluster/backup --output-format json-pretty'",
                },
            ],
        },
    ]

    return {
        "targets": targets,
        "tiers": tiers,
    }


def render_text(plan: dict[str, Any], tier_filter: str = "all") -> str:
    lines = [
        "ADR 0100 disaster recovery runbook",
        f"Target RTO: < {plan['targets']['platform_target']['rto_minutes'] // 60}h",
        f"Target RPO: < {plan['targets']['platform_target']['rpo_hours']}h",
    ]
    for tier in plan["tiers"]:
        if tier_filter != "all" and tier["id"] != tier_filter:
            continue
        lines.extend(["", f"{tier['id']}  {tier['title']}  (deadline {tier['deadline_minutes']}m)"])
        for index, step in enumerate(tier["steps"], start=1):
            lines.append(f"{index}. [{step['kind']}] {step['summary']}")
            lines.append(f"   {step['command']}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the ADR 0100 disaster-recovery plan.")
    parser.add_argument("--tier", default="all", help="Specific tier id to show, or 'all'.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_runbook_plan()
    if args.format == "json":
        print(json.dumps(plan, indent=2))
    else:
        print(render_text(plan, tier_filter=args.tier))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
