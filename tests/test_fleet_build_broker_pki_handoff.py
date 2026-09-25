from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "fleet_build_broker_pki_handoff"
)
SCRIPT_PATH = ROLE_ROOT / "templates" / "fleet-build-broker-pki-handoff.py"
PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "fleet-build-broker-pki.yml"
)
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"

spec = importlib.util.spec_from_file_location("fleet_build_broker_pki_handoff", SCRIPT_PATH)
assert spec and spec.loader
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


def _run(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True)


def _make_certificate_authority(
    directory: Path, name: str, issuer: tuple[Path, Path] | None = None
) -> tuple[Path, Path]:
    certificate = directory / f"{name}.crt"
    private_key = directory / f"{name}.key"
    request = directory / f"{name}.csr"
    extensions = directory / f"{name}-extensions.cnf"
    path_length = "0" if name == handoff.BROKER_CLIENT_CA_SUBJECT else "1"
    extensions.write_text(
        f"[broker_ca]\nbasicConstraints=critical,CA:TRUE,pathlen:{path_length}\nkeyUsage=critical,keyCertSign,cRLSign\n"
    )
    _run(
        [
            "/usr/bin/openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(private_key),
            "-out",
            str(request),
            "-subj",
            f"/CN={name}",
        ]
    )
    if issuer is None:
        _run(
            [
                "/usr/bin/openssl",
                "x509",
                "-req",
                "-in",
                str(request),
                "-signkey",
                str(private_key),
                "-out",
                str(certificate),
                "-days",
                "30",
                "-extfile",
                str(extensions),
                "-extensions",
                "broker_ca",
            ]
        )
    else:
        _run(
            [
                "/usr/bin/openssl",
                "x509",
                "-req",
                "-in",
                str(request),
                "-CA",
                str(issuer[0]),
                "-CAkey",
                str(issuer[1]),
                "-CAcreateserial",
                "-out",
                str(certificate),
                "-days",
                "30",
                "-extfile",
                str(extensions),
                "-extensions",
                "broker_ca",
            ]
        )
    return certificate, private_key


def _make_leaf(
    directory: Path, name: str, extensions: str, issuer: tuple[Path, Path] | None = None
) -> tuple[Path, Path]:
    certificate = directory / f"{name}.crt"
    private_key = directory / f"{name}.key"
    request = directory / f"{name}.csr"
    extension_file = directory / f"{name}-extensions.cnf"
    extension_file.write_text(extensions)
    _run(
        [
            "/usr/bin/openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(private_key),
            "-out",
            str(request),
            "-subj",
            f"/CN={name}",
        ]
    )
    if issuer is None:
        _run(
            [
                "/usr/bin/openssl",
                "x509",
                "-req",
                "-in",
                str(request),
                "-signkey",
                str(private_key),
                "-out",
                str(certificate),
                "-days",
                "1",
                "-extfile",
                str(extension_file),
            ]
        )
    else:
        _run(
            [
                "/usr/bin/openssl",
                "x509",
                "-req",
                "-in",
                str(request),
                "-CA",
                str(issuer[0]),
                "-CAkey",
                str(issuer[1]),
                "-CAcreateserial",
                "-out",
                str(certificate),
                "-days",
                "1",
                "-extfile",
                str(extension_file),
            ]
        )
    return certificate, private_key


def _make_fixture_pki(directory: Path) -> dict[str, tuple[Path, Path]]:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    root = _make_certificate_authority(directory, "root")
    client_ca = _make_certificate_authority(directory, handoff.BROKER_CLIENT_CA_SUBJECT)
    client_ca[0].chmod(0o444)
    client_ca[1].chmod(0o400)
    materials = {"root": root, "client_ca": client_ca}
    materials["server"] = _make_leaf(
        directory,
        "server",
        "subjectAltName=DNS:fleet-build-broker.internal,IP:198.51.100.80\nextendedKeyUsage=serverAuth\n",
        root,
    )
    for client_id, details in handoff.EXPECTED_CLIENTS.items():
        materials[client_id] = _make_leaf(
            directory,
            client_id,
            f"subjectAltName=URI:{details['spiffe_id']}\nextendedKeyUsage=clientAuth\n",
            client_ca,
        )
    return materials


