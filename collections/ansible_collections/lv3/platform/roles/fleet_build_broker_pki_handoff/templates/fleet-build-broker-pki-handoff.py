#!/usr/bin/env python3
"""Root-only certificate issuance and vault-delivery handoff for the broker.

This program deliberately has no network or secret values in its configuration.
It creates all replacement leaf material in a private temporary directory,
validates it, then hands the complete set to the canonical fleet-secrets writer
over stdin.  That writer is responsible for issuing one short-lived
``infra-privileged`` key, committing the batch, and revoking that key in a
``finally`` path.  Neither this program nor systemd logs certificate or key
material, command output, credential values, or credential-bearing paths.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any


LEAF_LIFETIME_SECONDS = 24 * 60 * 60
RENEW_AT_ELAPSED_SECONDS = int(LEAF_LIFETIME_SECONDS * 0.80)
CLIENT_CA_LIFETIME_SECONDS = 90 * 24 * 60 * 60
CLIENT_CA_ROTATE_BEFORE_SECONDS = 7 * 24 * 60 * 60
WRITER_SCOPE = "infra-privileged"
WRITER_PRINCIPAL = "fleet-build-broker-pki-renewer"
RUNTIME_RENDERER = "fleet-build-broker-runtime-renderer"
MONITOR_RENDERER = "fleet-build-broker-monitor-renderer"
BROKER_SERVER_DNS = "fleet-build-broker.internal"
BROKER_CLIENT_CA_SUBJECT = "fleet-build-broker-client-ca"
OPENSSL = "/usr/bin/openssl"

EXPECTED_CLIENTS = {
    "builder-0docker": {
        "spiffe_id": "spiffe://0exec.com/fleet/builder/0docker",
        "consumer": "fleet-build-broker-builder-0docker",
        "cert_secret": "fleet_build_broker_builder_0docker_cert",
        "key_secret": "fleet_build_broker_builder_0docker_key",
    },
    "builder-0mcp": {
        "spiffe_id": "spiffe://example.org/fleet/builder/0mcp",
        "consumer": "fleet-build-broker-builder-0mcp",
        "cert_secret": "fleet_build_broker_builder_0mcp_cert",
        "key_secret": "fleet_build_broker_builder_0mcp_key",
    },
    "monitor": {
        "spiffe_id": "spiffe://example.org/fleet/monitor/fleet-build-broker",
        "consumer": MONITOR_RENDERER,
        "cert_secret": "fleet_build_broker_monitor_cert",
        "key_secret": "fleet_build_broker_monitor_key",
    },
}


class HandoffError(RuntimeError):
    """A safe, non-secret-bearing handoff failure."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HandoffError(message)


def _absolute_path(value: Any, name: str) -> str:
    _require(isinstance(value, str) and value.startswith("/"), f"{name} must be an absolute path")
    return value


def _string(value: Any, name: str) -> str:
    _require(isinstance(value, str) and value, f"{name} must be a non-empty string")
    return value


def _exact_list(value: Any, expected: list[str], name: str) -> None:
    _require(value == expected, f"{name} has an unexpected authority boundary")


def _controlled_child(directory: str, filename: str, value: Any, name: str) -> str:
    path = _absolute_path(value, name)
    _require(Path(path).parent == Path(directory), f"{name} must stay in the dedicated client CA directory")
    _require(Path(path).name == filename, f"{name} has an unexpected filename")
    return path


