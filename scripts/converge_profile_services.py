#!/usr/bin/env python3
"""
converge_profile_services.py — run make converge-* for every service in the
active deployment profile.

Called by: make converge-all-services
Usage:     uv run --with pyyaml python scripts/converge_profile_services.py

Reads:
  .local/manifest.yml              -- active profiles + disabled_services
  inventory/group_vars/all/service_profiles.yml  -- profile → service list

For each enabled service, runs:
  make converge-<service_key_with_hyphen> env=<env>

Services that were already converged in earlier bootstrap steps (openbao,
keycloak, step_ca) are skipped by default to avoid redundant re-runs; pass
--include-bootstrap-steps to force them.

Services without a known make target are logged as INFO and skipped.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR: PyYAML not installed — run via: uv run --with pyyaml python ...", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / ".local" / "manifest.yml"
SERVICE_PROFILES_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "service_profiles.yml"

# Services handled in dedicated bootstrap steps (skip by default).
BOOTSTRAP_STEP_SERVICES = {"openbao", "keycloak", "step_ca"}

# Mapping from service_key → make target.  Entries not in this map are skipped.
# When multiple services map to the same target, the target runs only once.
SERVICE_MAKE_TARGETS: dict[str, str] = {
    "openbao":         "converge-openbao",
    "keycloak":        "converge-keycloak",
    "step_ca":         "converge-step-ca",
    "nginx_runtime":   "converge-nginx-edge",
    "docker_runtime":  "converge-docker-runtime",
    "alertmanager":    "converge-monitoring",
    "uptime_kuma":     "converge-monitoring",
    "ops_portal":      "converge-ops-portal",
    "homepage":        "converge-homepage",
    "dozzle":          "converge-dozzle",
    # Extend as new services gain dedicated make targets.
}


def load_yaml(path: Path) -> Any:
    with path.open() as fh:
        return yaml.safe_load(fh)


def resolve_profile_services(
    profiles: list[str],
    service_profiles: dict[str, Any],
    *,
    disabled: list[str] | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """Walk the profile inheritance graph and return a deduplicated ordered list."""
    disabled_set = set(disabled or [])
    services: list[str] = []
    seen: set[str] = set()

    def add_profile(name: str) -> None:
        entry = service_profiles.get(name, {})
        for parent in entry.get("extends", []):
            add_profile(parent)
        for svc in entry.get("services", []):
            if svc not in seen:
                seen.add(svc)
                services.append(svc)

    for p in profiles:
        add_profile(p)
    for svc in (extra or []):
        if svc not in seen:
            seen.add(svc)
            services.append(svc)

    return [s for s in services if s not in disabled_set]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="production", help="Deployment environment")
    parser.add_argument(
        "--include-bootstrap-steps",
        action="store_true",
        help="Also run openbao / keycloak / step_ca (normally handled by earlier steps)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print targets without running")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        print(f"ERROR: {MANIFEST_PATH} not found — run from repo root with .local/ configured", file=sys.stderr)
        return 1
    if not SERVICE_PROFILES_PATH.exists():
        print(f"ERROR: {SERVICE_PROFILES_PATH} not found", file=sys.stderr)
        return 1

    manifest = load_yaml(MANIFEST_PATH)
    profiles_raw = load_yaml(SERVICE_PROFILES_PATH)
    service_profiles: dict[str, Any] = profiles_raw.get("service_profiles", {})

    active_profiles: list[str] = manifest.get("profiles", ["core"])
    disabled: list[str] = manifest.get("disabled_services", [])
    extra: list[str] = manifest.get("extra_services", [])

    services = resolve_profile_services(active_profiles, service_profiles, disabled=disabled, extra=extra)

    if not args.include_bootstrap_steps:
        services = [s for s in services if s not in BOOTSTRAP_STEP_SERVICES]

    # Deduplicate make targets while preserving first-occurrence order.
    targets_seen: set[str] = set()
    plan: list[tuple[str, str]] = []
    for svc in services:
        target = SERVICE_MAKE_TARGETS.get(svc)
        if target is None:
            print(f"INFO  skip  {svc!s:30s}  (no make target registered)")
            continue
        if target in targets_seen:
            print(f"INFO  dedup {svc!s:30s}  → {target} (already queued)")
            continue
        targets_seen.add(target)
        plan.append((svc, target))
        print(f"INFO  queue {svc!s:30s}  → {target}")

    if not plan:
        print("INFO  nothing to do — all profile services already handled or unmapped")
        return 0

    failures = 0
    for svc, target in plan:
        cmd = ["make", target, f"env={args.env}"]
        print(f"\n{'='*60}")
        print(f"converge-all-services: {target} ({svc})")
        print(f"{'='*60}")
        if args.dry_run:
            print(f"[dry-run] would run: {' '.join(cmd)}")
            continue
        result = subprocess.run(cmd, cwd=str(REPO_ROOT))
        if result.returncode != 0:
            print(f"ERROR: {target} exited {result.returncode}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\nconverge-all-services: {failures} target(s) failed", file=sys.stderr)
        return 1

    print(f"\nconverge-all-services: all {len(plan)} target(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
