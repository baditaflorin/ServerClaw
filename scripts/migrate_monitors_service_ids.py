#!/usr/bin/env python3
"""One-time migration: add service_id field to each monitor in config/uptime-kuma/monitors.json.

After this script runs, decommission_service.py._remove_from_json_array_flat() can remove
uptime-kuma monitors atomically when a service is decommissioned.

Usage:
    python3 scripts/migrate_monitors_service_ids.py [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "config" / "uptime-kuma" / "monitors.json"

# Map monitor name → service_id.
# Infrastructure items (Proxmox, PostgreSQL VIP, NGINX Edge, etc.) are mapped
# to None so they are left without a service_id (the decommission script skips them).
MONITOR_SERVICE_MAP: dict[str, str | None] = {
    "Platform API Gateway Public":      "api_gateway",
    "Backup PBS Port":                  None,          # infrastructure — no catalog service
    "Browser Runner Private":           None,          # ambiguous — port 8096 matches repo_intake but name diverges
    "Dify Public":                      "dify",
    "Directus Public Health":           "directus",
    "Docker Build SSH":                 None,          # infrastructure
    "Dozzle Private":                   "dozzle",
    "Excalidraw Public":                "excalidraw",
    "Flagsmith Public Health":          "flagsmith",
    "Gitea Private":                    "gitea",
    "Grafana Public":                   "grafana",
    "Harbor Registry Public":           "harbor",
    "Headscale Public Health":          "headscale",
    "Homepage Public":                  "homepage",
    "Keycloak OIDC Discovery":          "keycloak",
    "Lago Public Health":               "lago",
    "Langfuse Public Health":           "langfuse",
    "Mail Platform Gateway Private":    None,          # infrastructure
    "MinIO Public Health":              "minio",
    "Matrix Synapse Public":            "matrix_synapse",
    "Mattermost Private":               "mattermost",
    "n8n Public Health":                "n8n",
    "Nextcloud Public Status":          "nextcloud",
    "NetBox Private":                   "netbox",
    "NGINX Edge Public":                None,          # infrastructure
    "ntfy Public":                      "ntfy",
    "Ops Portal Public":                "ops_portal",
    "Grist Public Status":              "grist",
    "Outline Public Health":            "outline",
    "Paperless Public Health":          "paperless",
    "Plane Public":                     "plane",
    "Platform Context Private":         None,          # internal platform service
    "Plausible Public Health":          "plausible",
    "Portainer Private":                "portainer",
    "PostgreSQL VIP Port":              None,          # infrastructure
    "Proxmox UI Port":                  None,          # infrastructure
    "Realtime Metrics Private":         "netdata",     # already removed — decommission handles cleanup
    "Semaphore Private":                "semaphore",
    "ServerClaw":                       "serverclaw",
    "Step CA Private":                  "step_ca",
    "Superset Public Health":           "superset",
    "Tika Private":                     "tika",
    "Uptime Kuma Public":               "uptime_kuma",
    "Windmill Private":                 "windmill",
    "Woodpecker Public":                "woodpecker",
    "GlitchTip Public Health":          "glitchtip",
    "Repowise Private":                 "repowise",
}


def add_service_ids(monitors: list[dict]) -> tuple[list[dict], int, list[str]]:
    """Insert service_id after the name field. Returns (updated_list, count_added, unmapped)."""
    updated: list[dict] = []
    count = 0
    unmapped: list[str] = []

    for monitor in monitors:
        name = monitor.get("name", "")
        if name not in MONITOR_SERVICE_MAP:
            unmapped.append(name)
            updated.append(monitor)
            continue

        service_id = MONITOR_SERVICE_MAP[name]
        if service_id is None or "service_id" in monitor:
            updated.append(monitor)
            continue

        # Insert service_id right after "name"
        new_entry: dict = {}
        for k, v in monitor.items():
            new_entry[k] = v
            if k == "name":
                new_entry["service_id"] = service_id
        updated.append(new_entry)
        count += 1

    return updated, count, unmapped


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    if not TARGET.is_file():
        print(f"ERROR: {TARGET} not found", file=sys.stderr)
        return 1

    data = json.loads(TARGET.read_text())
    if not isinstance(data, list):
        print("ERROR: monitors.json root is not a list", file=sys.stderr)
        return 1

    # Skip if already migrated
    if any(isinstance(m, dict) and "service_id" in m for m in data):
        print("INFO: monitors.json already contains service_id fields — skipping")
        return 0

    updated, count, unmapped = add_service_ids(data)

    if unmapped:
        print(f"WARN: {len(unmapped)} monitors not in MONITOR_SERVICE_MAP:")
        for name in unmapped:
            print(f"  - {name!r}")

    print(f"Migration: {count} monitors will receive a service_id field")

    if dry_run:
        print("DRY-RUN: no file written")
        print("--- sample (first 5 entries) ---")
        for entry in updated[:5]:
            print(json.dumps(entry, indent=2))
        return 0

    TARGET.write_text(json.dumps(updated, indent=2) + "\n")
    print(f"Wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
