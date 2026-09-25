import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "fleet_build_broker_pki_vault_writer"
)
SCRIPT_PATH = ROLE_ROOT / "templates" / "fleet-build-broker-pki-vault-writer.py.j2"


def _load_writer_module():
    spec = importlib.util.spec_from_loader("broker_pki_writer", SourceFileLoader("broker_pki_writer", str(SCRIPT_PATH)))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_payload(writer):
    return {
        "schema_version": 1,
        "secrets": [
            {
                "name": name,
                "value": f"-----BEGIN TEST {index}-----\\nvalue\\n-----END TEST {index}-----\\n",
                "consumers": list(consumers),
                "description": description,
            }
            for index, (name, consumers, description) in enumerate(writer.EXPECTED_BATCH, start=1)
        ],
    }


def test_writer_role_is_dockerhost_only_and_forces_one_exact_transaction() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    authorized_keys = (ROLE_ROOT / "templates" / "authorized_keys.j2").read_text()
    sudoers = (ROLE_ROOT / "templates" / "sudoers.j2").read_text()
    sshd = (ROLE_ROOT / "templates" / "sshd-fleet-build-broker-pki-writer.conf.j2").read_text()

    assert defaults["fleet_build_broker_pki_vault_writer_apikey_url"] == "http://127.0.0.1:18021"
    assert defaults["fleet_build_broker_pki_vault_writer_vault_url"] == "https://fleet-secrets.0exec.com"
    assert defaults["fleet_build_broker_pki_vault_writer_admin_token_file"] == "/opt/_shared/apikey-admin.env"
    assert defaults["fleet_build_broker_pki_vault_writer_timeout_seconds"] == 15

    validate = tasks[0]["ansible.builtin.assert"]["that"]
    assert "inventory_hostname == 'docker-runtime'" in validate
    assert any("authorized_public_key is match" in item for item in validate)
    assert any("apikey_url == 'http://127.0.0.1:18021'" in item for item in validate)
    assert any("vault_url == 'https://fleet-secrets.0exec.com'" in item for item in validate)

    for restriction in (
        "restrict",
        "no-port-forwarding",
        "no-agent-forwarding",
        "no-X11-forwarding",
        "no-pty",
        "no-user-rc",
    ):
        assert restriction in authorized_keys
    assert 'from="{{ fleet_build_broker_pki_vault_writer_allowed_source }}"' in authorized_keys
    assert 'command="/usr/bin/sudo -n' in authorized_keys
    assert (
        "transaction --principal fleet-build-broker-pki-renewer --scope infra-privileged --ttl-seconds 300"
        in authorized_keys
    )
    assert "NOPASSWD:" in sudoers
    assert "*" not in sudoers
    assert "Match User {{ fleet_build_broker_pki_vault_writer_user }}" in sshd
    assert "PasswordAuthentication no" in sshd
    assert "KbdInteractiveAuthentication no" in sshd
    assert "    PermitUserEnvironment " not in sshd
    assert "restrict" in authorized_keys
    assert "PermitTTY no" in sshd
    assert sshd.rstrip().endswith("Match all")
    assert "AllowTcpForwarding no" in sshd

    config_directory_task = next(
        task
        for task in tasks
        if task["name"] == "Ensure the writer configuration directory permits only SSH key traversal"
    )
    authorization_task = next(task for task in tasks if task["name"] == "Render the dedicated forced SSH authorization")
    transaction_config_task = next(
        task for task in tasks if task["name"] == "Render the root-only broker PKI vault writer configuration"
    )

    assert config_directory_task["ansible.builtin.file"] == {
        "path": "{{ fleet_build_broker_pki_vault_writer_config_dir }}",
        "state": "directory",
        "owner": "root",
        "group": "{{ fleet_build_broker_pki_vault_writer_group }}",
        "mode": "0710",
    }
    assert authorization_task["ansible.builtin.template"]["owner"] == "root"
    assert authorization_task["ansible.builtin.template"]["group"] == "{{ fleet_build_broker_pki_vault_writer_group }}"
    assert authorization_task["ansible.builtin.template"]["mode"] == "0640"
    assert transaction_config_task["ansible.builtin.template"]["owner"] == "root"
    assert transaction_config_task["ansible.builtin.template"]["group"] == "root"
    assert transaction_config_task["ansible.builtin.template"]["mode"] == "0600"


def test_writer_accepts_only_the_exact_ten_record_broker_batch() -> None:
    writer = _load_writer_module()
    payload = _valid_payload(writer)

    assert writer._validate_payload(payload) == payload
    assert len(writer.EXPECTED_BATCH) == 10

    wrong_consumer = _valid_payload(writer)
    wrong_consumer["secrets"][0]["consumers"] = ["other"]
    with pytest.raises(writer.BridgeError):
        writer._validate_payload(wrong_consumer)

    reordered = _valid_payload(writer)
    reordered["secrets"][0], reordered["secrets"][1] = reordered["secrets"][1], reordered["secrets"][0]
    with pytest.raises(writer.BridgeError):
        writer._validate_payload(reordered)

    extra = _valid_payload(writer)
    extra["secrets"].append(extra["secrets"][0])
    with pytest.raises(writer.BridgeError):
        writer._validate_payload(extra)


