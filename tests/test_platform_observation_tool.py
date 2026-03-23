import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import platform_observation_tool as tool


def test_parse_not_after_reads_subject_and_expiry():
    subject, expires = tool.parse_not_after(
        "subject=CN=example\nnotAfter=Mar 23 20:32:11 2026 GMT\n"
    )
    assert subject == "CN=example"
    assert expires is not None
    assert expires.year == 2026


def test_evaluate_probe_result_accepts_expected_stdout():
    probe = {
        "id": "grafana-api-health",
        "service_id": "grafana",
        "runner": "controller_local",
        "target": "controller",
        "expect": {"exit_code": 0, "stdout_contains": ["ok"]},
    }
    result = tool.CommandResult(command="curl ...", returncode=0, stdout='{"database":"ok"}', stderr="")
    ok, detail = tool.evaluate_probe_result(probe, result)
    assert ok is True
    assert detail["ok"] is True


def test_build_daily_digest_includes_findings():
    digest = tool.build_daily_digest(
        [
            {
                "check": "check-vm-state",
                "severity": "ok",
                "summary": "All managed guests are running.",
                "details": [{"managed_guest_count": 6}],
                "ts": "2026-03-22T00:00:00Z",
                "run_id": "00000000-0000-0000-0000-000000000000",
            }
        ]
    )
    assert "# LV3 Platform Findings" in digest
    assert "check-vm-state [ok]" in digest


def test_write_outputs_creates_digest_and_json(tmp_path: Path):
    findings = [
        {
            "check": "check-secret-ages",
            "severity": "warning",
            "summary": "Secret is close to expiry.",
            "details": [{"secret_id": "foo"}],
            "ts": "2026-03-22T00:00:00Z",
            "run_id": "00000000-0000-0000-0000-000000000001",
        }
    ]
    output_dir = tmp_path / "out"
    digest_path = tmp_path / "digest.md"
    tool.write_outputs(findings, output_dir, digest_path)
    assert (output_dir / "findings.json").exists()
    assert (output_dir / "check-secret-ages.json").exists()
    assert digest_path.exists()


def test_format_certificate_subject_flattens_nested_pairs():
    subject = ((("commonName", "proxmox.lv3.org"),), (("organizationName", "LV3"),))
    assert tool.format_certificate_subject(subject) == "commonName=proxmox.lv3.org, organizationName=LV3"


def test_normalize_image_reference_strips_default_registry_prefixes():
    assert tool.normalize_image_reference("docker.io/netboxcommunity/netbox:v4.5") == "netboxcommunity/netbox:v4.5"
    assert tool.normalize_image_reference("index.docker.io/library/redis:7") == "redis:7"


def test_check_image_freshness_flags_unpinned_and_local_build(monkeypatch):
    catalog = {
        "images": [
            {
                "id": "windmill-server",
                "service_id": "windmill",
                "runtime_host": "docker-runtime-lv3",
                "container_name": "windmill-windmill_server-1",
                "image_reference": "ghcr.io/windmill-labs/windmill:main",
                "source_kind": "upstream",
                "pin_status": "unpinned",
                "pinned_digest": None,
            },
            {
                "id": "mail-gateway",
                "service_id": "mail_platform",
                "runtime_host": "docker-runtime-lv3",
                "container_name": "lv3-mail-gateway",
                "image_reference": "mail-platform-mail-gateway",
                "source_kind": "local_build",
                "pin_status": "local_build",
                "pinned_digest": None,
            },
        ]
    }

    real_load_json = tool.load_json

    def fake_load_json(path):
        if path == tool.IMAGE_CATALOG_PATH:
            return catalog
        return real_load_json(path)

    def fake_execute_runner(context, runner, target, command):
        del context, runner, target
        if "windmill-windmill_server-1" in command:
            return tool.CommandResult(
                command=command,
                returncode=0,
                stdout="ghcr.io/windmill-labs/windmill:main|sha256:abc",
                stderr="",
            )
        return tool.CommandResult(
            command=command,
            returncode=0,
            stdout="mail-platform-mail-gateway|sha256:def",
            stderr="",
        )

    monkeypatch.setattr(tool, "load_json", fake_load_json)
    monkeypatch.setattr(tool, "execute_runner", fake_execute_runner)

    finding = tool.check_image_freshness({}, "run-1")

    assert finding["severity"] == "warning"
    assert [entry["image_id"] for entry in finding["details"]] == ["mail-gateway", "windmill-server"]
    assert finding["details"][0]["status"] == "local_build_ok"
    assert finding["details"][1]["status"] == "unpinned"


