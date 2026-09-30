from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import drift_lib
import security_posture_report as report


def test_build_report_detects_new_lynis_findings_and_hardening_delta() -> None:
    previous = json.loads((REPO_ROOT / "tests" / "fixtures" / "security_posture_previous.json").read_text())
    host_reports = [
        {
            "host": "docker-runtime",
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
        "docker-runtime": [
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
                {"vm": "docker-runtime", "environments": {"production": {"status": "active"}}},
                {"vm": "coolify", "environments": {"production": {"status": "active"}}},
                {"vm": "backup", "environments": {"production": {"status": "active"}}},
                {"vm": "old-host", "environments": {"production": {"status": "retired"}}},
                {"vm": "proxmox-host"},
            ]
        },
    )

    assert report.default_lynis_hosts("production") == [
        "backup_guests",
        "coolify",
        "docker-runtime",
        "proxmox-host",
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
                    "host": "docker-runtime",
                    "hardening_index": 72,
                    "hardening_index_delta": -11,
                }
            ],
            "images": [
                {
                    "host": "docker-runtime",
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
        "/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/worker.id_ed25519",
        repo_root=repo_root,
    )

    assert resolved == mirrored_secret


def test_resolve_repo_local_path_maps_inaccessible_controller_local_secret(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    mirrored_secret = repo_root / ".local" / "ssh" / "worker.id_ed25519"
    mirrored_secret.parent.mkdir(parents=True)
    mirrored_secret.write_text("secret", encoding="utf-8")
    inaccessible = "/private/tmp/nonexistent-controller/.local/ssh/worker.id_ed25519"

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
        inventory=[tmp_path / "inventory.yml", tmp_path / "local-inventory.yml"],
        playbook=tmp_path / "playbook.yml",
        output_dir=tmp_path / "output",
        hosts=["proxmox-host", "docker-runtime"],
        bootstrap_key=tmp_path / "bootstrap.id_ed25519",
        jump_host_addr="10.10.10.1",
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == "ansible-playbook"
    assert [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-i"] == [
        str(tmp_path / "inventory.yml"),
        str(tmp_path / "local-inventory.yml"),
    ]
    assert "--private-key" in command
    assert "proxmox_guest_ssh_connection_mode=proxmox_host_jump" in command
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["LV3_BOOTSTRAP_SSH_PRIVATE_KEY"] == str(tmp_path / "bootstrap.id_ed25519")
    assert env["LV3_PROXMOX_HOST_ADDR"] == "10.10.10.1"


def test_security_report_parser_accepts_layered_inventory_sources(tmp_path: Path) -> None:
    args = report.build_parser().parse_args(
        ["--inventory", str(tmp_path / "repo.yml"), "--inventory", str(tmp_path / "local.yml")]
    )

    assert args.inventories == [tmp_path / "repo.yml", tmp_path / "local.yml"]


def test_resolve_trivy_guest_addresses_uses_layered_inventory(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None):
        captured["command"] = command
        return drift_lib.CommandResult(
            argv=command,
            returncode=0,
            stdout=json.dumps(
                {
                    "production": {
                        "hosts": [
                            "docker-runtime-yourname",
                            "docker-runtime-lv3",
                            "docker-build-yourname",
                            "docker-build-lv3",
                        ]
                    },
                    "_meta": {
                        "hostvars": {
                            "docker-runtime-yourname": {"ansible_host": "10.10.10.20"},
                            "docker-runtime-lv3": {"ansible_host": "10.20.10.20"},
                            "docker-build-yourname": {"ansible_host": "10.10.10.30"},
                            "docker-build-lv3": {"ansible_host": "10.20.10.30"},
                        }
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(report, "run_command", fake_run_command)
    inventory_paths = [tmp_path / "repo.yml", tmp_path / "local.yml"]

    resolved = report.resolve_trivy_guest_addresses(inventory_paths, ["docker-runtime", "docker-build"], "production")

    assert resolved == {"docker-runtime": "10.20.10.20", "docker-build": "10.20.10.30"}
    command = captured["command"]
    assert isinstance(command, list)
    assert [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-i"] == [
        str(path) for path in inventory_paths
    ]


def test_build_guest_ssh_command_makes_proxy_non_interactive(tmp_path: Path) -> None:
    context = {
        "bootstrap_key": tmp_path / "worker.id_ed25519",
        "host_user": "ops",
        "host_addr": "100.64.0.1",
        "host_port": "2222",
        "guests": {"docker-runtime": "10.10.10.20"},
    }
    command = drift_lib.build_guest_ssh_command(
        context,
        "docker-runtime",
        "true",
    )
    tunnel_command = drift_lib.build_guest_ssh_tunnel_command(
        context,
        "docker-runtime",
        local_bind="127.0.0.1:4222",
        remote_bind="127.0.0.1:4222",
    )

    for ssh_command in (command, tunnel_command):
        joined = " ".join(ssh_command)
        assert "ProxyCommand=ssh" in joined
        assert " -p 2222 " in joined
        assert " -W %h:%p " in joined
        assert joined.index(" -W %h:%p ") < joined.index("ops@100.64.0.1")
        assert "StrictHostKeyChecking=no" in joined
        assert "UserKnownHostsFile=/dev/null" in joined


def test_resolve_nats_tunnel_target_prefers_runtime_control() -> None:
    target = drift_lib.resolve_nats_tunnel_target(
        {
            "guests": {
                "docker-runtime": "10.10.10.20",
                "runtime-control": "10.10.10.92",
            }
        }
    )

    assert target == "runtime-control"


def test_resolve_nats_tunnel_target_falls_back_to_docker_runtime() -> None:
    target = drift_lib.resolve_nats_tunnel_target({"guests": {"docker-runtime": "10.10.10.20"}})

    assert target == "docker-runtime"


def test_inventory_guest_proxy_command_is_non_interactive() -> None:
    candidate_paths = (
        REPO_ROOT / "inventory" / "group_vars" / "all" / "main.yml",
        REPO_ROOT / "inventory" / "group_vars" / "all.yml",
    )
    group_vars_path = next(path for path in candidate_paths if path.exists())
    group_vars = group_vars_path.read_text(encoding="utf-8")

    assert "proxmox_guest_ssh_proxy_command" in group_vars
    assert (
        'ProxyCommand="ssh -p {{ proxmox_guest_ssh_jump_port }} -W %h:%p -o IdentitiesOnly=yes -i {{ proxmox_guest_ssh_bootstrap_key_path }}'
        in group_vars
    )
    assert (
        'proxmox_host_jump: "-o IdentitiesOnly=yes -i {{ proxmox_guest_ssh_bootstrap_key_path }} {{ proxmox_guest_ssh_proxy_command }}"'
        in group_vars
    )
    assert "LV3_PROXMOX_HOST_ADDR" in group_vars
    assert "LV3_PROXMOX_HOST_PORT" in group_vars


def test_inventory_proxmox_host_is_env_overridable() -> None:
    inventory = (REPO_ROOT / "inventory" / "hosts.yml").read_text(encoding="utf-8")

    assert "lookup('env', 'LV3_PROXMOX_HOST_ADDR')" in inventory
    assert "lookup('env', 'LV3_PROXMOX_HOST_PORT')" in inventory


def test_skip_lynis_reuses_cached_reports(monkeypatch, tmp_path: Path) -> None:
    cached_dir = tmp_path / "lynis"
    cached_dir.mkdir()
    fixture = REPO_ROOT / "tests" / "fixtures" / "security_posture_docker_runtime.dat"
    (cached_dir / "docker-runtime-lynis-report.dat").write_text(fixture.read_text(), encoding="utf-8")

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


def test_main_treats_optional_publish_failures_as_warnings(monkeypatch, tmp_path: Path, capsys) -> None:
    cached_dir = tmp_path / "lynis"
    cached_dir.mkdir()
    fixture = REPO_ROOT / "tests" / "fixtures" / "security_posture_docker_runtime.dat"
    (cached_dir / "docker-runtime-lynis-report.dat").write_text(fixture.read_text(), encoding="utf-8")

    monkeypatch.setattr(report, "load_controller_context", lambda: {"bootstrap_key": None, "host_addr": "100.64.0.1"})
    monkeypatch.setattr(report, "load_previous_report", lambda _path: None)
    monkeypatch.setattr(report, "run_remote_script", lambda **_kwargs: {})
    monkeypatch.setattr(report, "write_receipt", lambda _dir, _report: tmp_path / "receipt.json")
    monkeypatch.setattr(
        report,
        "build_security_events",
        lambda _report: [{"event": "platform.security.critical-finding", "kind": "security-finding"}],
    )
    monkeypatch.setattr(report, "maybe_publish_nats", lambda *args, **kwargs: None)
    monkeypatch.setattr(report, "maybe_write_metrics", lambda _report: (_ for _ in ()).throw(RuntimeError("metrics")))
    monkeypatch.setattr(report, "emit_event_best_effort", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        report, "post_mattermost_summary", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("mattermost"))
    )
    monkeypatch.setattr(
        report, "post_glitchtip_events", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("glitchtip"))
    )

    exit_code = report.main(
        [
            "--env",
            "production",
            "--skip-lynis",
            "--skip-trivy",
            "--lynis-dir",
            str(cached_dir),
            "--mattermost-webhook-url",
            "https://example.com/hooks/security",
            "--glitchtip-event-url",
            "https://example.com/api/events",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code in {0, 1, 2}
    assert "failed to publish metrics: metrics" in captured.err
    assert "failed to publish mattermost: mattermost" in captured.err
    assert "failed to publish glitchtip: glitchtip" in captured.err