def _write_fake_step(directory: Path, fixtures: Path) -> Path:
    path = directory / "fake-step.py"
    path.write_text(
        """#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sys

args = sys.argv[1:]
fixtures = Path(os.environ['PKI_FIXTURES'])
if args[:2] == ['ca', 'certificate']:
    source = 'server'
elif args[:2] == ['certificate', 'create']:
    source = Path(args[-2]).stem
else:
    raise SystemExit(12)
certificate = Path(args[-2])
private_key = Path(args[-1])
shutil.copyfile(fixtures / f'{source}.crt', certificate)
shutil.copyfile(fixtures / f'{source}.key', private_key)
"""
    )
    path.chmod(0o700)
    return path


def _write_fake_writer(directory: Path, success: bool = True) -> Path:
    path = directory / "fake-writer.py"
    path.write_text(
        """#!/usr/bin/env python3
import os
from pathlib import Path
import sys

Path(os.environ['WRITER_ARGS']).write_text('\\n'.join(sys.argv[1:]))
Path(os.environ['WRITER_PAYLOAD']).write_bytes(sys.stdin.buffer.read())
raise SystemExit(0 if os.environ.get('WRITER_SUCCESS') == '1' else 42)
"""
    )
    path.chmod(0o700)
    return path


def _config(tmp_path: Path, *, step: Path, writer: Path, materials: dict[str, tuple[Path, Path]]) -> dict[str, object]:
    state_directory = tmp_path / "state"
    client_ca_directory = state_directory / "client-ca"
    client_ca_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_directory.chmod(0o700)
    client_ca_directory.chmod(0o700)
    client_ca_certificate = client_ca_directory / "client-ca.crt"
    client_ca_key = client_ca_directory / "client-ca.key"
    shutil.copyfile(materials["client_ca"][0], client_ca_certificate)
    shutil.copyfile(materials["client_ca"][1], client_ca_key)
    client_ca_certificate.chmod(0o444)
    client_ca_key.chmod(0o400)
    return {
        "schema_version": 1,
        "lifecycle": {
            "leaf_lifetime_seconds": 86400,
            "renew_at_elapsed_seconds": 69120,
            "timer_interval_seconds": 3600,
            "state_file": str(state_directory / "issuance.json"),
        },
        "step_ca": {
            "command": [sys.executable, str(step)],
            "ca_url": "https://ca.example.test",
            "root_certificate_file": str(materials["root"][0]),
            "provisioner": "services",
            "provisioner_password_file": str(tmp_path / "services-password"),
        },
        "client_ca": {
            "directory": str(client_ca_directory),
            "certificate_file": str(client_ca_certificate),
            "key_file": str(client_ca_key),
            "subject": handoff.BROKER_CLIENT_CA_SUBJECT,
            "lifetime_seconds": handoff.CLIENT_CA_LIFETIME_SECONDS,
            "rotate_before_seconds": handoff.CLIENT_CA_ROTATE_BEFORE_SECONDS,
            "trust_secret": "fleet_build_broker_client_ca",
            "trust_consumers": [handoff.RUNTIME_RENDERER],
        },
        "writer": {
            "command": [sys.executable, str(writer)],
            "principal": handoff.WRITER_PRINCIPAL,
            "scope": "infra-privileged",
            "ttl_seconds": 300,
        },
        "server": {
            "subject": "fleet-build-broker.internal",
            "ip_san": "198.51.100.80",
            "sans": ["fleet-build-broker.internal", "198.51.100.80"],
            "cert_secret": "fleet_build_broker_server_cert",
            "key_secret": "fleet_build_broker_server_key",
            "consumers": ["fleet-build-broker-runtime-renderer"],
        },
        "server_trust": {
            "source_file": str(materials["root"][0]),
            "secret": "fleet_build_broker_server_ca",
            "consumers": [
                "fleet-build-broker-monitor-renderer",
                "fleet-build-broker-builder-0docker",
                "fleet-build-broker-builder-0mcp",
            ],
        },
        "clients": [
            {"id": client_id, **details, "extended_key_usage": "clientAuth"}
            for client_id, details in handoff.EXPECTED_CLIENTS.items()
        ],
    }


def test_role_installs_root_only_timer_and_short_lived_writer_boundary() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    service = (ROLE_ROOT / "templates" / "fleet-build-broker-pki-renew.service.j2").read_text()
    readme = (ROLE_ROOT / "README.md").read_text()

    assert defaults["fleet_build_broker_pki_handoff_on_calendar"] == "hourly"
    assert defaults["fleet_build_broker_pki_vault_writer_command"] == []
    assert any(
        task["name"] == "Validate the rendered broker PKI handoff contract without issuing material" for task in tasks
    )
    assert "User=root" in service
    assert "UMask=0077" in service
    assert "ProtectSystem=strict" in service
    assert "five-minute `infra-privileged` API key" in readme
    assert "revoke the key in a `finally` path" in readme
    assert any(task["name"] == "Bootstrap or validate the broker-exclusive client trust anchor" for task in tasks)
    assert "not chained to the platform root" in readme

    handoff_binary_task = next(
        task for task in tasks if task["name"] == "Install the root-only broker PKI handoff executable"
    )
    assert handoff_binary_task["ansible.builtin.template"] == {
        "src": "fleet-build-broker-pki-handoff.py",
        "dest": "{{ fleet_build_broker_pki_handoff_binary_path }}",
        "owner": "root",
        "group": "root",
        "mode": "0700",
    }
    assert "ansible.builtin.copy" not in handoff_binary_task