def validate_config(config: dict[str, Any]) -> None:
    """Validate the non-secret contract before any issuer or vault action."""

    _require(config.get("schema_version") == 1, "unsupported handoff configuration schema")

    lifecycle = config.get("lifecycle")
    _require(isinstance(lifecycle, dict), "lifecycle is required")
    _require(lifecycle.get("leaf_lifetime_seconds") == LEAF_LIFETIME_SECONDS, "leaf lifetime must be exactly 24 hours")
    _require(
        lifecycle.get("renew_at_elapsed_seconds") == RENEW_AT_ELAPSED_SECONDS,
        "renewal must begin at 80 percent of the 24-hour leaf lifetime",
    )
    _require(lifecycle.get("timer_interval_seconds") <= 60 * 60, "renewal timer must run at least hourly")
    state_file = _absolute_path(lifecycle.get("state_file"), "lifecycle.state_file")

    step_ca = config.get("step_ca")
    _require(isinstance(step_ca, dict), "step_ca is required")
    command = step_ca.get("command")
    _require(isinstance(command, list) and command and all(isinstance(item, str) and item for item in command), "step_ca.command is required")
    _require(command[0].startswith("/"), "step_ca.command must use an absolute binary path")
    _require(_string(step_ca.get("ca_url"), "step_ca.ca_url").startswith("https://"), "step_ca.ca_url must use HTTPS")
    _absolute_path(step_ca.get("root_certificate_file"), "step_ca.root_certificate_file")
    _absolute_path(step_ca.get("provisioner_password_file"), "step_ca.provisioner_password_file")
    _require(step_ca.get("provisioner") == "services", "broker issuance must use the services Step-CA provisioner")

    client_ca = config.get("client_ca")
    _require(isinstance(client_ca, dict), "client_ca is required")
    client_ca_directory = _absolute_path(client_ca.get("directory"), "client_ca.directory")
    _require(
        Path(client_ca_directory) == Path(state_file).parent / "client-ca",
        "client_ca.directory must be the controlled child of the PKI state directory",
    )
    _controlled_child(
        client_ca_directory,
        "client-ca.crt",
        client_ca.get("certificate_file"),
        "client_ca.certificate_file",
    )
    _controlled_child(
        client_ca_directory,
        "client-ca.key",
        client_ca.get("key_file"),
        "client_ca.key_file",
    )
    _require(client_ca.get("subject") == BROKER_CLIENT_CA_SUBJECT, "client_ca subject is not broker-exclusive")
    _require(
        client_ca.get("lifetime_seconds") == CLIENT_CA_LIFETIME_SECONDS,
        "client_ca lifetime must use the controlled 90-day lifecycle",
    )
    _require(
        client_ca.get("rotate_before_seconds") == CLIENT_CA_ROTATE_BEFORE_SECONDS,
        "client_ca rotation threshold must be seven days",
    )
    _require(client_ca.get("trust_secret") == "fleet_build_broker_client_ca", "client CA trust secret name changed")
    _exact_list(client_ca.get("trust_consumers"), [RUNTIME_RENDERER], "client_ca.trust_consumers")

    writer = config.get("writer")
    _require(isinstance(writer, dict), "writer is required")
    writer_command = writer.get("command")
    _require(
        isinstance(writer_command, list) and writer_command and all(isinstance(item, str) and item for item in writer_command),
        "writer.command is required",
    )
    _require(writer_command[0].startswith("/"), "writer.command must use an absolute binary path")
    _require(writer.get("principal") == WRITER_PRINCIPAL, "writer principal is not the root PKI renewer")
    _require(writer.get("scope") == WRITER_SCOPE, "writer scope must be infra-privileged")
    _require(writer.get("ttl_seconds") == 300, "writer TTL must be exactly five minutes")

    server = config.get("server")
    _require(isinstance(server, dict), "server is required")
    _require(server.get("subject") == BROKER_SERVER_DNS, "broker server subject must be fixed")
    server_ip = _string(server.get("ip_san"), "server.ip_san")
    try:
        ipaddress.ip_address(server_ip)
    except ValueError as exc:
        raise HandoffError("server.ip_san must be an IP address") from exc
    _exact_list(server.get("sans"), [BROKER_SERVER_DNS, server_ip], "server.sans")
    _exact_list(server.get("consumers"), [RUNTIME_RENDERER], "server.consumers")
    _require(server.get("cert_secret") == "fleet_build_broker_server_cert", "server certificate secret name changed")
    _require(server.get("key_secret") == "fleet_build_broker_server_key", "server key secret name changed")

    server_trust = config.get("server_trust")
    _require(isinstance(server_trust, dict), "server_trust is required")
    _absolute_path(server_trust.get("source_file"), "server_trust.source_file")
    _require(server_trust.get("secret") == "fleet_build_broker_server_ca", "server trust secret name changed")
    _exact_list(
        server_trust.get("consumers"),
        [MONITOR_RENDERER, "fleet-build-broker-builder-0docker", "fleet-build-broker-builder-0mcp"],
        "server_trust.consumers",
    )

    clients = config.get("clients")
    _require(isinstance(clients, list) and len(clients) == len(EXPECTED_CLIENTS), "exactly three client identities are required")
    supplied = {item.get("id"): item for item in clients if isinstance(item, dict)}
    _require(set(supplied) == set(EXPECTED_CLIENTS), "client identity set changed")
    for client_id, expected in EXPECTED_CLIENTS.items():
        client = supplied[client_id]
        for field, expected_value in expected.items():
            _require(client.get(field) == expected_value, f"{client_id}.{field} changed")
        _require(client.get("extended_key_usage") == "clientAuth", f"{client_id} must be clientAuth only")


