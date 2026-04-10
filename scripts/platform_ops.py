#!/usr/bin/env python3
"""CPU-only operational CLI for the platform. No AI, no tokens, no network.

Queries machine-readable contracts to answer operational questions that
would otherwise require an AI agent session.

ADR 0391: CPU-Only Operational Automation

Usage:
    python3 scripts/platform_ops.py converge-plan --since main
    python3 scripts/platform_ops.py converge-plan --changed-files inventory/group_vars/all/identity.yml
    python3 scripts/platform_ops.py completeness --failing
    python3 scripts/platform_ops.py changelog --since v0.178.77
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from controller_automation_toolkit import load_json, repo_path


# ============================================================================
# Data loading — all from local files, zero network
# ============================================================================

def _load_yaml_lines(path: Path) -> dict[str, Any]:
    """Minimal YAML-like loader for simple key: value files. Not a full parser."""
    result: dict[str, Any] = {}
    if not path.is_file():
        return result
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("-"):
            key, _, val = stripped.partition(":")
            result[key.strip()] = val.strip()
    return result


def load_dependency_graph() -> dict[str, Any]:
    path = repo_path("config", "dependency-graph.json")
    if path.is_file():
        return load_json(path)
    return {}


def load_service_catalog() -> dict[str, Any]:
    return load_json(repo_path("config", "service-capability-catalog.json"), {})


def load_workflow_catalog() -> dict[str, Any]:
    return load_json(repo_path("config", "workflow-catalog.json"), {})


def load_platform_services() -> dict[str, Any]:
    """Load platform_services.yml via the repo's YAML loader."""
    try:
        from controller_automation_toolkit import _load_yaml_without_pyyaml
        path = repo_path("inventory", "group_vars", "all", "platform_services.yml")
        if path.is_file():
            return _load_yaml_without_pyyaml(path) or {}
    except (ImportError, Exception):
        pass
    return {}


def _service_name_variants(service_id: str) -> list[str]:
    underscore = service_id
    hyphen = service_id.replace("_", "-")
    joined = service_id.replace("_", "")
    return sorted(set([underscore, hyphen, joined]))


# ============================================================================
# Subcommand: references
# ============================================================================

def cmd_references(args: argparse.Namespace) -> dict[str, Any]:
    """Find all files referencing a service. Grouped by category."""
    variants = _service_name_variants(args.service)
    pattern = "|".join(re.escape(v) for v in variants)

    # Historical files to separate
    historical_dirs = {"receipts", "docs/release-notes"}

    # Search specific directories to avoid huge receipts/ and build/ dirs
    search_dirs = [
        "collections", "inventory", "config", "scripts", "tests",
        "docs", "workstreams", "versions", "playbooks", "Makefile",
    ]
    existing = [d for d in search_dirs if (REPO_ROOT / d).exists()]

    cmd = ["grep", "-rl", "-E", pattern,
           "--exclude-dir=.git", "--exclude-dir=node_modules",
           "--exclude-dir=__pycache__", "--exclude-dir=.claude"] + existing
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30)

    files = sorted(set(
        line.lstrip("./") for line in result.stdout.strip().splitlines() if line
    ))

    grouped: dict[str, list[str]] = defaultdict(list)
    for f in files:
        if any(f.startswith(h) for h in historical_dirs):
            grouped["historical"].append(f)
        elif f.startswith("collections/") and "/roles/" in f:
            grouped["roles"].append(f)
        elif "playbook" in f or f.startswith("playbooks/"):
            grouped["playbooks"].append(f)
        elif f.startswith("inventory/"):
            grouped["inventory"].append(f)
        elif f.startswith("config/"):
            grouped["config"].append(f)
        elif f.startswith("tests/"):
            grouped["tests"].append(f)
        elif f.startswith("scripts/"):
            grouped["scripts"].append(f)
        elif f.startswith("docs/"):
            grouped["docs"].append(f)
        elif f.startswith("versions/"):
            grouped["versions"].append(f)
        elif f.startswith("workstreams/"):
            grouped["workstreams"].append(f)
        else:
            grouped["other"].append(f)

    active_count = sum(len(v) for k, v in grouped.items() if k != "historical")
    return {
        "service_id": args.service,
        "variants": variants,
        "active_references": active_count,
        "historical_references": len(grouped.get("historical", [])),
        "by_category": {k: v for k, v in sorted(grouped.items()) if k != "historical"},
        "historical": grouped.get("historical", []),
    }