def test_pki_handoff_has_a_dedicated_step_ca_control_host_playbook() -> None:
    playbook = yaml.safe_load(PLAYBOOK_PATH.read_text())

    assert (
        playbook[0]["hosts"]
        == "{{ 'docker-runtime-staging' if (env | default('production')) == 'staging' else 'runtime-control' }}"
    )
    assert playbook[0]["become"] is True
    assert playbook[0]["roles"] == [{"role": "lv3.platform.fleet_build_broker_pki_handoff"}]


def test_pki_writer_bridge_firewall_is_limited_to_runtime_control_ssh() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]

    writer_bridge_rules = [
        rule
        for rule in docker_runtime_rules
        if rule["description"] == "Root-only fleet-build-broker PKI writer bridge from runtime-control"
    ]

    assert writer_bridge_rules == [
        {
            "source": "runtime-control",
            "protocol": "tcp",
            "ports": [22],
            "description": "Root-only fleet-build-broker PKI writer bridge from runtime-control",
        }
    ]


def test_plan_locks_server_sans_client_spiffe_and_renderer_principals(tmp_path: Path) -> None:
    materials = _make_fixture_pki(tmp_path / "materials")
    step = _write_fake_step(tmp_path, tmp_path / "materials")
    writer = _write_fake_writer(tmp_path)
    config = _config(tmp_path, step=step, writer=writer, materials=materials)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(path), "--plan"],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(completed.stdout)

    assert plan["leaf_lifetime_seconds"] == 86400
    assert plan["renew_at_elapsed_seconds"] == 69120
    assert plan["server"] == {
        "subject": "fleet-build-broker.internal",
        "sans": ["fleet-build-broker.internal", "198.51.100.80"],
        "eku": "serverAuth",
    }
    assert plan["client_trust_anchor"] == {
        "subject": "fleet-build-broker-client-ca",
        "lifetime_seconds": 7_776_000,
        "rotate_before_seconds": 604_800,
        "consumers": ["fleet-build-broker-runtime-renderer"],
    }
    assert {item["spiffe_id"] for item in plan["clients"]} == {
        "spiffe://0exec.com/fleet/builder/0docker",
        "spiffe://example.org/fleet/builder/0mcp",
        "spiffe://example.org/fleet/monitor/fleet-build-broker",
    }
    assert {item["consumer"] for item in plan["clients"]} == {
        "fleet-build-broker-builder-0docker",
        "fleet-build-broker-builder-0mcp",
        "fleet-build-broker-monitor-renderer",
    }


def test_config_rejects_cross_renderer_secret_authority(tmp_path: Path) -> None:
    materials = _make_fixture_pki(tmp_path / "materials")
    config = _config(
        tmp_path,
        step=_write_fake_step(tmp_path, tmp_path / "materials"),
        writer=_write_fake_writer(tmp_path),
        materials=materials,
    )
    config["server"]["consumers"] = ["fleet-build-broker-monitor-renderer"]  # type: ignore[index]

    try:
        handoff.validate_config(config)
    except handoff.HandoffError as error:
        assert "authority boundary" in str(error)
    else:
        raise AssertionError("cross-renderer authority was accepted")


def test_config_rejects_platform_or_cross_renderer_client_trust(tmp_path: Path) -> None:
    materials = _make_fixture_pki(tmp_path / "materials")
    config = _config(
        tmp_path,
        step=_write_fake_step(tmp_path, tmp_path / "materials"),
        writer=_write_fake_writer(tmp_path),
        materials=materials,
    )
    config["client_ca"]["trust_consumers"] = [  # type: ignore[index]
        handoff.RUNTIME_RENDERER,
        handoff.MONITOR_RENDERER,
    ]

    with pytest.raises(handoff.HandoffError, match="authority boundary"):
        handoff.validate_config(config)


