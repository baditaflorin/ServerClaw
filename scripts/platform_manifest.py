#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path, write_json
from deployment_history import collect_live_apply_entries
from maintenance_window_tool import list_active_windows_best_effort
from slo_tracking import build_slo_status_entries

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
    ) from exc


MANIFEST_VERSION = "1.0.0"
ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T")
TRUST_ORDER = {"T1": 1, "T2": 2, "T3": 3}
RUNTIME_SLO_STATUS_MAP = {
    "healthy": ("healthy", 0.95, True),
    "warning": ("degraded", 0.60, False),
    "critical": ("critical", 0.20, False),
    "unknown": ("degraded", 0.50, False),
}

VERSION_PATH = repo_path("VERSION")
STACK_PATH = repo_path("versions", "stack.yaml")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
STATIC_CONFIG_PATH = repo_path("config", "manifest-static.yaml")
SCHEMA_PATH = repo_path("docs", "schema", "platform-manifest.schema.json")
ADR_DIR = repo_path("docs", "adr")
RUNBOOK_DIR = repo_path("docs", "runbooks")
RELEASE_NOTES_DIR = repo_path("docs", "release-notes")
DEFAULT_OUTPUT_PATH = repo_path("build", "platform-manifest.json")
DEFAULT_INCIDENT_DIR = repo_path(".local", "triage", "reports")
WORKFLOW_CATALOG_PATH = repo_path("config", "workflow-catalog.json")
WORKFLOW_DEFAULTS_PATH = repo_path("config", "workflow-defaults.yaml")