def test_check_image_freshness_supports_pinned_mapping_catalog(monkeypatch):
    catalog = {
        "images": {
            "windmill_runtime": {
                "kind": "runtime",
                "service_id": "windmill",
                "runtime_host": "docker-runtime-lv3",
                "container_name": "windmill-windmill_server-1",
                "ref": "ghcr.io/windmill-labs/windmill:1.662.0@sha256:abc",
                "digest": "sha256:abc",
            },
            "mail_platform_gateway_python_base": {
                "kind": "build_base",
                "ref": "docker.io/library/python:3.13.12-slim-trixie@sha256:def",
                "digest": "sha256:def",
            },
        }
    }

    real_load_json = tool.load_json

    def fake_load_json(path):
        if path == tool.IMAGE_CATALOG_PATH:
            return catalog
        return real_load_json(path)

    def fake_execute_runner(context, runner, target, command):
        del context
        assert runner == "guest_jump"
        assert target == "docker-runtime-lv3"
        assert "windmill-windmill_server-1" in command
        return tool.CommandResult(
            command=command,
            returncode=0,
            stdout="ghcr.io/windmill-labs/windmill:1.662.0@sha256:abc|sha256:abc",
            stderr="",
        )

    monkeypatch.setattr(tool, "load_json", fake_load_json)
    monkeypatch.setattr(tool, "execute_runner", fake_execute_runner)

    finding = tool.check_image_freshness({}, "run-2")

    assert finding["severity"] == "ok"
    assert finding["outputs"]["checked_image_count"] == 1
    assert finding["details"] == [
        {
            "image_id": "windmill_runtime",
            "service_id": "windmill",
            "container_name": "windmill-windmill_server-1",
            "expected_reference": "ghcr.io/windmill-labs/windmill:1.662.0@sha256:abc",
            "running_reference": "ghcr.io/windmill-labs/windmill:1.662.0@sha256:abc",
            "running_digest": "sha256:abc",
            "pin_status": "pinned",
            "status": "pinned_ok",
        }
    ]


def test_check_certificate_expiry_uses_tls_probe(monkeypatch):
    def fake_execute_runner(context, runner, target, command):
        del context, target, command
        assert runner == "host_ssh"
        return tool.CommandResult(
            command="openssl x509",
            returncode=0,
            stdout="subject=CN=proxmox.lv3.org\nnotAfter=Jun 19 20:50:43 2026 GMT\n",
            stderr="",
        )

    def fake_probe_tls_certificate(host, port, server_name=None, timeout_seconds=10):
        del server_name, timeout_seconds
        mapping = {
            ("100.118.189.95", 9443): ("commonName=step-ca", tool.parse_date("2026-04-23T20:32:11Z")),
            ("100.118.189.95", 8200): ("commonName=openbao", tool.parse_date("2026-04-23T18:36:41Z")),
            ("100.118.189.95", 9444): ("commonName=portainer", tool.parse_date("2031-03-22T19:17:59Z")),
        }
        return mapping[(host, port)]

    monkeypatch.setattr(tool, "execute_runner", fake_execute_runner)
    monkeypatch.setattr(tool, "probe_tls_certificate", fake_probe_tls_certificate)
    monkeypatch.setattr(tool, "utc_now", lambda: tool.parse_date("2026-03-23T00:00:00Z"))

    finding = tool.check_certificate_expiry({}, "run-2")

    assert finding["severity"] == "ok"
    assert [entry["certificate_id"] for entry in finding["details"]] == [
        "openbao-proxy",
        "portainer-proxy",
        "proxmox-ui",
        "step-ca-proxy",
    ]