# ============================================================================
# Subcommand: impact
# ============================================================================

def cmd_impact(args: argparse.Namespace) -> dict[str, Any]:
    """Analyze the impact of changing or removing a service."""
    service_id = args.service
    refs = cmd_references(args)

    # Dependency graph: who depends on this service?
    dep_graph = load_dependency_graph()
    dependents: list[str] = []
    dependencies: list[str] = []
    edges = dep_graph.get("edges", dep_graph.get("extra_edges", []))
    for edge in edges:
        if isinstance(edge, dict):
            if edge.get("to") == service_id:
                dependents.append(edge.get("from", "unknown"))
            if edge.get("from") == service_id:
                dependencies.append(edge.get("to", "unknown"))

    # Workflow catalog: what workflows reference this service?
    workflows = load_workflow_catalog()
    affected_workflows: list[str] = []
    variants = _service_name_variants(service_id)
    for wf_id, wf in workflows.items():
        if isinstance(wf, dict):
            wf_str = json.dumps(wf)
            if any(v in wf_str for v in variants):
                affected_workflows.append(wf_id)

    # Service catalog entry
    catalog = load_service_catalog()
    service_entry = None
    for svc in catalog.get("services", []):
        if isinstance(svc, dict) and svc.get("id") == service_id:
            service_entry = svc
            break

    return {
        "service_id": service_id,
        "service_entry": service_entry,
        "dependents": sorted(set(dependents)),
        "dependencies": sorted(set(dependencies)),
        "affected_workflows": sorted(affected_workflows),
        "active_file_references": refs["active_references"],
        "reference_breakdown": {k: len(v) for k, v in refs["by_category"].items()},
        "removal_command": f"python3 scripts/decommission_service.py --service {service_id}",
    }


# ============================================================================
# Subcommand: converge-plan
# ============================================================================

def _changed_files_from_git(since: str) -> list[str]:
    """Get list of changed files between ref and HEAD."""
    cmd = ["git", "diff", "--name-only", f"{since}...HEAD"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10)
    if result.returncode != 0:
        # Try without the triple-dot (for tags/commits)
        cmd = ["git", "diff", "--name-only", since, "HEAD"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10)
    return [f for f in result.stdout.strip().splitlines() if f]


def _files_to_services(changed_files: list[str]) -> dict[str, list[str]]:
    """Map changed files to affected service IDs."""
    service_files: dict[str, list[str]] = defaultdict(list)

    for f in changed_files:
        # Role files: roles/<service>_runtime/ → service
        match = re.match(r"collections/.*/roles/(\w+?)_(runtime|postgres)/", f)
        if match:
            service_files[match.group(1)].append(f)
            continue

        # Playbooks: playbooks/<service>.yml → service
        match = re.match(r"(?:collections/.*/)?playbooks/(?:services/)?([a-z0-9_-]+)\.yml$", f)
        if match:
            svc = match.group(1).replace("-", "_")
            service_files[svc].append(f)
            continue

        # Inventory/config: broad impact — mark as "platform-wide"
        if f.startswith("inventory/group_vars/all/"):
            service_files["__platform_wide__"].append(f)
            continue

        # Config changes: try to extract service from filename
        match = re.match(r"config/(?:alertmanager/rules|grafana/dashboards)/([a-z0-9_-]+)\.", f)
        if match:
            svc = match.group(1).replace("-", "_")
            service_files[svc].append(f)
            continue

        # Common role changes affect everything
        if "roles/common/" in f or "roles/common_handlers/" in f:
            service_files["__platform_wide__"].append(f)
            continue

        # Keycloak runtime changes
        if "roles/keycloak_runtime/" in f:
            service_files["keycloak"].append(f)
            continue

        # Docker runtime changes
        if "roles/docker_runtime/" in f:
            service_files["__docker_runtime__"].append(f)
            continue

    return dict(service_files)