def test_root_bootstrap_creates_self_signed_broker_only_client_ca(tmp_path: Path, monkeypatch) -> None:
    materials = _make_fixture_pki(tmp_path / "materials")
    config = _config(
        tmp_path,
        step=_write_fake_step(tmp_path, tmp_path / "materials"),
        writer=_write_fake_writer(tmp_path),
        materials=materials,
    )
    client_ca = config["client_ca"]  # type: ignore[index]
    Path(client_ca["certificate_file"]).unlink()
    Path(client_ca["key_file"]).unlink()
    monkeypatch.setattr(handoff.os, "geteuid", lambda: 0)

    not_after = handoff._bootstrap_dedicated_client_ca(config, int(time.time()))

    certificate = Path(client_ca["certificate_file"])
    private_key = Path(client_ca["key_file"])
    assert not_after > int(time.time()) + handoff.CLIENT_CA_ROTATE_BEFORE_SECONDS
    assert stat.S_IMODE(certificate.stat().st_mode) == 0o444
    assert stat.S_IMODE(private_key.stat().st_mode) == 0o400
    assert "CN=fleet-build-broker-client-ca" in handoff._certificate_extension(certificate, "basicConstraints")
    assert handoff._certificate_name(certificate, "subject") == "CN=fleet-build-broker-client-ca"
    assert handoff._certificate_name(certificate, "issuer") == "CN=fleet-build-broker-client-ca"


def test_root_bootstrap_refuses_partial_trust_anchor(tmp_path: Path, monkeypatch) -> None:
    materials = _make_fixture_pki(tmp_path / "materials")
    config = _config(
        tmp_path,
        step=_write_fake_step(tmp_path, tmp_path / "materials"),
        writer=_write_fake_writer(tmp_path),
        materials=materials,
    )
    client_ca = config["client_ca"]  # type: ignore[index]
    Path(client_ca["certificate_file"]).unlink()
    monkeypatch.setattr(handoff.os, "geteuid", lambda: 0)

    with pytest.raises(handoff.HandoffError, match="incomplete"):
        handoff._bootstrap_dedicated_client_ca(config, int(time.time()))


def test_cross_signed_or_unsafe_client_ca_is_rejected(tmp_path: Path) -> None:
    materials = _make_fixture_pki(tmp_path / "materials")
    config = _config(
        tmp_path,
        step=_write_fake_step(tmp_path, tmp_path / "materials"),
        writer=_write_fake_writer(tmp_path),
        materials=materials,
    )
    client_ca = config["client_ca"]  # type: ignore[index]
    cross_signed_certificate, cross_signed_key = _make_certificate_authority(
        tmp_path,
        handoff.BROKER_CLIENT_CA_SUBJECT,
        materials["root"],
    )
    certificate = Path(client_ca["certificate_file"])
    private_key = Path(client_ca["key_file"])
    certificate.unlink()
    private_key.unlink()
    shutil.copyfile(cross_signed_certificate, certificate)
    shutil.copyfile(cross_signed_key, private_key)
    certificate.chmod(0o444)
    private_key.chmod(0o400)

    with pytest.raises(handoff.HandoffError, match="self-signed and broker-exclusive"):
        handoff._verify_dedicated_client_ca(config, int(time.time()))

    certificate.unlink()
    shutil.copyfile(materials["client_ca"][0], certificate)
    certificate.chmod(0o644)
    with pytest.raises(handoff.HandoffError, match="unsafe permissions"):
        handoff._verify_dedicated_client_ca(config, int(time.time()))


def test_client_leaf_chains_only_to_broker_trust_anchor(tmp_path: Path) -> None:
    materials = _make_fixture_pki(tmp_path / "materials")
    config = _config(
        tmp_path,
        step=_write_fake_step(tmp_path, tmp_path / "materials"),
        writer=_write_fake_writer(tmp_path),
        materials=materials,
    )
    client = {
        "id": "builder-0docker",
        **handoff.EXPECTED_CLIENTS["builder-0docker"],
        "extended_key_usage": "clientAuth",
    }
    broker_leaf = materials["builder-0docker"]
    assert handoff._verify_client_leaf(
        broker_leaf[0],
        broker_leaf[1],
        client,
        config["client_ca"],
        int(time.time()),  # type: ignore[index]
    ) > int(time.time())

    platform_leaf = _make_leaf(
        tmp_path,
        "platform-client",
        f"subjectAltName=URI:{client['spiffe_id']}\nextendedKeyUsage=clientAuth\n",
        materials["root"],
    )
    with pytest.raises(handoff.HandoffError, match="issuer validation command failed"):
        handoff._verify_client_leaf(
            platform_leaf[0],
            platform_leaf[1],
            client,
            config["client_ca"],
            int(time.time()),  # type: ignore[index]
        )


