from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import failure_domain_policy  # noqa: E402


def build_host_vars(*, secondary_domain_active: bool = False, standby_has_exception: bool = True) -> dict:
    standby_exceptions = (
        [{"scope": "failure_domain", "rationale": "single active domain for now"}] if standby_has_exception else []
    )
    return {
        "platform_failure_domains": [
            {
                "id": "host:proxmox_florin",
                "kind": "host",
                "status": "active",
                "live_label": "fd-host-proxmox-florin",
                "summary": "Primary host",
            },
            {
                "id": "cloud:hetzner-fsn1",
                "kind": "cloud",
                "status": "active" if secondary_domain_active else "planned",
                "live_label": "fd-cloud-hetzner-fsn1",
                "summary": "Auxiliary cloud",
            },
        ],
        "proxmox_guests": [
            {
                "vmid": 150,
                "name": "postgres-lv3",
                "tags": ["postgres", "database", "lv3"],
                "placement": {
                    "failure_domain": "host:proxmox_florin",
                    "placement_class": "primary",
                    "anti_affinity_group": "postgres-ha",
                    "co_location_exceptions": [],
                },
            },
            {
                "vmid": 151,
                "name": "postgres-replica-lv3",
                "tags": ["postgres", "database", "ha", "lv3"],
                "placement": {
                    "failure_domain": "host:proxmox_florin",
                    "placement_class": "standby",
                    "anti_affinity_group": "postgres-ha",
                    "co_location_exceptions": standby_exceptions,
                },
            },
            {
                "vmid": 160,
                "name": "backup-lv3",
                "tags": ["backup", "pbs", "lv3"],
                "placement": {
                    "failure_domain": "host:proxmox_florin",
                    "placement_class": "recovery",
                    "anti_affinity_group": "control-plane-recovery",
                    "co_location_exceptions": standby_exceptions,
                },
            },
        ],
    }


def build_environment_topology(*, include_standby_exclusion: bool = True) -> dict:
    exclusions = ["standby", "recovery"] if include_standby_exclusion else ["recovery"]
    return {
        "environments": [
            {
                "id": "production",
                "name": "Production",
                "status": "active",
                "purpose": "Primary environment",
                "base_domain": "lv3.org",
                "hostname_pattern": "<service>.lv3.org",
                "edge_service_id": "nginx_edge",
                "edge_vm": "postgres-lv3",
                "ingress_ipv4": "65.108.75.123",
                "topology_model": "single-node-shared-edge",
                "isolation_model": "Shared edge",
            },
            {
                "id": "staging",
                "name": "Staging",
                "status": "active",
                "purpose": "Preview lane",
                "base_domain": "staging.lv3.org",
                "hostname_pattern": "<service>.staging.lv3.org",
                "edge_service_id": "nginx_edge",
                "edge_vm": "postgres-lv3",
                "ingress_ipv4": "65.108.75.123",
                "topology_model": "single-node-shared-edge",
                "isolation_model": "Shared host",
                "placement": {
                    "failure_domain": "host:proxmox_florin",
                    "placement_class": "preview",
                    "anti_affinity_group": "staging-preview",
                    "co_location_exceptions": [
                        {
                            "scope": "failure_domain",
                            "rationale": "single active domain for now",
                        }
                    ],
                    "reserved_capacity_exclusions": exclusions,
                },
            },
        ]
    }


def build_service_catalog() -> dict:
    return {
        "services": [
            {
                "id": "postgres",
                "name": "PostgreSQL",
                "vm": "postgres-lv3",
                "redundancy": {
                    "tier": "R2",
                    "standby": {
                        "vm": "postgres-replica-lv3",
                    },
                },
            }
        ]
    }


def test_repo_policy_validates() -> None:
    report = failure_domain_policy.validate_failure_domain_policy()
    standby_pairs = {item["service_id"] for item in report["standby_pairs"]}
    assert "postgres" in standby_pairs
    postgres_guest = next(item for item in report["guests"] if item["name"] == "postgres-replica-lv3")
    assert "exc-same-domain" in postgres_guest["live_tags"]


def test_same_domain_standby_requires_explicit_exception() -> None:
    with pytest.raises(ValueError, match="same-domain co_location_exception"):
        failure_domain_policy.validate_failure_domain_policy(
            host_vars=build_host_vars(standby_has_exception=False),
            environment_topology=build_environment_topology(),
            service_catalog=build_service_catalog(),
        )


def test_same_domain_standby_is_rejected_when_multiple_domains_are_active() -> None:
    with pytest.raises(ValueError, match="despite multiple active domains"):
        failure_domain_policy.validate_failure_domain_policy(
            host_vars=build_host_vars(secondary_domain_active=True),
            environment_topology=build_environment_topology(),
            service_catalog=build_service_catalog(),
        )


def test_preview_environment_must_protect_standby_capacity() -> None:
    with pytest.raises(ValueError, match="must include 'standby'"):
        failure_domain_policy.validate_failure_domain_policy(
            host_vars=build_host_vars(),
            environment_topology=build_environment_topology(include_standby_exclusion=False),
            service_catalog=build_service_catalog(),
        )
