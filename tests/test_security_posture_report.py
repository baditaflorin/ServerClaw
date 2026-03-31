from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import drift_lib  # noqa: E402
import security_posture_report as report  # noqa: E402


def test_build_report_detects_new_lynis_findings_and_hardening_delta() -> None:
    previous = json.loads((REPO_ROOT / "tests" / "fixtures" / "security_posture_previous.json").read_text())
    host_reports = [
        {
            "host": "docker-runtime-lv3",
            "hardening_index": 72,
            "finding_counts": {"warning": 2, "suggestion": 1, "suppressed": 0},
            "findings": [
                {
                    "id": "AUTH-9208",
                    "type": "warning",
                    "description": "Set a password hashing iteration count",
                    "suggestion": "",
                    "raw": "AUTH-9208|Set a password hashing iteration count",
                    "suppressed": False,
                },
                {
                    "id": "PKGS-7392",
                    "type": "warning",
                    "description": "Apply the latest Debian security updates",
                    "suggestion": "",
                    "raw": "PKGS-7392|Apply the latest Debian security updates",
                    "suppressed": False,
                },
            ],
            "suppressed_findings": [],
        }
    ]
    trivy_payloads = {
        "docker-runtime-lv3": [
            {
                "image": "ghcr.io/example/app:1.0.0",
                "artifact_name": "ghcr.io/example/app:1.0.0",
                "severity_counts": {"HIGH": 2, "CRITICAL": 1},
                "vulnerabilities": [
                    {
                        "cve_id": "CVE-2026-0001",
                        "severity": "CRITICAL",
                        "package": "openssl",
                        "installed": "3.0.0",
                        "fixed_in": "3.0.1",
                        "title": "critical issue",
                    }
                ],
            }
        ]
    }

    built = report.build_report(
        environment="production",
        host_reports=host_reports,
        trivy_payloads=trivy_payloads,
        previous_report=previous,
    )

    assert built["hosts"][0]["new_findings_since_last_scan"] == 1
    assert built["hosts"][0]["hardening_index_delta"] == -2
    assert built["summary"]["total_critical_cves"] == 1
    assert built["summary"]["total_high_cves"] == 2
    assert built["summary"]["status"] == "critical"


def test_default_lynis_hosts_reads_active_service_vms(monkeypatch) -> None:
    monkeypatch.setattr(
        report,
        "load_json",
        lambda path: {
            "services": [
                {"vm": "docker-runtime-lv3", "environments": {"production": {"status": "active"}}},
                {"vm": "coolify-lv3", "environments": {"production": {"status": "active"}}},
                {"vm": "old-host", "environments": {"production": {"status": "retired"}}},
                {"vm": "proxmox_florin"},
            ]
        },
    )

    assert report.default_lynis_hosts("production") == [
        "coolify-lv3",
        "docker-runtime-lv3",
        "proxmox_florin",
    ]


def test_build_security_events_emits_summary_and_critical_findings() -> None:
    events = report.build_security_events(
        {
            "environment": "production",
            "generated_at": "2026-03-23T21:00:00Z",
            "summary": {
                "status": "critical",
                "status_code": 2,
                "total_critical_cves": 1,
                "total_high_cves": 2,
                "lowest_hardening_index": 72,
                "new_lynis_findings": 1,
            },
            "hosts": [
                {
                    "host": "docker-runtime-lv3",
                    "hardening_index": 72,
                    "hardening_index_delta": -11,
                }
            ],
            "images": [
                {
                    "host": "docker-runtime-lv3",
                    "image": "ghcr.io/example/app:1.0.0",
                    "cves": [
                        {
                            "cve_id": "CVE-2026-0001",
                            "severity": "CRITICAL",
                        }
                    ],
                }
            ],
        }
    )

    assert events[0]["event"] == "platform.security.report"
    critical_events = [item for item in events if item["event"] == "platform.security.critical-finding"]
    assert len(critical_events) == 2


