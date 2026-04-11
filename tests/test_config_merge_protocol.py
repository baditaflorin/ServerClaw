from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest
import yaml

from platform.config_merge import ConfigMergeRegistry, DuplicateKeyError


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_yaml(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@pytest.fixture()
def merge_repo(tmp_path: Path) -> dict[str, object]:
    write_json(
        tmp_path / "config" / "service-capability-catalog.json",
        {
            "schema_version": "1.0.0",
            "services": [
                {
                    "id": "grafana",
                    "name": "Grafana",
                    "description": "Monitoring UI",
                }
            ],
        },
    )
    write_json(
        tmp_path / "config" / "subdomain-catalog.json",
        {
            "schema_version": "1.0.0",
            "subdomains": [
                {
                    "fqdn": "grafana.example.com",
                    "service_id": "grafana",
                }
            ],
        },
    )
    write_json(
        tmp_path / "config" / "workflow-catalog.json",
        {
            "schema_version": "1.0.0",
            "workflows": {
                "validate": {
                    "description": "Validate the repo",
                }
            },
        },
    )
    write_yaml(
        tmp_path / "config" / "agent-policies.yaml",
        [
            {
                "agent_id": "agent/codex",
                "description": "Interactive coding session",
                "identity_class": "operator-agent",
                "trust_tier": "T3",
            }
        ],
    )
    write_yaml(
        tmp_path / "config" / "merge-eligible-files.yaml",
        {
            "schema_version": "1.0.0",
            "merge_eligible": [
                {
                    "file": "config/service-capability-catalog.json",
                    "format": "json",
                    "collection_path": ["services"],
                    "collection_type": "list",
                    "key_field": "id",
                    "conflict_resolution": "reject_duplicate_key",
                    "allowed_operations": ["append", "update", "delete"],
                },
                {
                    "file": "config/workflow-catalog.json",
                    "format": "json",
                    "collection_path": ["workflows"],
                    "collection_type": "mapping",
                    "key_field": "workflow_id",
                    "conflict_resolution": "reject_duplicate_key",
                    "allowed_operations": ["append", "update", "delete"],
                    "drop_key_field_on_write": True,
                },
                {
                    "file": "config/agent-policies.yaml",
                    "format": "yaml",
                    "collection_path": [],
                    "collection_type": "list",
                    "key_field": "agent_id",
                    "conflict_resolution": "last_write_wins",
                    "allowed_operations": ["append", "update", "delete"],
                },
            ],
        },
    )
    db_path = tmp_path / "config-merge.sqlite3"
    return {
        "repo_root": tmp_path,
        "catalog_path": tmp_path / "config" / "merge-eligible-files.yaml",
        "dsn": f"sqlite:///{db_path}",
    }


def build_registry(merge_repo: dict[str, object], *, publish_nats: bool = False, publisher=None) -> ConfigMergeRegistry:
    registry = ConfigMergeRegistry(
        repo_root=merge_repo["repo_root"],
        catalog_path=merge_repo["catalog_path"],
        dsn=str(merge_repo["dsn"]),
        publish_nats=publish_nats,
        nats_publisher=publisher,
    )
    registry.ensure_schema()
    return registry


def test_stage_append_overlays_pending_entry_and_merges_file(merge_repo: dict[str, object]) -> None:
    published: list[tuple[str, dict[str, object]]] = []
    registry = build_registry(
        merge_repo, publish_nats=True, publisher=lambda subject, payload: published.append((subject, payload))
    )
    change = registry.stage_append(
        file_path="config/service-capability-catalog.json",
        entry={"id": "netbox", "name": "NetBox", "description": "Source of truth"},
        actor="agent/codex",
        context_id=str(uuid.uuid4()),
    )

    on_disk = json.loads(
        (Path(merge_repo["repo_root"]) / "config" / "service-capability-catalog.json").read_text(encoding="utf-8")
    )
    assert [item["id"] for item in on_disk["services"]] == ["grafana"]

    overlaid = registry.read_file("config/service-capability-catalog.json", include_pending=True)
    assert [item["id"] for item in overlaid["services"]] == ["grafana", "netbox"]

    report = registry.merge_pending(actor="agent/config-merge-job")

    assert report["merged_files"] == ["config/service-capability-catalog.json"]
    merged = json.loads(
        (Path(merge_repo["repo_root"]) / "config" / "service-capability-catalog.json").read_text(encoding="utf-8")
    )
    assert [item["id"] for item in merged["services"]] == ["grafana", "netbox"]
    assert report["merged_change_ids"] == [change["change_id"]]

    for _ in range(20):
        if published:
            break
        time.sleep(0.01)
    assert published
    assert published[0][0] == "platform.config.merged"
    assert published[0][1]["payload"]["change_id"] == change["change_id"]


def test_duplicate_key_is_rejected_for_reject_duplicate_key_files(merge_repo: dict[str, object]) -> None:
    registry = build_registry(merge_repo)
    with pytest.raises(DuplicateKeyError):
        registry.stage_append(
            file_path="config/service-capability-catalog.json",
            entry={"id": "grafana", "name": "Grafana duplicate"},
            actor="agent/codex",
            context_id=str(uuid.uuid4()),
        )


def test_mapping_collections_use_explicit_key_and_drop_it_on_write(merge_repo: dict[str, object]) -> None:
    registry = build_registry(merge_repo)
    registry.stage_append(
        file_path="config/workflow-catalog.json",
        entry={
            "workflow_id": "merge-config-changes",
            "description": "Merge pending registry rows",
            "live_impact": "guest_live",
        },
        actor="agent/codex",
        context_id=str(uuid.uuid4()),
    )

    report = registry.merge_pending()

    payload = json.loads(
        (Path(merge_repo["repo_root"]) / "config" / "workflow-catalog.json").read_text(encoding="utf-8")
    )
    assert report["merged_files"] == ["config/workflow-catalog.json"]
    assert "merge-config-changes" in payload["workflows"]
    assert "workflow_id" not in payload["workflows"]["merge-config-changes"]


def test_root_level_yaml_registry_supports_last_write_wins_updates(merge_repo: dict[str, object]) -> None:
    registry = build_registry(merge_repo)
    registry.stage_append(
        file_path="config/agent-policies.yaml",
        entry={
            "agent_id": "agent/codex",
            "description": "Interactive coding session",
            "identity_class": "operator-agent",
            "trust_tier": "T4",
        },
        actor="agent/codex",
        context_id=str(uuid.uuid4()),
    )

    registry.merge_pending(file_path="config/agent-policies.yaml")

    payload = yaml.safe_load(
        (Path(merge_repo["repo_root"]) / "config" / "agent-policies.yaml").read_text(encoding="utf-8")
    )
    assert payload[0]["agent_id"] == "agent/codex"
    assert payload[0]["trust_tier"] == "T4"
