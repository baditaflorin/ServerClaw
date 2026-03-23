from __future__ import annotations

import json
from pathlib import Path

import pytest

import lv3_cli


@pytest.fixture()
def minimal_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "inventory").mkdir()
    (tmp_path / "receipts" / "live-applies").mkdir(parents=True)
    (tmp_path / "receipts" / "dr-table-top-reviews").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "versions").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "Makefile").write_text(
        "\n".join(
            [
                "drift-report:",
                "remote-lint:",
                "remote-validate:",
                "remote-pre-push:",
                "remote-exec:",
                "rotate-secret:",
                "promote:",
                "fixture-up:",
                "fixture-down:",
                "fixture-list:",
                "",
            ]
        )
    )
    (tmp_path / "inventory" / "hosts.yml").write_text(
        """
all:
  children:
    lv3_guests:
      hosts:
        monitoring-lv3:
          ansible_host: 10.10.10.40
        docker-runtime-lv3:
          ansible_host: 10.10.10.20
        nginx-lv3:
          ansible_host: 10.10.10.10
""".strip()
        + "\n"
    )
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "grafana",
                        "name": "Grafana",
                        "vm": "monitoring-lv3",
                        "lifecycle_status": "active",
                        "internal_url": "http://127.0.0.1:18080/health",
                        "health_probe_id": "grafana",
                        "environments": {"production": {"status": "active", "url": "http://127.0.0.1:18080/health"}},
                    },
                    {
                        "id": "windmill",
                        "name": "Windmill",
                        "vm": "docker-runtime-lv3",
                        "lifecycle_status": "active",
                        "internal_url": "http://127.0.0.1:18081",
                        "health_probe_id": "windmill",
                        "environments": {"production": {"status": "active", "url": "http://127.0.0.1:18081"}},
                    },
                    {
                        "id": "ops_portal",
                        "name": "Ops Portal",
                        "vm": "nginx-lv3",
                        "lifecycle_status": "planned",
                        "public_url": "https://ops.lv3.org",
                        "environments": {"production": {"status": "planned", "url": "https://ops.lv3.org"}},
                    },
                ]
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "health-probe-catalog.json").write_text(
        json.dumps(
            {
                "services": {
                    "grafana": {"readiness": {"validate_tls": True}},
                    "windmill": {"readiness": {"validate_tls": True}},
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "controller-local-secrets.json").write_text(
        json.dumps(
            {
                "secrets": {
                    "windmill_superadmin_secret": {"path": str(tmp_path / "windmill-token.txt")},
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "windmill_healthcheck": {"description": "Healthcheck"},
                    "disaster-recovery-runbook": {"description": "DR runbook"},
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "disaster-recovery-targets.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "platform_target": {"rto_minutes": 240, "rpo_hours": 24},
                "review_policy": {"table_top_interval_days": 90, "live_drill_interval_days": 365},
                "offsite_backup": {"strategy": "vm160", "storage_id": "lv3-backup-offsite"},
                "scenarios": [
                    {"id": "host", "name": "Host loss", "rto_minutes": 240, "rpo_hours": 24, "notes": "restore vm160"}
                ],
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "versions" / "stack.yaml").write_text(
        """
repo_version: 0.96.0
platform_version: 0.40.0
backups:
  control_plane_recovery:
    latest_restore_drill:
      checked_at: 2026-03-23T08:00:00Z
      result: pass
""".strip()
        + "\n"
    )
    (tmp_path / "docs" / "adr" / "0093-interactive-ops-portal.md").write_text(
        "- Status: Proposed\n- Implementation Status: Not Implemented\n"
    )
    (tmp_path / "docs" / "adr" / "0094-developer-portal-and-documentation-site.md").write_text(
        "- Status: Proposed\n- Implementation Status: Not Implemented\n"
    )
    (tmp_path / "docs" / "adr" / "0109-public-status-page.md").write_text(
        "- Status: Proposed\n- Implementation Status: Not Implemented\n"
    )
    (tmp_path / "receipts" / "dr-table-top-reviews" / "2026-03-23-review.json").write_text(
        json.dumps({"reviewed_on": "2026-03-23", "result": "completed_with_gaps"}) + "\n"
    )
    (tmp_path / "windmill-token.txt").write_text("secret-token\n")
    (tmp_path / "tests" / "fixtures" / "docker-host-fixture.yml").write_text("{}\n")
    (tmp_path / "receipts" / "live-applies" / "2026-03-23-grafana.json").write_text(
        json.dumps({"summary": "grafana deploy", "workflow_id": "converge-grafana"}) + "\n"
    )
    monkeypatch.setattr(lv3_cli, "REPO_ROOT", tmp_path)
    return tmp_path


def test_help_lists_command_groups(capsys: pytest.CaptureFixture[str], minimal_repo: Path) -> None:
    exit_code = lv3_cli.main(["--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "deploy" in captured.out
    assert "status" in captured.out
    assert "open" in captured.out


def test_deploy_dry_run_prints_remote_exec_route(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["deploy", "grafana", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "build server" in captured.out
    assert "make remote-exec" in captured.out
    assert "live-apply-service service=grafana env=production" in captured.out


def test_open_dry_run_uses_catalog_url(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["open", "ops_portal", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "https://ops.lv3.org" in captured.out


def test_logs_dry_run_builds_loki_query(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LV3_LOKI_URL", "http://loki.example/query_range")
    exit_code = lv3_cli.main(["logs", "windmill", "--since", "2h", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "http://loki.example/query_range" in captured.out
    assert "query=%7Bservice%3D%22windmill%22%7D" in captured.out


def test_run_dry_run_redacts_token(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["run", "windmill_healthcheck", "--args", "probe=manual", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "<redacted>" in captured.out
    assert "secret-token" not in captured.out


def test_vm_list_uses_inventory(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["vm", "list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "monitoring-lv3" in captured.out
    assert "10.10.10.40" in captured.out


def test_completion_suggests_services(minimal_repo: Path) -> None:
    candidates = lv3_cli.completion_candidates(["lv3", "open"], "g")
    assert candidates == ["grafana"]


def test_diff_dry_run_uses_drift_report_target(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["diff", "--env", "production", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "make drift-report ENV=production" in captured.out


def test_fixture_list_dry_run_prints_make_target(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["fixture", "list", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "make fixture-list" in captured.out


def test_fixture_completion_suggests_fixture_names(minimal_repo: Path) -> None:
    candidates = lv3_cli.completion_candidates(["lv3", "fixture", "create", "d"], "d")
    assert candidates == ["docker-host"]


def test_fixture_create_dry_run_passes_lifecycle_parameters(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(
        [
            "fixture",
            "create",
            "docker-host",
            "--purpose",
            "adr-0106-test",
            "--owner",
            "codex",
            "--lifetime-hours",
            "1",
            "--policy",
            "integration-test",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "make fixture-up" in captured.out
    assert "PURPOSE=adr-0106-test" in captured.out
    assert "OWNER=codex" in captured.out
    assert "LIFETIME_HOURS=1.0" in captured.out
    assert "EPHEMERAL_POLICY=integration-test" in captured.out


def test_fixture_destroy_dry_run_accepts_vmid(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["fixture", "destroy", "--vmid", "910", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "make fixture-down" in captured.out
    assert "VMID=910" in captured.out


def test_release_status_uses_dr_report(capsys: pytest.CaptureFixture[str], minimal_repo: Path) -> None:
    exit_code = lv3_cli.main(["release", "status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Platform 1.0.0 readiness" in captured.out
    assert "DR table-top review: complete" in captured.out