def current_repo_root() -> Path:
    return VERSION_PATH.parent


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_semver(value: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", value.strip())
    if not match:
        raise ValueError(f"invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def semver_sort_key(path: Path) -> tuple[int, int, int]:
    return parse_semver(path.stem)


def read_h1(path: Path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def parse_metadata_block(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.startswith("- "):
            if metadata:
                break
            continue
        key, _, value = line[2:].partition(":")
        if value:
            metadata[key.strip()] = value.strip()
    return metadata


def count_runbook_steps(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if re.match(r"^\d+\.\s+", line.strip()))


def relative_repo_path(path: Path) -> str:
    return str(path.relative_to(current_repo_root()).as_posix())


def release_note_paths() -> list[Path]:
    return sorted(
        (path for path in RELEASE_NOTES_DIR.glob("*.md") if path.stem != "README"),
        key=semver_sort_key,
    )


def parse_release_note(path: Path) -> dict[str, Any]:
    released_on = ""
    summary_items: list[str] = []
    in_summary = False
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if raw_line.startswith("Released on:"):
            released_on = raw_line.partition(":")[2].strip()
            continue
        if raw_line.startswith("## "):
            in_summary = raw_line == "## Summary"
            continue
        if in_summary and line.startswith("- "):
            summary_items.append(line[2:].strip())
    return {
        "version": path.stem,
        "released_on": released_on,
        "summary_items": summary_items,
        "path": path,
    }


def build_recent_changes(current_version: str) -> dict[str, str]:
    notes = [parse_release_note(path) for path in release_note_paths()]
    if not notes:
        raise ValueError("docs/release-notes has no versioned release notes")

    current_note = next((note for note in notes if note["version"] == current_version), notes[-1])
    current_index = notes.index(current_note)
    previous_version = notes[current_index - 1]["version"] if current_index > 0 else current_note["version"]
    summary_items = current_note["summary_items"] or ["Repository automation updated without a recorded summary."]
    return {
        "last_version": previous_version,
        "deployed_at": current_note["released_on"] or utc_now().date().isoformat(),
        "summary": " ".join(summary_items[:2]),
        "release_notes_url": relative_repo_path(current_note["path"]),
    }


def load_static_config() -> dict[str, Any]:
    payload = load_yaml(STATIC_CONFIG_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{STATIC_CONFIG_PATH} must be a mapping")
    if payload.get("schema_version") != "1.0.0":
        raise ValueError(f"{STATIC_CONFIG_PATH} must declare schema_version 1.0.0")
    return payload


def load_stack() -> dict[str, Any]:
    payload = load_yaml(STACK_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{STACK_PATH} must be a mapping")
    return payload


def load_service_catalog() -> dict[str, Any]:
    payload = load_json(SERVICE_CATALOG_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{SERVICE_CATALOG_PATH} must be an object")
    services = payload.get("services")
    if not isinstance(services, list) or not services:
        raise ValueError(f"{SERVICE_CATALOG_PATH} must define a non-empty services list")
    return payload


def load_workflow_catalog_data() -> dict[str, Any]:
    payload = load_json(WORKFLOW_CATALOG_PATH)
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError(f"{WORKFLOW_CATALOG_PATH} must define a workflows object")
    return payload


def load_workflow_defaults_data() -> dict[str, Any]:
    payload = load_yaml(WORKFLOW_DEFAULTS_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{WORKFLOW_DEFAULTS_PATH} must be a mapping")
    return payload


def workflow_risk_class(workflow: dict[str, Any]) -> str:
    live_impact = workflow["live_impact"]
    execution_class = workflow.get("execution_class", "mutation")
    if live_impact == "repo_only" and execution_class == "diagnostic":
        return "LOW"
    if live_impact == "repo_only":
        return "MEDIUM"
    if execution_class == "diagnostic":
        return "MEDIUM"
    return "HIGH"


def trust_tier_for_risk(risk_class: str) -> str:
    return {"LOW": "T1", "MEDIUM": "T2", "HIGH": "T3"}[risk_class]


def workflow_tags(workflow_id: str, workflow: dict[str, Any]) -> list[str]:
    tags = {
        workflow_id.replace("_", "-"),
        workflow["live_impact"].replace("_", "-"),
        workflow.get("execution_class", "mutation"),
    }
    if workflow.get("preflight", {}).get("required"):
        tags.add("preflight")
    if workflow.get("validation_targets"):
        tags.add("validated")
    return sorted(tags)


def build_workflow_capabilities() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    catalog = load_workflow_catalog_data()
    defaults = load_workflow_defaults_data().get("default_budget", {})
    workflows = []
    runbooks: dict[str, dict[str, Any]] = {}
    for workflow_id, workflow in sorted(catalog["workflows"].items()):
        if workflow.get("lifecycle_status") != "active":
            continue
        budget = dict(defaults)
        if isinstance(workflow.get("budget"), dict):
            budget.update(workflow["budget"])
        risk_class = workflow_risk_class(workflow)
        trust_tier = trust_tier_for_risk(risk_class)
        automation_eligible = workflow.get("execution_class", "mutation") in {"mutation", "diagnostic"}
        workflows.append(
            {
                "id": workflow_id,
                "description": workflow["description"],
                "tags": workflow_tags(workflow_id, workflow),
                "risk_class": risk_class,
                "automation_eligible": automation_eligible,
                "agent_trust_required": trust_tier,
                "execution_class": workflow.get("execution_class", "mutation"),
                "live_impact": workflow["live_impact"],
                "budget": budget,
                "runbook": workflow["owner_runbook"],
            }
        )
        if not automation_eligible:
            continue
        runbook_path = repo_path(workflow["owner_runbook"])
        bucket = runbooks.setdefault(
            workflow["owner_runbook"],
            {
                "id": runbook_path.stem,
                "title": read_h1(runbook_path),
                "agent_trust_required": trust_tier,
                "steps": count_runbook_steps(runbook_path),
                "path": workflow["owner_runbook"],
                "workflow_ids": [],
            },
        )
        if TRUST_ORDER[trust_tier] > TRUST_ORDER[bucket["agent_trust_required"]]:
            bucket["agent_trust_required"] = trust_tier
        bucket["workflow_ids"].append(workflow_id)
    for payload in runbooks.values():
        payload["workflow_ids"] = sorted(payload["workflow_ids"])
    return workflows, sorted(runbooks.values(), key=lambda item: item["id"])


def build_registered_agents(static_config: dict[str, Any], stack: dict[str, Any]) -> list[dict[str, Any]]:
    configured = {
        entry["agent_id"]: dict(entry)
        for entry in static_config.get("registered_agents", [])
        if isinstance(entry, dict) and entry.get("agent_id")
    }
    identities = (
        stack.get("desired_state", {})
        .get("identity_taxonomy", {})
        .get("managed_identities", [])
    )
    by_identity = {
        identity.get("id"): identity
        for identity in identities
        if isinstance(identity, dict) and identity.get("id")
    }
    result = []
    for agent_id, entry in sorted(configured.items()):
        source_identity_id = entry.get("source_identity_id")
        identity = by_identity.get(source_identity_id, {})
        result.append(
            {
                "agent_id": agent_id,
                "trust_tier": entry["trust_tier"],
                "description": entry["description"],
                "status": entry.get("status", "active"),
                "principal": entry.get("principal") or identity.get("principal") or agent_id,
                "owner": entry.get("owner") or identity.get("owner") or "Repository automation",
                **({"source_identity_id": source_identity_id} if source_identity_id else {}),
            }
        )
    return result


def live_apply_index(service_catalog: dict[str, Any]) -> dict[str, str]:
    latest: dict[str, dt.datetime] = {}
    entries = collect_live_apply_entries(service_catalog=service_catalog)
    for entry in entries:
        ts = parse_datetime(entry.get("timestamp"))
        if ts is None:
            continue
        for service_id in entry.get("service_ids", []):
            current = latest.get(service_id)
            if current is None or ts > current:
                latest[service_id] = ts
    return {service_id: isoformat(timestamp) for service_id, timestamp in latest.items()}


def build_health_section(
    service_catalog: dict[str, Any],
    *,
    prometheus_url: str | None,
    active_maintenance_ids: set[str],
) -> dict[str, Any]:
    services = service_catalog["services"]
    slo_entries = build_slo_status_entries(prometheus_url=prometheus_url or "")
    slo_by_service = {entry["service_id"]: entry for entry in slo_entries}
    live_apply_by_service = live_apply_index(service_catalog)
    payload: dict[str, Any] = {}
    runtime_used = False

    for service in sorted(services, key=lambda item: item["id"]):
        if service.get("lifecycle_status") != "active":
            continue
        service_id = service["id"]
        maintenance_active = service_id in active_maintenance_ids or "all" in active_maintenance_ids
        slo_entry = slo_by_service.get(service_id)
        if slo_entry and slo_entry.get("metrics_available"):
            status, score, safe_to_act = RUNTIME_SLO_STATUS_MAP.get(
                slo_entry.get("status", "unknown"),
                ("degraded", 0.50, False),
            )
            reason = f"SLO status is {slo_entry['status']}."
            source = "runtime_slo"
            runtime_used = True
        else:
            score = 0.35
            missing = []
            environments = service.get("environments", {})
            production_binding = environments.get("production", {}) if isinstance(environments, dict) else {}
            if production_binding.get("status") == "active":
                score += 0.15
            else:
                missing.append("production binding")
            if service.get("health_probe_id"):
                score += 0.20
            else:
                missing.append("health probe")
            if slo_entry:
                score += 0.15
            else:
                missing.append("SLO")
            if service_id in live_apply_by_service:
                score += 0.15
            else:
                missing.append("live apply evidence")
            if service.get("public_url") or service.get("internal_url"):
                score += 0.10
            score = min(score, 0.95)
            if score >= 0.80:
                status = "healthy"
            elif score >= 0.60:
                status = "degraded"
            else:
                status = "critical"
            safe_to_act = status == "healthy"
            reason = (
                "Repository evidence is complete enough for normal automation."
                if not missing
                else "Repository evidence is sufficient; missing supplemental evidence: " + ", ".join(missing) + "."
            )
            source = "repo_evidence"
        if maintenance_active:
            safe_to_act = False
            reason = f"{reason} Active maintenance window suppresses automation."
        payload[service_id] = {
            "service_name": service["name"],
            "status": status,
            "score": round(score, 2),
            "safe_to_act": safe_to_act,
            "source": source,
            "reason": reason,
            "lifecycle_status": service["lifecycle_status"],
            **({"primary_url": service["public_url"]} if service.get("public_url") else {}),
            **({"primary_url": service["internal_url"]} if not service.get("public_url") and service.get("internal_url") else {}),
            **({"maintenance_active": True} if maintenance_active else {}),
            **({"last_live_apply": live_apply_by_service[service_id]} if service_id in live_apply_by_service else {}),
            **({"slo_status": slo_entry.get("status", "unknown")} if slo_entry else {}),
        }
    statuses = {entry["status"] for entry in payload.values()}
    summary = "healthy"
    if "critical" in statuses:
        summary = "critical"
    elif "degraded" in statuses:
        summary = "degraded"
    return {"summary": summary, "mode": "runtime_slo" if runtime_used else "repo_evidence", "services": payload}


def normalize_window_id(service_id: str, window: dict[str, Any]) -> str:
    raw = window.get("window_id") or window.get("id") or f"maintenance-{service_id}"
    return str(raw)


def build_maintenance_section() -> dict[str, Any]:
    windows = list_active_windows_best_effort(stderr=io.StringIO())
    items = []
    for service_id, window in sorted(windows.items()):
        started_at = window.get("starts_at") or window.get("opened_at")
        duration = int(window.get("duration_minutes") or 60)
        started = parse_datetime(started_at) or utc_now()
        items.append(
            {
                "window_id": normalize_window_id(service_id, window),
                "service_id": service_id,
                "description": window.get("reason") or window.get("description") or "Maintenance window",
                "starts_at": isoformat(started),
                "ends_at": isoformat(started + dt.timedelta(minutes=duration)),
                "duration_minutes": duration,
            }
        )
    return {"active_windows": items, "upcoming_windows": []}


def active_maintenance_ids(maintenance: dict[str, Any]) -> set[str]:
    return {item["service_id"] for item in maintenance["active_windows"]}


def build_incidents_section(incident_dir: Path) -> dict[str, Any]:
    if not incident_dir.exists():
        return {"open_count": 0, "items": []}
    items = []
    for path in sorted(incident_dir.glob("*.json"), reverse=True):
        payload = load_json(path)
        if not isinstance(payload, dict):
            continue
        report_state = str(payload.get("loop_state") or "PROPOSING")
        if report_state.upper() in {"RESOLVED", "CLOSED"}:
            continue
        hypotheses = payload.get("hypotheses") or []
        top_hypothesis = ""
        confidence = 0.0
        if isinstance(hypotheses, list) and hypotheses and isinstance(hypotheses[0], dict):
            top_hypothesis = str(hypotheses[0].get("hypothesis") or hypotheses[0].get("description") or "")
            confidence = float(hypotheses[0].get("confidence") or 0.0)
        items.append(
            {
                "incident_id": str(payload.get("incident_id") or path.stem),
                "service": str(payload.get("affected_service") or payload.get("service_id") or "unknown"),
                "top_hypothesis": top_hypothesis or "No hypothesis recorded",
                "confidence": round(confidence, 2),
                "loop_state": report_state,
                "ts_fired": str(payload.get("ts_fired") or payload.get("generated_at") or isoformat(utc_now())),
                "report_path": relative_repo_path(path),
            }
        )
    return {"open_count": len(items), "items": items}


def build_known_gaps() -> list[dict[str, str]]:
    gaps = []
    for path in sorted(ADR_DIR.glob("*.md")):
        metadata = parse_metadata_block(path)
        status = metadata.get("Status", "")
        implementation_status = metadata.get("Implementation Status", "")
        if status == "Proposed" and implementation_status == "Not Implemented":
            adr_id = path.name.split("-", 1)[0]
            gaps.append(
                {
                    "adr": adr_id,
                    "title": read_h1(path).replace(f"ADR {adr_id}: ", ""),
                    "status": status,
                    "implementation_status": implementation_status,
                    "path": relative_repo_path(path),
                }
            )
    return gaps


def build_identity(static_config: dict[str, Any], stack: dict[str, Any]) -> dict[str, str]:
    desired = stack.get("desired_state", {})
    return {
        "platform_name": static_config["identity"]["platform_name"],
        "operator": static_config["identity"]["operator"],
        "description": static_config["identity"]["description"],
        "host_id": str(desired.get("host_id") or "proxmox_florin"),
        "provider": str(desired.get("provider") or "hetzner-dedicated"),
    }


def normalize_for_compare(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: normalize_for_compare(value)
            for key, value in payload.items()
            if key not in {"generated_at", "next_refresh_at"}
        }
    if isinstance(payload, list):
        return [normalize_for_compare(item) for item in payload]
    return payload


def validate_manifest(payload: dict[str, Any]) -> None:
    jsonschema.validate(instance=payload, schema=load_json(SCHEMA_PATH))


def build_manifest(
    *,
    generated_at: dt.datetime | None = None,
    prometheus_url: str | None = None,
    incident_dir: Path = DEFAULT_INCIDENT_DIR,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    static_config = load_static_config()
    stack = load_stack()
    service_catalog = load_service_catalog()
    maintenance = build_maintenance_section()
    workflows, runbooks = build_workflow_capabilities()
    manifest = {
        "$schema": "docs/schema/platform-manifest.schema.json",
        "manifest_version": MANIFEST_VERSION,
        "repo_version": VERSION_PATH.read_text().strip(),
        "platform_version": str(stack["platform_version"]),
        "generated_at": isoformat(generated_at),
        "next_refresh_at": isoformat(generated_at + dt.timedelta(minutes=int(static_config["refresh_interval_minutes"]))),
        "environment": static_config["environment"],
        "identity": build_identity(static_config, stack),
        "health": build_health_section(
            service_catalog,
            prometheus_url=prometheus_url,
            active_maintenance_ids=active_maintenance_ids(maintenance),
        ),
        "incidents": build_incidents_section(incident_dir),
        "maintenance": maintenance,
        "capabilities": {
            "available_workflows": workflows,
            "automation_eligible_runbooks": runbooks,
        },
        "agents": {
            "registered": build_registered_agents(static_config, stack),
        },
        "recent_changes": build_recent_changes(VERSION_PATH.read_text().strip()),
        "agentic_architecture": static_config["agentic_architecture"],
        "data_sources": static_config["data_sources"],
        "known_gaps": build_known_gaps(),
    }
    validate_manifest(manifest)
    return manifest


def write_manifest(
    output_path: Path,
    *,
    generated_at: dt.datetime | None,
    prometheus_url: str | None,
    incident_dir: Path,
) -> dict[str, Any]:
    manifest = build_manifest(generated_at=generated_at, prometheus_url=prometheus_url, incident_dir=incident_dir)
    write_json(output_path, manifest, indent=2)
    return manifest


def check_manifest(
    output_path: Path,
    *,
    generated_at: dt.datetime | None,
    prometheus_url: str | None,
    incident_dir: Path,
) -> None:
    if not output_path.exists():
        raise ValueError(f"missing generated manifest artifact: {output_path}")
    current = load_json(output_path)
    validate_manifest(current)
    expected = build_manifest(generated_at=generated_at, prometheus_url=prometheus_url, incident_dir=incident_dir)
    if normalize_for_compare(current) != normalize_for_compare(expected):
        raise ValueError(f"{output_path} is out of date; rerun scripts/platform_manifest.py --write")


def print_human_summary(payload: dict[str, Any]) -> None:
    services = payload["health"]["services"]
    unsafe = [service_id for service_id, item in services.items() if not item["safe_to_act"]]
    print(
        f"Platform: {payload['identity']['platform_name']} "
        f"(repo {payload['repo_version']}, platform {payload['platform_version']})"
    )
    print(
        f"Health: {payload['health']['summary']} [{payload['health']['mode']}] | "
        f"Incidents: {payload['incidents']['open_count']} | "
        f"Maintenance: {len(payload['maintenance']['active_windows'])} active"
    )
    if unsafe:
        print("Unsafe services:")
        for service_id in unsafe:
            item = services[service_id]
            print(f"  - {service_id}: {item['status']} ({item['score']:.2f}) - {item['reason']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or validate the self-describing platform manifest.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Manifest output path.")
    parser.add_argument("--write", action="store_true", help="Write the canonical manifest artifact.")
    parser.add_argument("--check", action="store_true", help="Validate schema and ensure the artifact is up to date.")
    parser.add_argument("--print", action="store_true", help="Print the manifest as JSON.")
    parser.add_argument("--summary", action="store_true", help="Print a short human summary.")
    parser.add_argument("--prometheus-url", help="Optional Prometheus base URL for live SLO lookups.")
    parser.add_argument("--incident-dir", default=str(DEFAULT_INCIDENT_DIR), help="Directory containing triage reports.")
    parser.add_argument("--generated-at", help="Override generated_at with an ISO-8601 timestamp for deterministic tests.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_path = Path(args.output).expanduser()
    generated_at = parse_datetime(args.generated_at) if args.generated_at else None
    incident_dir = Path(args.incident_dir).expanduser()

    try:
        if args.check:
            check_manifest(
                output_path,
                generated_at=generated_at,
                prometheus_url=args.prometheus_url,
                incident_dir=incident_dir,
            )
            return 0

        manifest = build_manifest(
            generated_at=generated_at,
            prometheus_url=args.prometheus_url,
            incident_dir=incident_dir,
        )
        if args.write:
            write_json(output_path, manifest, indent=2)
        if args.print or not args.write:
            print(json.dumps(manifest, indent=2))
        if args.summary:
            print_human_summary(manifest)
        return 0
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError, jsonschema.ValidationError) as exc:
        return emit_cli_error("platform manifest", exc)


if __name__ == "__main__":
    raise SystemExit(main())
