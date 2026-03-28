from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import capacity_report  # noqa: E402
import failure_domain_policy  # noqa: E402
import service_redundancy  # noqa: E402
import shared_policy_packs  # noqa: E402
import standby_capacity  # noqa: E402


def load_repo_policy_payload() -> dict:
    return json.loads(shared_policy_packs.SHARED_POLICY_PACKS_PATH.read_text(encoding="utf-8"))


def test_repo_policy_pack_loads_and_drives_consumers() -> None:
    policies = shared_policy_packs.load_shared_policy_packs()

    assert policies.allowed_redundancy_tiers == ("R0", "R1", "R2", "R3")
    assert policies.capacity_class_ids == ("ha_reserved", "recovery_reserved", "preview_burst")
    assert policies.max_supported_tier_for_failure_domain_count(1) == "R2"
    assert policies.max_supported_tier_for_failure_domain_count(2) == "R3"

    assert service_redundancy.TIER_ORDER == policies.tier_order
    assert service_redundancy.REHEARSAL_TIER_SEQUENCE == policies.rehearsal_tier_sequence
    assert standby_capacity.ALLOWED_REDUNDANCY_TIERS == set(policies.allowed_redundancy_tiers)
    assert capacity_report.CAPACITY_CLASSES == policies.capacity_class_ids
    assert capacity_report.REQUESTER_CLASS_ALIASES == policies.requester_class_aliases
    assert failure_domain_policy.ALLOWED_DOMAIN_KINDS == policies.failure_domain_kinds
    assert failure_domain_policy.ALLOWED_ENVIRONMENT_PLACEMENT_CLASSES == policies.environment_placement_classes


def test_duplicate_capacity_alias_is_rejected(tmp_path: Path) -> None:
    payload = deepcopy(load_repo_policy_payload())
    payload["packs"]["capacity_classes"]["classes"][1]["aliases"].append("preview")
    broken_path = tmp_path / "shared-policy-packs.json"
    broken_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="assigned to multiple requester classes"):
        shared_policy_packs.load_shared_policy_packs(broken_path)


def test_failure_domain_thresholds_must_start_at_one(tmp_path: Path) -> None:
    payload = deepcopy(load_repo_policy_payload())
    payload["packs"]["service_redundancy"]["max_supported_tier_by_failure_domain_count"] = [
        {
            "minimum_failure_domain_count": 2,
            "tier": "R2",
        }
    ]
    broken_path = tmp_path / "shared-policy-packs.json"
    broken_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must start at 1"):
        shared_policy_packs.load_shared_policy_packs(broken_path)


def test_requester_aliases_must_include_primary_class_and_requester_name(tmp_path: Path) -> None:
    payload = deepcopy(load_repo_policy_payload())
    payload["packs"]["capacity_classes"]["classes"][0]["aliases"] = ["standby", "failover"]
    broken_path = tmp_path / "shared-policy-packs.json"
    broken_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="aliases must include id 'ha_reserved'"):
        shared_policy_packs.load_shared_policy_packs(broken_path)