def _service_to_playbook(service_id: str) -> str | None:
    """Find the convergence playbook for a service."""
    hyphen = service_id.replace("_", "-")
    candidates = [
        f"collections/ansible_collections/lv3/platform/playbooks/{hyphen}.yml",
        f"collections/ansible_collections/lv3/platform/playbooks/{service_id}.yml",
        f"playbooks/{hyphen}.yml",
        f"playbooks/{service_id}.yml",
    ]
    for c in candidates:
        if (REPO_ROOT / c).is_file():
            return c
    return None


def _dependency_order(services: list[str], dep_graph: dict[str, Any]) -> list[str]:
    """Sort services by dependency order (dependencies first)."""
    edges = dep_graph.get("edges", dep_graph.get("extra_edges", []))
    deps: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if isinstance(edge, dict):
            src = edge.get("from", "")
            dst = edge.get("to", "")
            if src in services and dst in services:
                deps[src].add(dst)

    # Simple topological sort
    ordered: list[str] = []
    visited: set[str] = set()

    def visit(s: str) -> None:
        if s in visited:
            return
        visited.add(s)
        for dep in deps.get(s, []):
            visit(dep)
        ordered.append(s)

    for s in sorted(services):
        visit(s)
    return ordered


def cmd_converge_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Determine which playbooks need running based on changed files."""
    if args.since:
        changed = _changed_files_from_git(args.since)
    elif args.changed_files:
        changed = args.changed_files
    else:
        return {"error": "Provide --since <ref> or --changed-files <file1> <file2> ..."}

    service_map = _files_to_services(changed)
    dep_graph = load_dependency_graph()

    # Expand platform-wide changes to all services
    platform_wide = "__platform_wide__" in service_map or "__docker_runtime__" in service_map
    specific_services = [s for s in service_map if not s.startswith("__")]

    plan: list[dict[str, Any]] = []
    if platform_wide:
        plan.append({
            "note": "Platform-wide changes detected. Full site convergence recommended.",
            "trigger_files": service_map.get("__platform_wide__", []) + service_map.get("__docker_runtime__", []),
            "command": "make converge-site env=production",
        })
    else:
        ordered = _dependency_order(specific_services, dep_graph)
        for svc in ordered:
            playbook = _service_to_playbook(svc)
            entry: dict[str, Any] = {
                "service": svc,
                "trigger_files": service_map.get(svc, []),
                "playbook": playbook,
            }
            if playbook:
                entry["command"] = (
                    f"ansible-playbook {playbook} "
                    f"-e proxmox_guest_ssh_connection_mode=proxmox_host_jump "
                    f"--private-key=.local/ssh/bootstrap.id_ed25519"
                )
            else:
                entry["note"] = "No dedicated playbook found. May need group or site playbook."
            plan.append(entry)

    return {
        "changed_files": len(changed),
        "affected_services": specific_services,
        "platform_wide": platform_wide,
        "convergence_order": plan,
    }


# ============================================================================
# Subcommand: completeness
# ============================================================================

def cmd_completeness(args: argparse.Namespace) -> dict[str, Any]:
    """Check service completeness against contracts."""
    completeness_path = repo_path("config", "service-completeness.json")
    completeness = load_json(completeness_path, {})
    services_data = completeness.get("services", {})

    # services_data is a dict keyed by service_id
    results: list[dict[str, Any]] = []
    for svc_id, svc in sorted(services_data.items()):
        if not isinstance(svc, dict):
            continue
        if args.service and svc_id != args.service:
            continue

        checks: dict[str, bool] = {}

        # Check role exists
        role_dir = REPO_ROOT / "collections/ansible_collections/lv3/platform/roles" / f"{svc_id}_runtime"
        checks["role_exists"] = role_dir.is_dir()

        # Check playbook exists
        checks["playbook_exists"] = _service_to_playbook(svc_id) is not None

        # Check dashboard if required
        if svc.get("dashboard_file"):
            checks["dashboard_exists"] = (REPO_ROOT / svc["dashboard_file"]).is_file()

        # Check alert rules if required
        if svc.get("alert_rule_file"):
            checks["alert_rules_exist"] = (REPO_ROOT / svc["alert_rule_file"]).is_file()

        # Check test exists
        tests_dir = REPO_ROOT / "tests"
        checks["test_exists"] = tests_dir.is_dir() and any(tests_dir.glob(f"test_{svc_id}*.py"))

        passing = all(checks.values())
        if args.failing and passing:
            continue

        results.append({
            "service_id": svc_id,
            "passing": passing,
            "checks": checks,
            "suppressed": list(svc.get("suppressed_checks", {}).keys()),
        })

    return {
        "total_checked": len(results),
        "passing": sum(1 for r in results if r["passing"]),
        "failing": sum(1 for r in results if not r["passing"]),
        "services": results,
    }


# ============================================================================
# Subcommand: changelog
# ============================================================================

def cmd_changelog(args: argparse.Namespace) -> dict[str, Any]:
    """Generate changelog entries from git log."""
    cmd = ["git", "log", "--oneline", "--no-merges", f"{args.since}..HEAD"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10)
    if result.returncode != 0:
        return {"error": f"git log failed: {result.stderr.strip()}"}

    commits = result.stdout.strip().splitlines()
    entries: list[dict[str, str]] = []
    for line in commits:
        parts = line.split(" ", 1)
        if len(parts) == 2:
            sha, msg = parts
            # Classify by conventional prefix
            category = "other"
            for prefix in ["[fix]", "[release]", "[live-apply]", "[receipt]", "[adr", "[public-release]"]:
                if msg.lower().startswith(prefix):
                    category = prefix.strip("[]").split("-")[0]
                    break
            entries.append({"sha": sha, "message": msg, "category": category})

    # Group by category
    grouped: dict[str, list[str]] = defaultdict(list)
    for e in entries:
        grouped[e["category"]].append(f"- {e['message']} ({e['sha']})")

    # Format as markdown
    md_lines: list[str] = []
    for cat in sorted(grouped):
        md_lines.append(f"### {cat.title()}")
        md_lines.extend(grouped[cat])
        md_lines.append("")

    return {
        "since": args.since,
        "total_commits": len(commits),
        "by_category": {k: len(v) for k, v in grouped.items()},
        "markdown": "\n".join(md_lines),
    }


# ============================================================================
# Main
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CPU-only operational CLI. No AI, no tokens, no network.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # references
    p = sub.add_parser("references", help="Find all files referencing a service.")
    p.add_argument("--service", required=True)

    # impact
    p = sub.add_parser("impact", help="Analyze impact of changing or removing a service.")
    p.add_argument("--service", required=True)

    # converge-plan
    p = sub.add_parser("converge-plan", help="Which playbooks need running after changes?")
    p.add_argument("--since", help="Git ref to diff against (e.g. main, v0.178.77)")
    p.add_argument("--changed-files", nargs="+", help="Explicit list of changed files")

    # completeness
    p = sub.add_parser("completeness", help="Check service completeness against contracts.")
    p.add_argument("--service", help="Check a specific service (default: all)")
    p.add_argument("--failing", action="store_true", help="Show only failing services")

    # changelog
    p = sub.add_parser("changelog", help="Generate changelog from git commits.")
    p.add_argument("--since", required=True, help="Git ref to start from")

    args = parser.parse_args(argv)

    handlers = {
        "references": cmd_references,
        "impact": cmd_impact,
        "converge-plan": cmd_converge_plan,
        "completeness": cmd_completeness,
        "changelog": cmd_changelog,
    }

    try:
        result = handlers[args.command](args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