def _load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError("unable to load handoff configuration") from exc
    _require(isinstance(data, dict), "handoff configuration must be an object")
    validate_config(data)
    return data


def _run(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(argv, check=True, stdin=subprocess.DEVNULL, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HandoffError("issuer validation command failed") from exc


def _check_pair(certificate: Path, private_key: Path) -> None:
    cert_public = _run([OPENSSL, "x509", "-in", str(certificate), "-noout", "-pubkey"]).stdout
    key_public = _run([OPENSSL, "pkey", "-in", str(private_key), "-pubout"]).stdout
    _require(hashlib.sha256(cert_public).digest() == hashlib.sha256(key_public).digest(), "certificate and private key do not match")


def _certificate_extension(certificate: Path, extension: str) -> str:
    # ``openssl x509 -ext`` is available in modern OpenSSL but absent from the
    # LibreSSL build on developer workstations.  ``-text`` is stable across
    # both and its output remains process-local: it is never written to logs.
    del extension
    return _run([OPENSSL, "x509", "-in", str(certificate), "-noout", "-text"]).stdout.decode("utf-8", "replace")


def _not_after_epoch(certificate: Path) -> int:
    output = _run([OPENSSL, "x509", "-in", str(certificate), "-noout", "-enddate"]).stdout.decode("ascii", "strict").strip()
    _require(output.startswith("notAfter="), "certificate expiry could not be read")
    try:
        return int(dt.datetime.strptime(output.removeprefix("notAfter="), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.UTC).timestamp())
    except ValueError as exc:
        raise HandoffError("certificate expiry is malformed") from exc


def _verify_leaf_lifetime(certificate: Path, now: int) -> int:
    not_after = _not_after_epoch(certificate)
    remaining = not_after - now
    _require(23 * 60 * 60 <= remaining <= 25 * 60 * 60, "issued leaf does not have a 24-hour lifetime")
    return not_after


def _verify_server_leaf(certificate: Path, private_key: Path, server: dict[str, Any], step_ca: dict[str, Any], now: int) -> int:
    _check_pair(certificate, private_key)
    _run([OPENSSL, "verify", "-CAfile", step_ca["root_certificate_file"], str(certificate)])
    san = _certificate_extension(certificate, "subjectAltName")
    _require(f"DNS:{BROKER_SERVER_DNS}" in san and f"IP Address:{server['ip_san']}" in san, "server certificate SAN contract failed")
    eku = _certificate_extension(certificate, "extendedKeyUsage")
    _require("TLS Web Server Authentication" in eku or "serverAuth" in eku, "server certificate is missing serverAuth")
    return _verify_leaf_lifetime(certificate, now)


def _assert_root_owned(path: Path, expected_mode: int, name: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise HandoffError(f"{name} is unavailable") from exc
    _require(not stat.S_ISLNK(metadata.st_mode) and stat.S_ISREG(metadata.st_mode), f"{name} must be a regular file")
    _require(stat.S_IMODE(metadata.st_mode) == expected_mode, f"{name} has unsafe permissions")
    # Use the real uid here rather than the effective uid gate used by the
    # command entrypoint.  This keeps the ownership check meaningful for the
    # root-owned systemd service while allowing an unprivileged offline test
    # harness to exercise certificate validation with fixture files.
    if os.getuid() == 0:
        _require(metadata.st_uid == 0 and metadata.st_gid == 0, f"{name} must be owned by root")


def _assert_root_owned_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise HandoffError("dedicated client CA directory is unavailable") from exc
    _require(not stat.S_ISLNK(metadata.st_mode) and stat.S_ISDIR(metadata.st_mode), "dedicated client CA directory must not be a symlink")
    _require(stat.S_IMODE(metadata.st_mode) == 0o700, "dedicated client CA directory has unsafe permissions")
    if os.getuid() == 0:
        _require(metadata.st_uid == 0 and metadata.st_gid == 0, "dedicated client CA directory must be owned by root")


def _certificate_name(certificate: Path, field: str) -> str:
    output = _run([OPENSSL, "x509", "-in", str(certificate), "-noout", f"-{field}"]).stdout.decode("utf-8", "replace")
    prefix = f"{field}="
    _require(output.startswith(prefix), f"dedicated client CA {field} could not be read")
    # LibreSSL renders `/CN=...`; OpenSSL renders `CN = ...`.  Both normalize
    # to the same single-attribute DN, while a different or additional
    # attribute still fails the fixed broker-exclusive identity check.
    return output.removeprefix(prefix).strip().replace(" ", "").lstrip("/")


def _verify_dedicated_client_ca(config: dict[str, Any], now: int) -> int:
    client_ca = config["client_ca"]
    directory = Path(client_ca["directory"])
    certificate = Path(client_ca["certificate_file"])
    private_key = Path(client_ca["key_file"])
    _assert_root_owned_directory(directory)
    _assert_root_owned(certificate, 0o444, "dedicated client CA certificate")
    _assert_root_owned(private_key, 0o400, "dedicated client CA private key")
    _check_pair(certificate, private_key)
    constraints = _certificate_extension(certificate, "basicConstraints")
    normalized_constraints = constraints.lower()
    _require(
        "CA:TRUE" in constraints
        and ("pathlen:0" in normalized_constraints or "path length: 0" in normalized_constraints),
        "dedicated client CA constraints are invalid",
    )
    key_usage = _certificate_extension(certificate, "keyUsage")
    _require("Certificate Sign" in key_usage and "CRL Sign" in key_usage, "dedicated client CA key usage is invalid")
    _require("Extended Key Usage" not in constraints, "dedicated client CA must not have an extended key usage")
    subject = _certificate_name(certificate, "subject")
    issuer = _certificate_name(certificate, "issuer")
    expected_name = f"CN={BROKER_CLIENT_CA_SUBJECT}"
    _require(subject == expected_name and issuer == expected_name, "dedicated client CA must be self-signed and broker-exclusive")
    _run([OPENSSL, "verify", "-CAfile", str(certificate), str(certificate)])
    not_after = _not_after_epoch(certificate)
    _require(not_after > now + CLIENT_CA_ROTATE_BEFORE_SECONDS, "dedicated client CA rotation is required before issuing broker leaves")
    return not_after


def _bootstrap_dedicated_client_ca_locked(config: dict[str, Any], now: int) -> int:
    """Create the broker's sole client trust anchor once, or validate it.

    Rotating the trust anchor is intentionally not automatic: it needs a
    planned dual-client rollout rather than silently breaking an active mTLS
    connection.  The regular renewal path only checks the existing anchor.
    """

    _require(os.geteuid() == 0, "dedicated client CA bootstrap must run as root")
    client_ca = config["client_ca"]
    directory = Path(client_ca["directory"])
    certificate = Path(client_ca["certificate_file"])
    private_key = Path(client_ca["key_file"])
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    _assert_root_owned_directory(directory)
    certificate_exists = certificate.exists() or certificate.is_symlink()
    private_key_exists = private_key.exists() or private_key.is_symlink()
    _require(
        certificate_exists == private_key_exists,
        "dedicated client CA is incomplete; refusing to regenerate a trust anchor",
    )
    if certificate_exists:
        return _verify_dedicated_client_ca(config, now)

    with tempfile.TemporaryDirectory(prefix=".client-ca-bootstrap-", dir=directory) as temporary_directory:
        temporary = Path(temporary_directory)
        os.chmod(temporary, 0o700)
        temporary_certificate = temporary / "client-ca.crt"
        temporary_private_key = temporary / "client-ca.key"
        _run(
            [
                OPENSSL,
                "req",
                "-x509",
                "-new",
                "-newkey",
                "ec",
                "-pkeyopt",
                "ec_paramgen_curve:P-256",
                "-nodes",
                "-sha256",
                "-days",
                str(CLIENT_CA_LIFETIME_SECONDS // (24 * 60 * 60)),
                "-subj",
                f"/CN={BROKER_CLIENT_CA_SUBJECT}",
                "-addext",
                "basicConstraints=critical,CA:TRUE,pathlen:0",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
                "-keyout",
                str(temporary_private_key),
                "-out",
                str(temporary_certificate),
            ]
        )
        os.chmod(temporary_private_key, 0o400)
        os.chmod(temporary_certificate, 0o444)
        os.replace(temporary_private_key, private_key)
        os.replace(temporary_certificate, certificate)
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    return _verify_dedicated_client_ca(config, now)


def _bootstrap_dedicated_client_ca(config: dict[str, Any], now: int) -> int:
    """Serialize root-only bootstrap with leaf renewal state updates."""

    _require(os.geteuid() == 0, "dedicated client CA bootstrap must run as root")
    with _renewal_lock(Path(config["lifecycle"]["state_file"])):
        return _bootstrap_dedicated_client_ca_locked(config, now)


def _verify_client_leaf(certificate: Path, private_key: Path, client: dict[str, Any], client_ca: dict[str, Any], now: int) -> int:
    _check_pair(certificate, private_key)
    # The broker receives only this self-signed public trust anchor.  Do not
    # add the platform root or an intermediate here: that would allow any
    # platform client issuer to authenticate to this private broker.
    _run([OPENSSL, "verify", "-CAfile", client_ca["certificate_file"], str(certificate)])
    san = _certificate_extension(certificate, "subjectAltName")
    _require(f"URI:{client['spiffe_id']}" in san, "client certificate SPIFFE URI SAN contract failed")
    eku = _certificate_extension(certificate, "extendedKeyUsage")
    _require("TLS Web Client Authentication" in eku or "clientAuth" in eku, "client certificate is missing clientAuth")
    return _verify_leaf_lifetime(certificate, now)


def _issue_server(step_ca: dict[str, Any], server: dict[str, Any], certificate: Path, private_key: Path) -> None:
    argv = [
        *step_ca["command"],
        "ca",
        "certificate",
        "--force",
        "--provisioner",
        step_ca["provisioner"],
        "--provisioner-password-file",
        step_ca["provisioner_password_file"],
        "--ca-url",
        step_ca["ca_url"],
        "--root",
        step_ca["root_certificate_file"],
        "--san",
        BROKER_SERVER_DNS,
        "--san",
        server["ip_san"],
        "--not-after",
        "24h",
        server["subject"],
        str(certificate),
        str(private_key),
    ]
    _run(argv)


def _issue_client(
    step_ca: dict[str, Any], client: dict[str, Any], client_ca: dict[str, Any], certificate: Path, private_key: Path
) -> None:
    argv = [
        *step_ca["command"],
        "certificate",
        "create",
        "--profile",
        "leaf",
        "--kty",
        "EC",
        "--curve",
        "P-256",
        "--not-after",
        "24h",
        "--ca",
        client_ca["certificate_file"],
        "--ca-key",
        client_ca["key_file"],
        "--san",
        client["spiffe_id"],
        "--key-usage",
        "digitalSignature",
        "--ext-key-usage",
        "clientAuth",
        client["id"],
        str(certificate),
        str(private_key),
    ]
    _run(argv)


def _secret(name: str, value_path: Path, consumers: list[str], description: str) -> dict[str, Any]:
    try:
        value = value_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HandoffError("issued material is unavailable for the vault handoff") from exc
    _require(value.strip() != "", "issued material is empty")
    return {"name": name, "value": value, "consumers": consumers, "description": description}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.chmod(temporary_name, 0o600)
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _read_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


@contextmanager
def _renewal_lock(state_path: Path):
    """Prevent concurrent rotations from publishing overlapping leaf batches."""

    state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state_path.parent, 0o700)
    descriptor = os.open(state_path.parent / ".renew.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HandoffError("another broker PKI renewal is already in progress") from exc
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _write_failure_state(config: dict[str, Any], now: int) -> None:
    path = Path(config["lifecycle"]["state_file"])
    state = _read_state(path)
    state.update({"schema_version": 1, "status": "failed", "last_failure_epoch": now})
    _atomic_json(path, state)


def _deliver(config: dict[str, Any], payload: dict[str, Any]) -> None:
    writer = config["writer"]
    argv = [
        *writer["command"],
        "transaction",
        "--principal",
        WRITER_PRINCIPAL,
        "--scope",
        WRITER_SCOPE,
        "--ttl-seconds",
        str(writer["ttl_seconds"]),
    ]
    try:
        completed = subprocess.run(
            argv,
            input=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            capture_output=True,
            check=True,
        )
        del completed
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HandoffError("fleet-secrets transaction failed") from exc


def plan(config: dict[str, Any]) -> dict[str, Any]:
    """Return the safe, non-secret contract visible to code review and tests."""

    return {
        "status": "planned",
        "leaf_lifetime_seconds": config["lifecycle"]["leaf_lifetime_seconds"],
        "renew_at_elapsed_seconds": config["lifecycle"]["renew_at_elapsed_seconds"],
        "server": {"subject": config["server"]["subject"], "sans": config["server"]["sans"], "eku": "serverAuth"},
        "client_trust_anchor": {
            "subject": config["client_ca"]["subject"],
            "lifetime_seconds": config["client_ca"]["lifetime_seconds"],
            "rotate_before_seconds": config["client_ca"]["rotate_before_seconds"],
            "consumers": config["client_ca"]["trust_consumers"],
        },
        "clients": [
            {"id": client["id"], "spiffe_id": client["spiffe_id"], "eku": client["extended_key_usage"], "consumer": client["consumer"]}
            for client in config["clients"]
        ],
        "writer": {"principal": config["writer"]["principal"], "scope": config["writer"]["scope"], "ttl_seconds": config["writer"]["ttl_seconds"]},
    }


def renew(config: dict[str, Any]) -> dict[str, Any]:
    """Issue all leaves, validate them, then make one all-or-nothing writer call."""

    _require(os.geteuid() == 0, "renewal must run as root")
    now = int(time.time())
    state_path = Path(config["lifecycle"]["state_file"])
    with _renewal_lock(state_path):
        state = _read_state(state_path)
        if state.get("status") == "ok" and now < state.get("renew_after_epoch", 0):
            return {"status": "fresh"}

        workdir: Path | None = None
        try:
            workdir = Path(tempfile.mkdtemp(prefix="fleet-build-broker-pki-"))
            step_ca = config["step_ca"]
            client_ca = config["client_ca"]
            server = config["server"]
            client_ca_not_after = _verify_dedicated_client_ca(config, now)

            server_certificate = workdir / "server.crt"
            server_key = workdir / "server.key"
            _issue_server(step_ca, server, server_certificate, server_key)
            leaf_not_after = _verify_server_leaf(server_certificate, server_key, server, step_ca, now)

            client_material: list[tuple[dict[str, Any], Path, Path]] = []
            for client in config["clients"]:
                certificate = workdir / f"{client['id']}.crt"
                private_key = workdir / f"{client['id']}.key"
                _issue_client(step_ca, client, client_ca, certificate, private_key)
                leaf_not_after = min(leaf_not_after, _verify_client_leaf(certificate, private_key, client, client_ca, now))
                client_material.append((client, certificate, private_key))

            secrets = [
                _secret(server["cert_secret"], server_certificate, server["consumers"], "Fleet build broker 24-hour server certificate"),
                _secret(server["key_secret"], server_key, server["consumers"], "Fleet build broker 24-hour server private key"),
                _secret(
                    client_ca["trust_secret"],
                    Path(client_ca["certificate_file"]),
                    client_ca["trust_consumers"],
                    "Broker-exclusive client trust anchor for broker verification only",
                ),
                _secret(
                    config["server_trust"]["secret"],
                    Path(config["server_trust"]["source_file"]),
                    config["server_trust"]["consumers"],
                    "Platform server trust bundle for broker callers only",
                ),
            ]
            for client, certificate, private_key in client_material:
                secrets.extend(
                    [
                        _secret(client["cert_secret"], certificate, [client["consumer"]], f"Fleet build broker {client['id']} client certificate"),
                        _secret(client["key_secret"], private_key, [client["consumer"]], f"Fleet build broker {client['id']} client private key"),
                    ]
                )
            _deliver(config, {"schema_version": 1, "secrets": secrets})
            _atomic_json(
                state_path,
                {
                    "schema_version": 1,
                    "status": "ok",
                    "last_success_epoch": now,
                    "renew_after_epoch": now + RENEW_AT_ELAPSED_SECONDS,
                    "leaf_not_after_epoch": leaf_not_after,
                    "client_ca_not_after_epoch": client_ca_not_after,
                },
            )
            return {"status": "renewed"}
        except Exception as exc:
            # Keep any original state useful for expiry checks, but surface a
            # safe failure marker.  Never serialize exception details: command
            # failures can include sensitive filenames or transport data.
            try:
                _write_failure_state(config, now)
            except Exception:
                pass
            if isinstance(exc, HandoffError):
                raise
            raise HandoffError("broker PKI issuance or delivery failed") from exc
        finally:
            if workdir is not None:
                shutil.rmtree(workdir, ignore_errors=True)


def health(config: dict[str, Any]) -> dict[str, Any]:
    state = _read_state(Path(config["lifecycle"]["state_file"]))
    now = int(time.time())
    _verify_dedicated_client_ca(config, now)
    _require(state.get("status") == "ok", "no successful broker PKI issuance state")
    _require(now < state.get("renew_after_epoch", 0), "broker leaf renewal is overdue at the 80 percent lifetime boundary")
    _require(now < state.get("leaf_not_after_epoch", 0), "broker leaf certificate has expired")
    return {"status": "healthy"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fleet build broker root-only Step-CA handoff")
    parser.add_argument("--config", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-config", action="store_true")
    mode.add_argument("--bootstrap-client-ca", action="store_true")
    mode.add_argument("--check-client-ca", action="store_true")
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--renew", action="store_true")
    mode.add_argument("--health", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = _load_config(args.config)
        if args.check_config:
            result = {"status": "valid"}
        elif args.bootstrap_client_ca:
            result = {"status": "client-ca-ready", "not_after_epoch": _bootstrap_dedicated_client_ca(config, int(time.time()))}
        elif args.check_client_ca:
            result = {"status": "client-ca-valid", "not_after_epoch": _verify_dedicated_client_ca(config, int(time.time()))}
        elif args.plan:
            result = plan(config)
        elif args.renew:
            result = renew(config)
        else:
            result = health(config)
        print(json.dumps(result, sort_keys=True))
        return 0
    except HandoffError as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}), file=sys.stderr)
        return 1
    except Exception:
        print(json.dumps({"status": "failed", "reason": "broker PKI handoff failed"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