def test_root_renewal_validates_material_and_sends_only_stdin_to_writer(tmp_path: Path, monkeypatch) -> None:
    fixtures = tmp_path / "materials"
    materials = _make_fixture_pki(fixtures)
    step = _write_fake_step(tmp_path, fixtures)
    writer = _write_fake_writer(tmp_path)
    config = _config(tmp_path, step=step, writer=writer, materials=materials)

    password = Path(config["step_ca"]["provisioner_password_file"])  # type: ignore[index]
    password.write_text("synthetic-password-not-a-production-secret\n")
    capture_args = tmp_path / "writer-args"
    capture_payload = tmp_path / "writer-payload"
    monkeypatch.setenv("PKI_FIXTURES", str(fixtures))
    monkeypatch.setenv("WRITER_ARGS", str(capture_args))
    monkeypatch.setenv("WRITER_PAYLOAD", str(capture_payload))
    monkeypatch.setenv("WRITER_SUCCESS", "1")
    monkeypatch.setattr(handoff.os, "geteuid", lambda: 0)

    assert handoff.renew(config) == {"status": "renewed"}
    writer_args = capture_args.read_text()
    payload = json.loads(capture_payload.read_text())
    state = json.loads(Path(config["lifecycle"]["state_file"]).read_text())  # type: ignore[index]

    assert "transaction" in writer_args
    assert "--principal\nfleet-build-broker-pki-renewer" in writer_args
    assert "--scope\ninfra-privileged" in writer_args
    assert "synthetic-password-not-a-production-secret" not in writer_args
    assert len(payload["secrets"]) == 10
    assert {secret["name"] for secret in payload["secrets"]} >= {
        "fleet_build_broker_server_cert",
        "fleet_build_broker_server_key",
        "fleet_build_broker_client_ca",
        "fleet_build_broker_server_ca",
        "fleet_build_broker_monitor_cert",
        "fleet_build_broker_monitor_key",
    }
    assert state["status"] == "ok"
    assert stat.S_IMODE(Path(config["lifecycle"]["state_file"]).stat().st_mode) == 0o600  # type: ignore[index]
    assert handoff.health(config) == {"status": "healthy"}


def test_writer_failure_records_safe_failure_and_health_fails_closed(tmp_path: Path, monkeypatch) -> None:
    fixtures = tmp_path / "materials"
    materials = _make_fixture_pki(fixtures)
    step = _write_fake_step(tmp_path, fixtures)
    writer = _write_fake_writer(tmp_path)
    config = _config(tmp_path, step=step, writer=writer, materials=materials)
    Path(config["step_ca"]["provisioner_password_file"]).write_text("fixture\n")  # type: ignore[index]
    monkeypatch.setenv("PKI_FIXTURES", str(fixtures))
    monkeypatch.setenv("WRITER_ARGS", str(tmp_path / "writer-args"))
    monkeypatch.setenv("WRITER_PAYLOAD", str(tmp_path / "writer-payload"))
    monkeypatch.setenv("WRITER_SUCCESS", "0")
    monkeypatch.setattr(handoff.os, "geteuid", lambda: 0)

    try:
        handoff.renew(config)
    except handoff.HandoffError as error:
        assert str(error) == "fleet-secrets transaction failed"
    else:
        raise AssertionError("writer failure did not fail renewal")

    state = json.loads(Path(config["lifecycle"]["state_file"]).read_text())  # type: ignore[index]
    assert state["status"] == "failed"
    try:
        handoff.health(config)
    except handoff.HandoffError as error:
        assert "no successful" in str(error)
    else:
        raise AssertionError("failed issuance incorrectly passed health")


def test_overdue_80_percent_renewal_is_unhealthy(tmp_path: Path) -> None:
    materials = _make_fixture_pki(tmp_path / "materials")
    config = _config(
        tmp_path,
        step=_write_fake_step(tmp_path, tmp_path / "materials"),
        writer=_write_fake_writer(tmp_path),
        materials=materials,
    )
    state_path = Path(config["lifecycle"]["state_file"])  # type: ignore[index]
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "ok",
                "last_success_epoch": 1,
                "renew_after_epoch": 1,
                "leaf_not_after_epoch": 4_102_444_800,
            }
        )
    )

    try:
        handoff.health(config)
    except handoff.HandoffError as error:
        assert "80 percent" in str(error)
    else:
        raise AssertionError("overdue renewal incorrectly passed health")