def test_resolve_repo_local_path_maps_missing_controller_local_secret(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    mirrored_secret = repo_root / ".local" / "ssh" / "worker.id_ed25519"
    mirrored_secret.parent.mkdir(parents=True)
    mirrored_secret.write_text("secret", encoding="utf-8")

    resolved = drift_lib.resolve_repo_local_path(
        "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/worker.id_ed25519",
        repo_root=repo_root,
    )

    assert resolved == mirrored_secret


def test_resolve_repo_local_path_maps_inaccessible_controller_local_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    mirrored_secret = repo_root / ".local" / "ssh" / "worker.id_ed25519"
    mirrored_secret.parent.mkdir(parents=True)
    mirrored_secret.write_text("secret", encoding="utf-8")
    inaccessible = "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/worker.id_ed25519"
    original = drift_lib._path_exists

    def fake_path_exists(path: Path) -> bool:
        if str(path) == inaccessible:
            return False
        return original(path)

    monkeypatch.setattr(drift_lib, "_path_exists", fake_path_exists)

    resolved = drift_lib.resolve_repo_local_path(
        inaccessible,
        repo_root=repo_root,
    )

    assert resolved == mirrored_secret


def test_run_ansible_security_scan_uses_bootstrap_key_and_jump_mode(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        return drift_lib.CommandResult(argv=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(report, "run_command", fake_run_command)

    report.run_ansible_security_scan(
        inventory=tmp_path / "inventory.yml",
        playbook=tmp_path / "playbook.yml",
        output_dir=tmp_path / "output",
        hosts=["proxmox_florin", "docker-runtime-lv3"],
        bootstrap_key=tmp_path / "bootstrap.id_ed25519",
        jump_host_addr="10.10.10.1",
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert "--private-key" in command
    assert "proxmox_guest_ssh_connection_mode=proxmox_host_jump" in command
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["LV3_BOOTSTRAP_SSH_PRIVATE_KEY"] == str(tmp_path / "bootstrap.id_ed25519")
    assert env["LV3_PROXMOX_HOST_ADDR"] == "10.10.10.1"


def test_build_guest_ssh_command_makes_proxy_non_interactive(tmp_path: Path) -> None:
    command = drift_lib.build_guest_ssh_command(
        {
            "bootstrap_key": tmp_path / "worker.id_ed25519",
            "host_user": "ops",
            "host_addr": "100.64.0.1",
            "guests": {"docker-runtime-lv3": "10.10.10.20"},
        },
        "docker-runtime-lv3",
        "true",
    )

    joined = " ".join(command)
    assert "ProxyCommand=ssh" in joined
    assert "StrictHostKeyChecking=no" in joined
    assert "UserKnownHostsFile=/dev/null" in joined


def test_inventory_guest_proxy_command_is_non_interactive() -> None:
    group_vars = (REPO_ROOT / "inventory" / "group_vars" / "all.yml").read_text(encoding="utf-8")

    assert "proxmox_guest_ssh_proxy_command" in group_vars
    assert "-o BatchMode=yes" in group_vars
    assert "-o LogLevel=ERROR" in group_vars
    assert "-o StrictHostKeyChecking=no" in group_vars
    assert "-o UserKnownHostsFile=/dev/null" in group_vars


def test_inventory_proxmox_host_is_env_overridable() -> None:
    inventory = (REPO_ROOT / "inventory" / "hosts.yml").read_text(encoding="utf-8")

    assert "lookup('env', 'LV3_PROXMOX_HOST_ADDR')" in inventory


def test_skip_lynis_reuses_cached_reports(monkeypatch, tmp_path: Path) -> None:
    cached_dir = tmp_path / "lynis"
    cached_dir.mkdir()
    fixture = REPO_ROOT / "tests" / "fixtures" / "security_posture_docker_runtime.dat"
    (cached_dir / "docker-runtime-lv3-lynis-report.dat").write_text(fixture.read_text(), encoding="utf-8")

    monkeypatch.setattr(report, "load_controller_context", lambda: {"bootstrap_key": None, "host_addr": "100.64.0.1"})
    monkeypatch.setattr(report, "load_previous_report", lambda _path: None)
    monkeypatch.setattr(report, "run_remote_script", lambda **_kwargs: {})
    monkeypatch.setattr(report, "write_receipt", lambda _dir, _report: tmp_path / "receipt.json")
    monkeypatch.setattr(report, "build_security_events", lambda _report: [])
    monkeypatch.setattr(report, "maybe_publish_nats", lambda *args, **kwargs: None)
    monkeypatch.setattr(report, "maybe_write_metrics", lambda _report: None)
    monkeypatch.setattr(report, "emit_event_best_effort", lambda *args, **kwargs: None)
    monkeypatch.setattr(report, "maybe_read_secret_path", lambda *_args, **_kwargs: None)

    exit_code = report.main(
        [
            "--env",
            "production",
            "--skip-lynis",
            "--skip-trivy",
            "--lynis-dir",
            str(cached_dir),
        ]
    )

    assert exit_code in {0, 1, 2}