def test_check_service_health_supports_service_catalog(monkeypatch):
    catalog = {
        "services": {
            "windmill": {
                "service_name": "windmill",
                "owning_vm": "docker-runtime-lv3",
                "liveness": {
                    "kind": "command",
                    "description": "worker process",
                    "timeout_seconds": 10,
                    "retries": 1,
                    "delay_seconds": 0,
                    "argv": ["echo", "windmill"],
                    "success_rc": 0,
                },
                "readiness": {
                    "kind": "http",
                    "description": "api version",
                    "timeout_seconds": 10,
                    "retries": 1,
                    "delay_seconds": 0,
                    "url": "http://127.0.0.1:8000/api/version",
                    "method": "GET",
                    "expected_status": [200],
                },
            }
        }
    }
    real_load_json = tool.load_json

    def fake_load_json(path):
        if path == tool.HEALTH_PROBE_CATALOG_PATH:
            return catalog
        return real_load_json(path)

    def fake_execute_runner(context, runner, target, command):
        del context
        assert runner == "guest_jump"
        assert target == "docker-runtime-lv3"
        if "echo" in command:
            return tool.CommandResult(command=command, returncode=0, stdout="windmill", stderr="")
        return tool.CommandResult(
            command=command,
            returncode=0,
            stdout='{"version":"1.0"}\n__STATUS__=200',
            stderr="",
        )

    monkeypatch.setattr(tool, "load_json", fake_load_json)
    monkeypatch.setattr(tool, "execute_runner", fake_execute_runner)

    finding = tool.check_service_health({}, "run-3")

    assert finding["severity"] == "ok"
    assert finding["outputs"]["checked_probe_count"] == 2
    assert [entry["probe_id"] for entry in finding["details"]] == ["windmill-liveness", "windmill-readiness"]


def test_run_checks_suppresses_maintenance_findings_and_skips_webhooks(monkeypatch, tmp_path: Path):
    captured_findings = []
    webhook_payloads = []

    monkeypatch.setattr(
        tool,
        "load_observation_context",
        lambda: {"secret_manifest": {"secrets": {}}},
    )
    monkeypatch.setattr(
        tool,
        "CHECK_HANDLERS",
        {
            "check-service-health": lambda _context, run_id: {
                "check": "check-service-health",
                "severity": "critical",
                "summary": "1 service probe failed.",
                "details": [{"service_id": "grafana", "probe_id": "grafana-ready", "ok": False}],
                "ts": "2026-03-23T10:00:00Z",
                "run_id": run_id,
            }
        },
    )
    monkeypatch.setattr(
        tool,
        "list_active_windows_best_effort",
        lambda _context: {
            "maintenance/grafana": {
                "window_id": "33333333-3333-3333-3333-333333333333",
                "service_id": "grafana",
                "reason": "deploy",
                "opened_by": {"class": "operator", "id": "ops-linux"},
                "opened_at": "2026-03-23T09:50:00Z",
                "expected_duration_minutes": 30,
                "auto_close_at": "2026-03-23T10:20:00Z",
                "correlation_id": "deploy:grafana",
            }
        },
    )
    monkeypatch.setattr(
        tool,
        "write_outputs",
        lambda findings, _output_dir, _digest_path: captured_findings.extend(findings),
    )
    monkeypatch.setattr(tool, "post_json_webhook", lambda url, payload, headers=None: webhook_payloads.append(payload))

    args = argparse.Namespace(
        output_dir=str(tmp_path / "out"),
        digest_path=str(tmp_path / "digest.md"),
        publish_nats=False,
        mattermost_webhook_url="http://mattermost.example",
        glitchtip_event_url="http://glitchtip.example",
        checks=["check-service-health"],
    )

    exit_code = tool.run_checks(args)

    assert exit_code == 0
    assert captured_findings[0]["severity"] == "suppressed"
    assert webhook_payloads == []
