from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import seed_data_snapshots as seeds  # noqa: E402


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def configure_paths(monkeypatch, repo_root: Path) -> None:
    monkeypatch.setattr(seeds, "SEED_CATALOG_PATH", repo_root / "config" / "seed-data-catalog.json")
    monkeypatch.setattr(seeds, "CONTROLLER_SECRETS_PATH", repo_root / "config" / "controller-local-secrets.json")
    monkeypatch.setattr(seeds, "SERVICE_CATALOG_PATH", repo_root / "config" / "service-capability-catalog.json")
    monkeypatch.setattr(seeds, "WORKFLOW_CATALOG_PATH", repo_root / "config" / "workflow-catalog.json")


def make_repo(tmp_path: Path, monkeypatch) -> Path:
    write(
        tmp_path / "config" / "seed-data-catalog.json",
        json.dumps(
            {
                "schema_version": "1.0.0",
                "controller_secret_id": "seed_data_anonymization_salt",
                "local_snapshot_root": ".local/seed-data/snapshots",
                "guest_stage_root": "/var/lib/lv3-seed-data",
                "remote_store": {
                    "host": "backup-lv3",
                    "base_path": "/var/lib/lv3/seed-data-snapshots",
                    "directory_mode": "0750",
                },
                "managed_postgres_databases": ["keycloak", "windmill"],
                "classes": {
                    "tiny": {
                        "description": "smoke",
                        "datasets": {
                            "identities": 4,
                            "sessions": 6,
                            "workflow_runs": 5,
                            "messages": 8,
                            "assets": 4,
                            "audit_events": 10,
                        },
                    }
                },
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "controller-local-secrets.json",
        json.dumps(
            {
                "secrets": {
                    "seed_data_anonymization_salt": {
                        "kind": "file",
                        "path": str(tmp_path / ".local" / "seed-data" / "anonymization-salt.txt"),
                    }
                }
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps(
            {"services": [{"id": "netbox", "public_url": "https://netbox.example"}, {"id": "windmill"}]}, indent=2
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps({"workflows": {"validate": {}, "restore-verification": {}}}, indent=2) + "\n",
    )
    configure_paths(monkeypatch, tmp_path)
    real_run_command = __import__("subprocess")  # placeholder to keep scope explicit

    def fake_run(command):
        joined = " ".join(command)
        if "count(*)" in joined:
            completed = real_run_command.run(
                ["/bin/sh", "-lc", "printf '12'"], text=True, capture_output=True, check=False
            )
        else:
            completed = real_run_command.run(
                ["/bin/sh", "-lc", "printf '240'"], text=True, capture_output=True, check=False
            )
        return type(
            "Result",
            (),
            {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr},
        )()

    monkeypatch.setattr(
        seeds,
        "_load_drift_helpers",
        lambda: (
            lambda context, target, command: ["ssh", target, command],
            lambda: {
                "bootstrap_key": Path("/tmp/bootstrap"),
                "host_user": "ops",
                "host_addr": "100.64.0.1",
                "guests": {},
            },
            fake_run,
        ),
    )
    return tmp_path


def test_build_snapshot_writes_manifest_and_datasets(tmp_path: Path, monkeypatch) -> None:
    repo_root = make_repo(tmp_path, monkeypatch)
    catalog = seeds.load_catalog(repo_root / "config" / "seed-data-catalog.json")

    snapshot_path = seeds.build_snapshot("tiny", catalog=catalog)
    manifest = json.loads((snapshot_path / "manifest.json").read_text())

    assert manifest["seed_class"] == "tiny"
    assert manifest["dataset_counts"]["identities"] == 4
    assert (snapshot_path / "identities.ndjson").exists()
    assert (snapshot_path / "audit_events.ndjson").exists()
    assert seeds.verify_local_snapshot(snapshot_path)["snapshot_id"] == manifest["snapshot_id"]


def test_stage_snapshot_to_remote_dir_uses_requested_path(tmp_path: Path, monkeypatch) -> None:
    repo_root = make_repo(tmp_path, monkeypatch)
    catalog = seeds.load_catalog(repo_root / "config" / "seed-data-catalog.json")
    snapshot_path = seeds.build_snapshot("tiny", catalog=catalog)
    staged = {}

    def fake_stage(snapshot_arg, ssh_base, remote_dir, *, sudo=True):
        staged["snapshot"] = snapshot_arg
        staged["remote_dir"] = remote_dir
        return {
            "remote_dir": remote_dir,
            "snapshot_id": seeds.load_manifest(snapshot_arg)["snapshot_id"],
            "seed_class": "tiny",
        }

    monkeypatch.setattr(seeds, "stage_snapshot_with_ssh", fake_stage)

    result = seeds.stage_snapshot_to_remote_dir(
        "tiny",
        ["ssh", "fixture"],
        remote_dir="/var/lib/lv3-seed-data/tiny/test",
        catalog=catalog,
    )

    assert staged["snapshot"] == snapshot_path
    assert staged["remote_dir"] == "/var/lib/lv3-seed-data/tiny/test"
    assert result["seed_class"] == "tiny"