def test_writer_hardcodes_the_one_use_writer_and_avoids_shell_or_environment_transport() -> None:
    source = SCRIPT_PATH.read_text()
    writer = _load_writer_module()

    assert writer.WRITER_PRINCIPAL == "fleet-build-broker-pki-renewer"
    assert writer.WRITER_SCOPE == "infra-privileged"
    assert writer.WRITER_TIER == "infra-privileged"
    assert writer.WRITER_TTL_SECONDS == 300
    assert writer.WRITER_USE_LIMIT == 1
    assert writer.KEY_PATTERN.fullmatch("ak_" + "a" * 32) is not None
    assert writer.KEY_PATTERN.fullmatch("ak_" + "A" * 32) is None
    assert writer.APIKEY_URL == "http://127.0.0.1:18021"
    assert writer.VAULT_URL == "https://fleet-secrets.0exec.com"
    assert 'f"{VAULT_URL}/broker-pki-batch"' in source
    assert "ProxyHandler({})" in source
    assert "NoRedirect" in source
    assert "required root-owned parent directory is writable by another principal" in source
    assert "subprocess" not in source
    assert "os.environ" not in source
    assert "shell=True" not in source
    assert 'print("fleet-build-broker PKI vault transaction failed"' in source
    assert "writer_key" not in source.split('print("fleet-build-broker PKI vault transaction failed"')[1]


def test_writer_configuration_refuses_any_endpoint_or_credential_path_change() -> None:
    writer = _load_writer_module()
    config = {
        "managed-by": "test",
        "schema_version": 1,
        "admin_token_file": "/opt/_shared/apikey-admin.env",
        "apikey_url": "http://127.0.0.1:18021",
        "vault_url": "https://fleet-secrets.0exec.com",
        "timeout_seconds": 15,
    }

    assert writer._validate_config(config) == config
    changed = dict(config, vault_url="https://example.invalid")
    with pytest.raises(writer.BridgeError):
        writer._validate_config(changed)
    changed = dict(config, admin_token_file="/tmp/key")
    with pytest.raises(writer.BridgeError):
        writer._validate_config(changed)


def test_writer_permits_only_traversal_for_its_fixed_configuration_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    writer = _load_writer_module()
    writer_group_id = 987
    monkeypatch.setattr(writer.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=writer_group_id))

    def directory(mode: int, *, uid: int = 0, gid: int = 0) -> SimpleNamespace:
        return SimpleNamespace(st_mode=stat.S_IFDIR | mode, st_uid=uid, st_gid=gid)

    writer._safe_parent_directory(
        writer.CONFIG_PATH,
        writer.CONFIG_PATH.parent,
        directory(0o710, gid=writer_group_id),
    )

    for unsafe_parent in (
        directory(0o750, gid=writer_group_id),
        directory(0o710, gid=0),
        directory(0o730, gid=writer_group_id),
    ):
        with pytest.raises(writer.BridgeError):
            writer._safe_parent_directory(writer.CONFIG_PATH, writer.CONFIG_PATH.parent, unsafe_parent)

    with pytest.raises(writer.BridgeError):
        writer._safe_parent_directory(
            writer.ADMIN_TOKEN_FILE,
            writer.ADMIN_TOKEN_FILE.parent,
            directory(0o710, gid=writer_group_id),
        )


def test_transaction_always_attempts_writer_revocation_after_issuance(monkeypatch) -> None:
    writer = _load_writer_module()
    payload = _valid_payload(writer)
    events = []

    monkeypatch.setattr(writer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(writer, "_issue_writer", lambda: events.append("issue") or ("ak_" + "a" * 32))
    monkeypatch.setattr(
        writer, "_submit_batch", lambda key, batch: events.append(("submit", key, batch["schema_version"]))
    )
    monkeypatch.setattr(writer, "_revoke_writer", lambda key: events.append(("revoke", key)))

    writer._transaction({}, payload)
    assert events == [
        "issue",
        ("submit", "ak_" + "a" * 32, 1),
        ("revoke", "ak_" + "a" * 32),
    ]

    events.clear()

    def fail_submit(key, batch):
        events.append(("submit", key, batch["schema_version"]))
        raise writer.BridgeError("network failure")

    monkeypatch.setattr(writer, "_submit_batch", fail_submit)
    with pytest.raises(writer.BridgeError):
        writer._transaction({}, payload)
    assert events == [
        "issue",
        ("submit", "ak_" + "a" * 32, 1),
        ("revoke", "ak_" + "a" * 32),
    ]
