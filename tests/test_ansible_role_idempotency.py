from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

import ansible_role_idempotency


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_policy_file_covers_current_roles() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "ansible-role-idempotency.yml").read_text(encoding="utf-8"))

    enforced, tracked, exempt = ansible_role_idempotency.validate_config(
        config, path=REPO_ROOT / "config" / "ansible-role-idempotency.yml"
    )

    assert enforced == ["preflight", "secret_fact", "wait_for_healthy"]
    assert "_template" in exempt
    assert "docker_runtime" in tracked
    assert "redpanda_runtime" in tracked


def test_validate_config_rejects_role_tree_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "ansible-role-idempotency.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "roles": {
                    "alpha": {
                        "policy": "tracked",
                        "reason": "pending",
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    config = ansible_role_idempotency.load_config(config_path)
    monkeypatch.setattr(ansible_role_idempotency, "role_names", lambda: ["alpha", "beta"])

    with pytest.raises(ValueError, match="missing roles: beta"):
        ansible_role_idempotency.validate_config(config, path=config_path)


def test_http_fixture_server_serves_declared_json() -> None:
    fixture = {
        "responses": {
            "/health": {
                "status": 200,
                "json": {"status": "ok"},
            }
        }
    }

    with ansible_role_idempotency.http_fixture_server(fixture) as base_url:
        completed = subprocess.run(
            [
                "python3",
                "-c",
                "import json, urllib.request, sys; print(json.dumps(json.load(urllib.request.urlopen(sys.argv[1]))))",
                f"{base_url}/health",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"status": "ok"}


def test_run_enforced_role_detects_second_run_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    playbook = REPO_ROOT / "tests" / "idempotency" / "preflight.yml"
    inventory = REPO_ROOT / "tests" / "idempotency" / "localhost.ini"
    calls: list[tuple[Path, Path]] = []

    def fake_run(playbook_path: Path, *, inventory: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        del env
        calls.append((playbook_path, inventory))
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                ["ansible-playbook"],
                0,
                stdout=json.dumps({"plays": []}),
                stderr="",
            )
        return subprocess.CompletedProcess(
            ["ansible-playbook"],
            0,
            stdout=json.dumps(
                {
                    "plays": [
                        {
                            "tasks": [
                                {
                                    "task": {
                                        "name": "lv3.platform.preflight : Assert required preflight variables are present"
                                    },
                                    "hosts": {"localhost": {"changed": True}},
                                }
                            ]
                        }
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(ansible_role_idempotency, "run_ansible_playbook", fake_run)
    monkeypatch.setattr(ansible_role_idempotency, "DEFAULT_INVENTORY_PATH", inventory)

    result = ansible_role_idempotency.run_enforced_role(
        "preflight",
        {
            "policy": "enforced",
            "reason": "test",
            "scenario": {
                "playbook": str(playbook.relative_to(REPO_ROOT)),
            },
        },
    )

    assert result.status == "failed"
    assert "changed on second run" in result.detail
    assert calls == [(playbook, inventory), (playbook, inventory)]
