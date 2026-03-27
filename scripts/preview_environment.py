#!/usr/bin/env python3
"""Manage branch-scoped ephemeral preview environments on the governed Proxmox pool."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json, repo_path, write_json
from fixture_manager import (
    DEFAULT_EPHEMERAL_POLICY,
    apply_fixture,
    allocator_lock,
    archive_receipt,
    build_ephemeral_tag_metadata,
    build_ephemeral_tags,
    capture_ssh_fingerprint,
    compact_timestamp,
    converge_roles,
    default_fixture_context,
    ensure_ephemeral_lifetime_minutes,
    ensure_ephemeral_pool_capacity,
    ensure_runtime_files,
    fetch_cluster_resources,
    format_duration,
    isoformat,
    mac_from_vmid,
    parse_timestamp,
    proxmox_api_credentials,
    release_receipt,
    save_receipt,
    utc_now,
    verify_fixture,
    wait_for_ssh,
    destroy_fixture,
)
import fixture_manager
import vmid_allocator

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with jsonschema python ...'."
    ) from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_CATALOG_PATH = REPO_ROOT / "config" / "preview-environment-profiles.json"
SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "preview-environment-profiles.schema.json"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "build" / "platform-manifest.json"
LOCAL_ROOT = REPO_ROOT / ".local" / "preview-environments"
ACTIVE_STATE_DIR = LOCAL_ROOT / "active"
ARCHIVE_STATE_DIR = LOCAL_ROOT / "archive"
EVIDENCE_DIR = REPO_ROOT / "receipts" / "preview-environments"
LIVE_RECEIPTS_DIR = REPO_ROOT / "receipts" / "live-applies" / "preview"
ADR_PATH = Path("docs/adr/0185-branch-scoped-ephemeral-preview-environments.md")
WORKSTREAM_DOC_PATH = Path("docs/workstreams/adr-0185-branch-scoped-ephemeral-preview-environments.md")
RUNBOOK_PATH = Path("docs/runbooks/preview-environments.md")
WORKFLOW_ID = "adr-0185-branch-scoped-ephemeral-preview-environments-live-apply"
PREVIEW_VMID_RANGE = (910, 979)
DEFAULT_RECORDED_BY = os.environ.get("USER") or getpass.getuser()
PREVIEW_STATUS_ACTIVE = {"provisioning", "active", "validated"}


def repo_version() -> str:
    return repo_path("VERSION").read_text(encoding="utf-8").strip()


def git_output(*argv: str) -> str:
    completed = subprocess.run(
        ["git", *argv],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise RuntimeError(message)
    return completed.stdout.strip()


def current_branch() -> str:
    return git_output("rev-parse", "--abbrev-ref", "HEAD")


def current_commit() -> str:
    return git_output("rev-parse", "HEAD")


def sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        raise ValueError("preview identifiers must contain at least one alphanumeric character")
    return slug


def preview_slug(*, workstream: str, branch: str) -> str:
    base = sanitize_slug(workstream or branch)
    if len(base) <= 48:
        return base
    suffix = hashlib.sha1(branch.encode("utf-8")).hexdigest()[:8]
    return f"{base[:39].rstrip('-')}-{suffix}"


def preview_domain(slug: str, base_domain: str) -> str:
    return f"{slug}.{base_domain}"


def load_profile_catalog(path: Path = PROFILE_CATALOG_PATH) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object")
    return payload


def validate_profile_catalog(payload: dict[str, Any], *, path: Path = PROFILE_CATALOG_PATH) -> None:
    jsonschema.validate(instance=payload, schema=load_json(SCHEMA_PATH))

    network_pool = payload["network_pool"]
    network = ipaddress.IPv4Network(str(network_pool["network"]), strict=True)
    gateway = ipaddress.IPv4Address(str(network_pool["gateway"]))
    if gateway not in network:
        raise ValueError(f"{path}: network_pool.gateway must be inside {network}")

    start_ip = ipaddress.IPv4Address(str(network_pool["ip_range"][0]))
    end_ip = ipaddress.IPv4Address(str(network_pool["ip_range"][1]))
    if start_ip > end_ip:
        raise ValueError(f"{path}: network_pool.ip_range must be ascending")
    if start_ip not in network or end_ip not in network:
        raise ValueError(f"{path}: network_pool.ip_range must remain inside {network}")

    seen_profiles: set[str] = set()
    for profile in payload["profiles"]:
        profile_id = str(profile["id"])
        if profile_id in seen_profiles:
            raise ValueError(f"{path}: duplicate profile id '{profile_id}'")
        seen_profiles.add(profile_id)

        member_ids: set[str] = set()
        for member in profile["members"]:
            member_id = str(member["id"])
            if member_id in member_ids:
                raise ValueError(f"{path}: profile '{profile_id}' repeats member id '{member_id}'")
            member_ids.add(member_id)


def profile_choices(path: Path = PROFILE_CATALOG_PATH) -> tuple[str, ...]:
    payload = load_profile_catalog(path)
    validate_profile_catalog(payload, path=path)
    return tuple(sorted(str(profile["id"]) for profile in payload["profiles"]))


def profile_by_id(profile_id: str, *, path: Path = PROFILE_CATALOG_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = load_profile_catalog(path)
    validate_profile_catalog(payload, path=path)
    for profile in payload["profiles"]:
        if profile["id"] == profile_id:
            return payload, profile
    raise KeyError(f"Unknown preview profile '{profile_id}'")


def state_path(preview_id: str, *, archived: bool = False) -> Path:
    root = ARCHIVE_STATE_DIR if archived else ACTIVE_STATE_DIR
    return root / f"{preview_id}.json"


def active_states() -> list[dict[str, Any]]:
    if not ACTIVE_STATE_DIR.exists():
        return []
    rows = []
    for path in sorted(ACTIVE_STATE_DIR.glob("*.json")):
        payload = load_json(path)
        if isinstance(payload, dict):
            payload.setdefault("state_path", str(path))
            rows.append(payload)
    return rows


def active_preview_vmid_reservations() -> set[int]:
    vmids: set[int] = set()
    for state in active_states():
        for member in state.get("members", []):
            vm_id = member.get("vm_id")
            if isinstance(vm_id, int):
                vmids.add(vm_id)
    return vmids


def active_preview_ip_reservations() -> set[str]:
    ips: set[str] = set()
    for state in active_states():
        for member in state.get("members", []):
            ip_address = member.get("ip_address")
            if isinstance(ip_address, str) and ip_address:
                ips.add(ip_address)
    return ips


def allocate_preview_ips(catalog: dict[str, Any], count: int) -> list[str]:
    pool = catalog["network_pool"]
    start_ip = ipaddress.IPv4Address(str(pool["ip_range"][0]))
    end_ip = ipaddress.IPv4Address(str(pool["ip_range"][1]))
    reserved = active_preview_ip_reservations()
    available = []
    current = start_ip
    while current <= end_ip:
        candidate = str(current)
        if candidate not in reserved:
            available.append(candidate)
            if len(available) == count:
                return available
        current += 1
    raise RuntimeError("preview network pool exhausted")


def ensure_no_active_preview_for_slug(slug: str) -> None:
    for state in active_states():
        if state.get("preview_slug") == slug and state.get("status") in PREVIEW_STATUS_ACTIVE:
            raise RuntimeError(f"preview slug '{slug}' already has an active environment")


def build_member_definition(
    *,
    preview_id: str,
    slug: str,
    profile_id: str,
    member: dict[str, Any],
    ip_address: str,
    catalog: dict[str, Any],
    ttl_hours: float,
) -> dict[str, Any]:
    cidr = int(catalog["network_pool"]["cidr"])
    definition = {
        "fixture_id": f"preview-{profile_id}-{member['id']}",
        "template": member["template"],
        "vmid_range": list(PREVIEW_VMID_RANGE),
        "network": {
            "bridge": catalog["network_pool"]["bridge"],
            "ip_cidr": f"{ip_address}/{cidr}",
            "gateway": catalog["network_pool"]["gateway"],
        },
        "resources": dict(member["resources"]),
        "lifetime_minutes": int(round(ttl_hours * 60)),
        "extend_minutes": 0,
        "tags": [
            "ephemeral",
            "preview",
            f"preview-id-{preview_id}",
            f"preview-slug-{slug}",
            f"preview-profile-{profile_id}",
            f"preview-member-{member['id']}",
        ],
        "roles_under_test": list(member.get("roles_under_test", [])),
        "verify": list(member.get("smoke_checks", [])),
        "smoke_checks": list(member.get("smoke_checks", [])),
        "synthetic_checks": list(member.get("synthetic_checks", [])),
    }
    return definition


def build_member_receipt(
    *,
    preview_id: str,
    member_id: str,
    definition: dict[str, Any],
    vm_id: int,
    owner: str,
    purpose: str,
    policy: str,
) -> dict[str, Any]:
    now = utc_now()
    context = default_fixture_context()
    runtime_dir = LOCAL_ROOT / "runtime" / preview_id / member_id
    expires_at = now + dt.timedelta(minutes=int(definition["lifetime_minutes"]))
    metadata = build_ephemeral_tag_metadata(
        owner=owner,
        purpose=purpose,
        expires_epoch=int(expires_at.timestamp()),
        policy=policy,
    )
    network_ip = str(definition["network"]["ip_cidr"]).split("/", 1)[0]
    receipt = {
        "receipt_id": f"{preview_id}-{member_id}",
        "fixture_id": definition["fixture_id"],
        "status": "provisioning",
        "created_at": isoformat(now),
        "updated_at": isoformat(now),
        "lifetime_minutes": int(definition["lifetime_minutes"]),
        "extend_minutes": int(definition.get("extend_minutes", 0)),
        "owner": metadata.owner,
        "purpose": metadata.purpose,
        "policy": metadata.policy,
        "expires_epoch": metadata.expires_epoch,
        "expires_at": isoformat(expires_at),
        "ephemeral_tags": build_ephemeral_tags(metadata),
        "definition_path": str(PROFILE_CATALOG_PATH.relative_to(REPO_ROOT)),
        "runtime_dir": str(runtime_dir.relative_to(REPO_ROOT)),
        "vm_id": vm_id,
        "ip_address": network_ip,
        "mac_address": definition.get("mac_address", mac_from_vmid(vm_id)),
        "definition": definition,
        "context": context,
        "member_id": member_id,
        "name": f"{preview_id}-{member_id}",
    }
    return receipt


def save_state(payload: dict[str, Any], *, archived: bool = False) -> Path:
    path = state_path(str(payload["preview_id"]), archived=archived)
    write_json(path, payload, indent=2, sort_keys=True)
    return path


def load_state(preview_id: str, *, allow_archived: bool = False) -> dict[str, Any]:
    for archived in (False, True) if allow_archived else (False,):
        path = state_path(preview_id, archived=archived)
        if path.exists():
            payload = load_json(path)
            if isinstance(payload, dict):
                payload.setdefault("state_path", str(path))
                return payload
    raise FileNotFoundError(f"Unknown preview environment '{preview_id}'")


def summarize_check_result(result: dict[str, Any]) -> str:
    if "status" in result:
        return f"{result.get('target', 'target')} status={result['status']}"
    if "stdout" in result and result.get("stdout"):
        return str(result["stdout"]).strip()
    if "error" in result:
        return str(result["error"])
    if "stderr" in result and result.get("stderr"):
        return str(result["stderr"]).strip()
    return str(result.get("target") or "ok")


def run_named_checks(receipt: dict[str, Any], checks: list[dict[str, Any]], *, phase: str) -> dict[str, Any]:
    results = []
    for index, check in enumerate(checks):
        timeout_seconds = int(check.get("timeout_seconds", 30))
        if "command" in check:
            result = fixture_manager.verify_command(receipt, str(check["command"]), timeout_seconds)
            label = f"{phase}:{receipt['member_id']}:command:{index + 1}"
        elif "port" in check:
            result = fixture_manager.verify_tcp(receipt["ip_address"], int(check["port"]), timeout_seconds)
            label = f"{phase}:{receipt['member_id']}:port:{index + 1}"
        else:
            result = fixture_manager.verify_http(str(check["url"]), int(check.get("expected_status", 200)), timeout_seconds)
            label = f"{phase}:{receipt['member_id']}:url:{index + 1}"
        results.append(
            {
                "label": label,
                "member_id": receipt["member_id"],
                "ok": bool(result.get("ok")),
                "observed": summarize_check_result(result),
                "raw": result,
            }
        )
    return {
        "phase": phase,
        "ok": all(result["ok"] for result in results) if results else True,
        "results": results,
    }


def build_manifest_snapshot(manifest_path: Path) -> dict[str, Any]:
    payload = load_json(manifest_path)
    if not isinstance(payload, dict):
        raise ValueError(f"{manifest_path} must be a JSON object")
    services = payload.get("services", [])
    return {
        "path": str(manifest_path.relative_to(REPO_ROOT)),
        "generated_at": payload.get("generated_at", ""),
        "version": payload.get("manifest_version", ""),
        "service_count": len(services) if isinstance(services, list) else 0,
    }


def build_preview_state(
    *,
    preview_id: str,
    slug: str,
    domain: str,
    branch: str,
    workstream: str,
    profile: dict[str, Any],
    manifest_path: Path,
    owner: str,
    ttl_hours: float,
    policy: str,
    members: list[dict[str, Any]],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    expires_at = now + dt.timedelta(hours=ttl_hours)
    return {
        "schema_version": "1.0.0",
        "preview_id": preview_id,
        "preview_slug": slug,
        "preview_domain": domain,
        "status": "provisioning",
        "created_at": isoformat(now),
        "updated_at": isoformat(now),
        "owner": owner,
        "branch": branch,
        "workstream": workstream,
        "profile_id": profile["id"],
        "profile_name": profile["name"],
        "profile_description": profile["description"],
        "service_subset": list(profile.get("service_subset", [])),
        "ttl_hours": ttl_hours,
        "expires_at": isoformat(expires_at),
        "auto_destroy_policy": {
            "policy": policy,
            "reaper": "adr-0106-ephemeral-environment-lifecycle",
        },
        "network_boundary": {
            "bridge": catalog["network_pool"]["bridge"],
            "network": catalog["network_pool"]["network"],
            "gateway": catalog["network_pool"]["gateway"],
            "ip_range": list(catalog["network_pool"]["ip_range"]),
        },
        "manifest_snapshot": build_manifest_snapshot(manifest_path),
        "members": members,
        "validation": {},
    }


def preview_evidence_path(preview_id: str) -> Path:
    return EVIDENCE_DIR / f"{preview_id}.json"


def preview_live_receipt_path(preview_id: str) -> Path:
    return LIVE_RECEIPTS_DIR / f"{preview_id}.json"


def repo_relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def result_to_receipt_line(phase: str, report: dict[str, Any]) -> dict[str, str]:
    passed = sum(1 for item in report.get("results", []) if item.get("ok"))
    total = len(report.get("results", []))
    result = "pass" if report.get("ok") else "fail"
    observed = f"{passed}/{total} checks passed" if total else "no checks declared"
    return {"check": phase, "result": result, "observed": observed}


def build_live_apply_receipt(state: dict[str, Any], evidence_path: Path) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    targets = [
        {"kind": "preview_environment", "name": state["preview_domain"]},
    ]
    for member in state.get("members", []):
        targets.append(
            {
                "kind": "vm",
                "name": member["name"],
                "vmid": member["vm_id"],
                "address": member["ip_address"],
            }
        )

    verification = [
        {
            "check": "Preview provisioning",
            "result": "pass" if state.get("status") == "destroyed" else "partial",
            "observed": f"{len(state.get('members', []))} preview VM(s) provisioned on {state['network_boundary']['bridge']}",
        }
    ]
    validation = state.get("validation", {})
    for phase in ("smoke", "synthetic"):
        report = validation.get(phase)
        if isinstance(report, dict):
            verification.append(result_to_receipt_line(f"Preview {phase}", report))
    verification.append(
        {
            "check": "Preview teardown",
            "result": "pass" if state.get("destroyed_at") else "partial",
            "observed": f"Destroyed preview environment {state['preview_domain']}",
        }
    )

    return {
        "schema_version": "1.0.0",
        "receipt_id": state["preview_id"],
        "environment": "preview",
        "applied_on": today,
        "recorded_on": today,
        "recorded_at": isoformat(utc_now()),
        "recorded_by": DEFAULT_RECORDED_BY,
        "source_commit": current_commit(),
        "repo_version_context": repo_version(),
        "workflow_id": WORKFLOW_ID,
        "adr": "0185",
        "summary": (
            f"Created, validated, and destroyed preview environment {state['preview_domain']} "
            f"from branch {state['branch']} using profile {state['profile_id']}."
        ),
        "targets": targets,
        "verification": verification,
        "evidence_refs": [
            repo_relative_or_absolute(evidence_path),
            str(ADR_PATH),
            str(WORKSTREAM_DOC_PATH),
            str(RUNBOOK_PATH),
        ],
        "notes": [
            f"Workstream: {state['workstream']}",
            f"Service subset: {', '.join(state.get('service_subset', [])) or 'none declared'}",
            "Merge to main must still update README.md, VERSION, changelog.md, and versions/stack.yaml only during the final integrated replay.",
        ],
    }


def finalize_preview_evidence(state: dict[str, Any]) -> tuple[Path, Path]:
    evidence_path = preview_evidence_path(state["preview_id"])
    live_receipt_path = preview_live_receipt_path(state["preview_id"])
    write_json(evidence_path, state, indent=2, sort_keys=True)
    live_receipt = build_live_apply_receipt(state, evidence_path)
    write_json(live_receipt_path, live_receipt, indent=2, sort_keys=True)
    return evidence_path, live_receipt_path


def create_preview(
    *,
    workstream: str,
    branch: str | None,
    profile_id: str,
    manifest_path: Path,
    owner: str | None,
    ttl_hours: float | None,
    policy: str,
) -> dict[str, Any]:
    catalog, profile = profile_by_id(profile_id)
    resolved_branch = branch or current_branch()
    resolved_workstream = workstream
    slug = preview_slug(workstream=resolved_workstream, branch=resolved_branch)
    ensure_no_active_preview_for_slug(slug)
    resolved_owner = sanitize_slug(owner or getpass.getuser())
    resolved_ttl_hours = ttl_hours if ttl_hours is not None else float(profile["ttl_hours"])
    ttl_minutes = ensure_ephemeral_lifetime_minutes(
        lifetime_hours=resolved_ttl_hours,
        definition={"lifetime_minutes": int(round(float(profile["ttl_hours"]) * 60))},
        policy=policy,
        extend=False,
    )
    preview_id = f"{dt.date.today().isoformat()}-adr-0185-{slug}-{compact_timestamp(utc_now()).lower()}"
    domain = preview_domain(slug, str(catalog["default_base_domain"]))
    allocated_ips = allocate_preview_ips(catalog, len(profile["members"]))

    endpoint, api_token = proxmox_api_credentials()
    cluster_resources = fetch_cluster_resources(endpoint, api_token)
    members: list[dict[str, Any]] = []
    lock_handle = allocator_lock()
    try:
        used_vmids = vmid_allocator.parse_cluster_vmids({"data": cluster_resources})
        used_vmids.update(fixture_manager.reserved_vmids())
        used_vmids.update(active_preview_vmid_reservations())
        for member, ip_address in zip(profile["members"], allocated_ips, strict=True):
            definition = build_member_definition(
                preview_id=preview_id,
                slug=slug,
                profile_id=profile_id,
                member=member,
                ip_address=ip_address,
                catalog=catalog,
                ttl_hours=resolved_ttl_hours,
            )
            ensure_ephemeral_pool_capacity(definition, cluster_resources)
            vm_id = vmid_allocator.allocate_free_vmid(used_vmids, PREVIEW_VMID_RANGE[0], PREVIEW_VMID_RANGE[1])
            used_vmids.add(vm_id)
            receipt = build_member_receipt(
                preview_id=preview_id,
                member_id=str(member["id"]),
                definition=definition,
                vm_id=vm_id,
                owner=resolved_owner,
                purpose=f"{slug}-{member['id']}",
                policy=policy,
            )
            receipt["lifetime_minutes"] = ttl_minutes
            receipt["expires_at"] = isoformat(parse_timestamp(receipt["created_at"]) + dt.timedelta(minutes=ttl_minutes))
            receipt["expires_epoch"] = int(parse_timestamp(receipt["expires_at"]).timestamp())
            receipt["ephemeral_tags"] = build_ephemeral_tags(
                build_ephemeral_tag_metadata(
                    owner=receipt["owner"],
                    purpose=receipt["purpose"],
                    expires_epoch=receipt["expires_epoch"],
                    policy=policy,
                )
            )
            members.append(receipt)
            cluster_resources.append(
                {
                    "vmid": vm_id,
                    "cpus": int(definition["resources"]["cores"]),
                    "maxmem": int(definition["resources"]["memory_mb"]) * 1024 * 1024,
                    "maxdisk": int(definition["resources"]["disk_gb"]) * 1024 * 1024 * 1024,
                    "type": "qemu",
                }
            )
    finally:
        import fcntl

        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()

    state = build_preview_state(
        preview_id=preview_id,
        slug=slug,
        domain=domain,
        branch=resolved_branch,
        workstream=resolved_workstream,
        profile=profile,
        manifest_path=manifest_path,
        owner=resolved_owner,
        ttl_hours=resolved_ttl_hours,
        policy=policy,
        members=members,
        catalog=catalog,
    )
    save_state(state)

    provisioned: list[dict[str, Any]] = []
    try:
        for member in members:
            save_receipt(member)
            runtime_dir = ensure_runtime_files(member)
            apply_fixture(runtime_dir, endpoint, api_token)
            wait_for_ssh(member)
            converge_roles(member)
            verification = verify_fixture(member, member["definition"])
            if not verification["ok"]:
                raise RuntimeError(f"preview smoke checks failed for member '{member['member_id']}'")
            member["status"] = "active"
            member["ssh_fingerprint"] = capture_ssh_fingerprint(member)
            member["verification"] = verification
            member["name"] = f"{preview_id}-{member['member_id']}"
            save_receipt(member)
            provisioned.append(member)
        state["status"] = "active"
        state["updated_at"] = isoformat(utc_now())
        state["validation"]["smoke"] = {
            "phase": "smoke",
            "ok": all(member.get("verification", {}).get("ok") for member in members),
            "results": [
                {
                    "label": f"smoke:{member['member_id']}",
                    "member_id": member["member_id"],
                    "ok": bool(member.get("verification", {}).get("ok")),
                    "observed": f"{len(member.get('verification', {}).get('checks', []))} smoke checks passed",
                }
                for member in members
            ],
        }
        save_state(state)
        return state
    except Exception:
        for member in reversed(provisioned or members):
            runtime_dir = REPO_ROOT / member["runtime_dir"]
            try:
                destroy_fixture(runtime_dir, endpoint, api_token)
            except Exception:
                pass
            member["status"] = "failed"
            archive_receipt(member)
            release_receipt(member)
        state["status"] = "failed"
        state["updated_at"] = isoformat(utc_now())
        save_state(state, archived=True)
        active_path = state_path(preview_id)
        if active_path.exists():
            active_path.unlink()
        raise


def validate_preview(preview_id: str) -> dict[str, Any]:
    state = load_state(preview_id)
    synthetic_results = []
    smoke_results = []
    for member in state.get("members", []):
        smoke_results.extend(run_named_checks(member, list(member["definition"].get("smoke_checks", [])), phase="smoke")["results"])
        synthetic_results.extend(
            run_named_checks(member, list(member["definition"].get("synthetic_checks", [])), phase="synthetic")["results"]
        )
    state["validation"]["smoke"] = {
        "phase": "smoke",
        "ok": all(result["ok"] for result in smoke_results) if smoke_results else True,
        "results": smoke_results,
    }
    state["validation"]["synthetic"] = {
        "phase": "synthetic",
        "ok": all(result["ok"] for result in synthetic_results) if synthetic_results else True,
        "results": synthetic_results,
    }
    state["status"] = "validated" if state["validation"]["synthetic"]["ok"] else "active"
    state["updated_at"] = isoformat(utc_now())
    save_state(state)
    return state


def destroy_preview(preview_id: str) -> dict[str, Any]:
    state = load_state(preview_id)
    endpoint, api_token = proxmox_api_credentials()
    for member in reversed(state.get("members", [])):
        runtime_dir = REPO_ROOT / member["runtime_dir"]
        destroy_fixture(runtime_dir, endpoint, api_token)
        member["status"] = "destroyed"
        member["destroyed_at"] = isoformat(utc_now())
        archive_receipt(member)
        release_receipt(member)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
    state["status"] = "destroyed"
    state["destroyed_at"] = isoformat(utc_now())
    state["updated_at"] = state["destroyed_at"]
    evidence_path, live_receipt_path = finalize_preview_evidence(state)
    archived_path = save_state(state, archived=True)
    active_path = state_path(preview_id)
    if active_path.exists():
        active_path.unlink()
    state["evidence_path"] = str(evidence_path.relative_to(REPO_ROOT))
    state["live_receipt_path"] = str(live_receipt_path.relative_to(REPO_ROOT))
    state["state_path"] = str(archived_path)
    return state


def list_previews() -> list[dict[str, Any]]:
    rows = []
    for state in active_states():
        remaining = format_duration(parse_timestamp(str(state["expires_at"])) - utc_now())
        rows.append(
            {
                "preview_id": state["preview_id"],
                "status": state.get("status", "unknown"),
                "branch": state.get("branch", ""),
                "workstream": state.get("workstream", ""),
                "profile_id": state.get("profile_id", ""),
                "preview_domain": state.get("preview_domain", ""),
                "remaining": remaining,
            }
        )
    return rows


def render_preview(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "preview_id": state["preview_id"],
        "status": state.get("status", "unknown"),
        "preview_domain": state.get("preview_domain"),
        "branch": state.get("branch"),
        "workstream": state.get("workstream"),
        "profile_id": state.get("profile_id"),
        "service_subset": state.get("service_subset", []),
        "expires_at": state.get("expires_at"),
        "members": [
            {
                "member_id": member.get("member_id"),
                "name": member.get("name"),
                "vm_id": member.get("vm_id"),
                "ip_address": member.get("ip_address"),
                "status": member.get("status"),
            }
            for member in state.get("members", [])
        ],
        "validation": state.get("validation", {}),
        "evidence_path": state.get("evidence_path"),
        "live_receipt_path": state.get("live_receipt_path"),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    validate_catalog_cmd = subparsers.add_parser("validate-catalog", help="Validate the preview profile catalog.")
    validate_catalog_cmd.add_argument("--catalog", type=Path, default=PROFILE_CATALOG_PATH)

    create = subparsers.add_parser("create", help="Provision a new branch-scoped preview environment.")
    create.add_argument("--workstream", required=True)
    create.add_argument("--branch")
    create.add_argument("--profile", default="runtime-smoke", choices=profile_choices())
    create.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    create.add_argument("--owner")
    create.add_argument("--ttl-hours", type=float)
    create.add_argument("--policy", default=DEFAULT_EPHEMERAL_POLICY)
    create.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate", help="Run smoke and synthetic validation against an active preview.")
    validate.add_argument("--preview-id", required=True)
    validate.add_argument("--json", action="store_true")

    destroy = subparsers.add_parser("destroy", help="Destroy a preview and write durable evidence.")
    destroy.add_argument("--preview-id", required=True)
    destroy.add_argument("--json", action="store_true")

    list_cmd = subparsers.add_parser("list", help="List active previews.")
    list_cmd.add_argument("--json", action="store_true")

    show = subparsers.add_parser("show", help="Show one preview environment.")
    show.add_argument("--preview-id", required=True)
    show.add_argument("--archived", action="store_true")
    show.add_argument("--json", action="store_true")

    return parser.parse_args(argv or sys.argv[1:])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.action == "validate-catalog":
            payload = load_profile_catalog(args.catalog)
            validate_profile_catalog(payload, path=args.catalog)
            print(f"Preview environment catalog OK: {args.catalog}")
            return 0
        if args.action == "create":
            state = create_preview(
                workstream=args.workstream,
                branch=args.branch,
                profile_id=args.profile,
                manifest=args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest,
                owner=args.owner,
                ttl_hours=args.ttl_hours,
                policy=args.policy,
            )
            payload = render_preview(state)
            print(json.dumps(payload, indent=2) if args.json else f"Created preview {payload['preview_id']} {payload['preview_domain']}")
            return 0
        if args.action == "validate":
            state = validate_preview(args.preview_id)
            payload = render_preview(state)
            print(json.dumps(payload, indent=2) if args.json else f"Validated preview {payload['preview_id']}")
            return 0 if state.get("validation", {}).get("synthetic", {}).get("ok", True) else 1
        if args.action == "destroy":
            state = destroy_preview(args.preview_id)
            payload = render_preview(state)
            print(json.dumps(payload, indent=2) if args.json else f"Destroyed preview {payload['preview_id']}")
            return 0
        if args.action == "list":
            payload = list_previews()
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                for row in payload:
                    print(
                        f"{row['preview_id']}  {row['status']}  {row['profile_id']}  "
                        f"{row['preview_domain']}  remaining={row['remaining']}"
                    )
            return 0
        state = load_state(args.preview_id, allow_archived=args.archived)
        payload = render_preview(state)
        print(json.dumps(payload, indent=2) if args.json else f"{payload['preview_id']}  {payload['status']}  {payload['preview_domain']}")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI entrypoint
        print(f"preview-environment error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
