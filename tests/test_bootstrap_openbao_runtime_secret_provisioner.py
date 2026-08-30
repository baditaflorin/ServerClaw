from __future__ import annotations

import importlib.util
import io
import json
import stat
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "bootstrap_openbao_runtime_secret_provisioner.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_openbao_runtime_secret_provisioner", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def configuration() -> Any:
    contracts = (
        MODULE.ServiceContract(
            registry_key="authentik",
            secret_namespace="authentik",
            secret_path="services/authentik/runtime-env",
            policy_name="test-service-authentik-runtime",
            approle_name="authentik-runtime",
        ),
        MODULE.ServiceContract(
            registry_key="rag_context",
            secret_namespace="platform-context",
            secret_path="services/platform-context/runtime-env",
            policy_name="test-service-platform-context-runtime",
            approle_name="platform-context-runtime",
        ),
    )
    provisioner_policy = "test-agent-runtime-secret-provisioner"
    policies = {contract.policy_name: MODULE._service_policy(contract) for contract in contracts}
    policies[provisioner_policy] = MODULE._provisioner_policy(contracts)
    roles = {
        contract.approle_name: MODULE.DesiredRole(contract.approle_name, contract.policy_name) for contract in contracts
    }
    roles[MODULE.PROVISIONER_ROLE_NAME] = MODULE.DesiredRole(MODULE.PROVISIONER_ROLE_NAME, provisioner_policy)
    return MODULE.BootstrapConfiguration(
        platform_domain="selected.example.net",
        config_prefix="test",
        api_url="http://127.0.0.1:8201",
        ssh_tunnel=MODULE.SSHTunnelConfiguration(
            jump_host="192.0.2.10",
            target_guest="runtime-control",
            target_host="10.10.10.92",
            remote_port=8201,
        ),
        contracts=contracts,
        policies=policies,
        roles=roles,
        provisioner_policy_name=provisioner_policy,
        protected_approle_names=("controller-automation", MODULE.PROVISIONER_ROLE_NAME),
    )


class FakeAPI:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.policies: dict[str, str] = {}
        self.roles: dict[str, dict[str, Any]] = {}
        self.role_ids: dict[str, str] = {}
        self.secret_ids: dict[tuple[str, str], str] = {}
        self.secret_id_accessors: dict[str, tuple[str, str]] = {}
        self.revoked_accessors: list[str] = []
        self.requests: list[tuple[str, str]] = []
        self.configuration_mutations: list[tuple[str, str]] = []
        self.admin_capabilities = ["create", "delete", "list", "patch", "read", "sudo", "update"]
        allowed, denied = MODULE._provisioner_capability_expectations(config)
        self.provisioner_capabilities = {path: sorted(caps) for path, caps in allowed.items()}
        self.provisioner_capabilities.update({path: ["deny"] for path in denied})
        self._secret_counter = 0

    def seed_desired_remote_state(self) -> None:
        self.policies = dict(self.config.policies)
        self.roles = {
            name: {**role.api_payload, "local_secret_ids": role.local_secret_ids}
            for name, role in self.config.roles.items()
        }

    def add_provisioner_credential(self, *, role_id: str, secret_id: str) -> None:
        self.role_ids[MODULE.PROVISIONER_ROLE_NAME] = role_id
        self.secret_ids[(role_id, secret_id)] = MODULE.PROVISIONER_ROLE_NAME

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
        expected_statuses: set[int] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del expected_statuses
        self.requests.append((method, path))
        if method == "GET" and path == "/v1/sys/health":
            return 200, {}
        if method == "GET" and path == "/v1/sys/seal-status":
            return 200, {"initialized": True, "sealed": False}
        if method == "POST" and path == "/v1/auth/userpass/login/breakglass":
            assert payload and payload.get("password") == "breakglass-password"
            return 200, {
                "auth": {
                    "client_token": "admin-token",
                    "policies": ["default", f"{self.config.config_prefix}-breakglass"],
                }
            }
        if method == "POST" and path == "/v1/sys/capabilities-self":
            assert payload and isinstance(payload.get("paths"), list)
            capability_source = (
                dict.fromkeys(payload["paths"], self.admin_capabilities)
                if token == "admin-token"
                else self.provisioner_capabilities
            )
            return 200, {
                "data": {requested: capability_source.get(requested, ["deny"]) for requested in payload["paths"]}
            }
        if path.startswith("/v1/sys/policies/acl/"):
            name = path.rsplit("/", 1)[-1]
            if method == "GET":
                return (
                    (200, {"data": {"name": name, "rules": self.policies[name]}})
                    if name in self.policies
                    else (404, {})
                )
            if method == "PUT":
                assert token == "admin-token" and payload and isinstance(payload.get("policy"), str)
                self.policies[name] = payload["policy"]
                self.configuration_mutations.append((method, path))
                return 204, {}
        if path.startswith("/v1/auth/approle/role/"):
            tail = path.removeprefix("/v1/auth/approle/role/")
            if tail.endswith("/role-id"):
                role_name = tail.removesuffix("/role-id")
                role_id = self.role_ids.setdefault(role_name, f"role-id-{role_name}")
                return 200, {"data": {"role_id": role_id}}
            if tail.endswith("/secret-id"):
                role_name = tail.removesuffix("/secret-id")
                assert method == "POST" and token == "admin-token"
                self._secret_counter += 1
                role_id = self.role_ids.setdefault(role_name, f"role-id-{role_name}")
                secret_id = f"generated-secret-{self._secret_counter}"
                self.secret_ids[(role_id, secret_id)] = role_name
                accessor = f"accessor-{self._secret_counter}"
                self.secret_id_accessors[accessor] = (role_id, secret_id)
                return 200, {
                    "data": {
                        "secret_id": secret_id,
                        "secret_id_accessor": accessor,
                    }
                }
            if tail.endswith("/secret-id-accessor/destroy"):
                assert method == "POST" and token == "admin-token" and payload
                accessor = payload.get("secret_id_accessor")
                assert isinstance(accessor, str)
                credential = self.secret_id_accessors.pop(accessor, None)
                if credential is not None:
                    self.secret_ids.pop(credential, None)
                self.revoked_accessors.append(accessor)
                return 204, {}
            role_name = tail
            if method == "GET":
                return (200, {"data": dict(self.roles[role_name])}) if role_name in self.roles else (404, {})
            if method == "POST":
                assert token == "admin-token" and payload
                # OpenBao's local_secret_ids setting is creation-only. Role
                # updates retain the existing value while new roles receive
                # the server default (false).
                local_secret_ids = self.roles.get(role_name, {}).get("local_secret_ids", False)
                self.roles[role_name] = {**payload, "local_secret_ids": local_secret_ids}
                self.role_ids.setdefault(role_name, f"role-id-{role_name}")
                self.configuration_mutations.append((method, path))
                return 204, {}
        if method == "POST" and path == "/v1/auth/approle/login":
            assert payload
            role_name = self.secret_ids.get((payload.get("role_id", ""), payload.get("secret_id", "")))
            if role_name != MODULE.PROVISIONER_ROLE_NAME:
                return 400, {}
            policies = self.roles[role_name]["token_policies"]
            policy_list = [policies] if isinstance(policies, str) else list(policies)
            return 200, {"auth": {"client_token": "provisioner-token", "policies": ["default", *policy_list]}}
        raise AssertionError(f"unexpected API request: {method} {path}")


def _write_sensitive(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def _write_artifact(path: Path, *, role_id: str, secret_id: str, role_name: str = MODULE.PROVISIONER_ROLE_NAME) -> None:
    _write_sensitive(
        path,
        json.dumps(
            {
                "auth_path": "approle",
                "role_name": role_name,
                "role_id": role_id,
                "secret_id": secret_id,
                "secret_id_accessor": "existing-accessor",
            }
        ),
    )


def test_configuration_derives_canonical_prefix_exact_contracts_and_namespace_override(tmp_path: Path) -> None:
    identity = tmp_path / "identity.yml"
    registry = tmp_path / "registry.yml"
    defaults = tmp_path / "defaults.yml"
    topology = tmp_path / "topology.yml"
    platform_vars = tmp_path / "platform.yml"
    identity.write_text(
        "platform_domain: example.org\nplatform_config_prefix: 0mpc\nmanagement_ipv4: 192.0.2.10\n",
        encoding="utf-8",
    )
    registry.write_text(
        """
platform_service_registry:
  openbao:
    service_type: platform_core
    needs_openbao: false
    host_group: runtime-control
  authentik:
    service_type: docker_compose
  disabled:
    service_type: docker_compose
    needs_openbao: false
  package:
    service_type: system_package
    needs_openbao: true
  rag_context:
    service_type: docker_compose
    needs_openbao: true
""".lstrip(),
        encoding="utf-8",
    )
    defaults.write_text(
        """
openbao_runtime_secret_provisioner_approle_name: runtime-secret-provisioner
openbao_runtime_secret_protected_approle_names:
  - controller-automation
  - runtime-secret-provisioner
openbao_runtime_secret_namespace_overrides:
  rag_context: platform-context
""".lstrip(),
        encoding="utf-8",
    )
    topology.write_text(
        """
management_tailscale_ipv4: 127.0.0.1
proxmox_internal_ipv4: 10.10.10.1
platform_port_assignments:
  openbao_http_port: 8201
  openbao_proxy_port: 8201
proxmox_guests:
  - name: runtime-control
    ipv4: 10.10.10.92
platform_service_topology:
  openbao:
    owning_vm: runtime-control
""".lstrip(),
        encoding="utf-8",
    )
    platform_vars.write_text(
        f"""
platform_generation:
  host_vars_source: {topology}
  identity_overlay:
    platform_domain: example.org
    management_ipv4: 192.0.2.10
platform_host:
  network:
    internal_ipv4: 10.10.10.1
platform_guest_catalog:
  by_name:
    runtime-control:
      ipv4: 10.10.10.92
platform_service_topology:
  openbao:
    owning_vm: runtime-control
    private_ip: 10.10.10.92
platform_port_assignments:
  openbao_http_port: 8201
  openbao_proxy_port: 8201
openbao_controller_url: https://127.0.0.1:8201
""".lstrip(),
        encoding="utf-8",
    )

    loaded = MODULE.load_configuration(
        identity,
        topology,
        registry_path=registry,
        defaults_path=defaults,
        platform_vars_path=platform_vars,
    )

    assert [contract.registry_key for contract in loaded.contracts] == ["authentik", "rag_context"]
    assert loaded.config_prefix == "0mcp"
    assert loaded.ssh_tunnel == MODULE.SSHTunnelConfiguration(
        jump_host="192.0.2.10",
        target_guest="runtime-control",
        target_host="10.10.10.92",
        remote_port=8201,
    )
    assert loaded.provisioner_policy_name == "0mcp-agent-runtime-secret-provisioner"
    rag_contract = loaded.contracts[1]
    assert rag_contract.secret_path == "services/platform-context/runtime-env"
    assert rag_contract.approle_name == "platform-context-runtime"
    assert rag_contract.policy_name == "0mcp-service-platform-context-runtime"
    assert 'path "kv/data/services/platform-context/runtime-env"' in loaded.policies[rag_contract.policy_name]
    assert (
        'path "auth/approle/role/platform-context-runtime/role-id"' in loaded.policies[loaded.provisioner_policy_name]
    )
    assert 'path "*"' not in "\n".join(loaded.policies.values())
    receipt = MODULE._receipt_payload(
        loaded,
        {"health_status": 200, "initialized": True, "sealed": False},
        MODULE.VerificationSummary(True, True, 1, 1),
        artifact_action="created",
        remote_changed=True,
    )
    assert receipt["provisioner"]["policy_name"] == "0mcp-agent-runtime-secret-provisioner"
    assert "init.json" not in SCRIPT_PATH.read_text(encoding="utf-8")

    other_topology = tmp_path / "other-topology.yml"
    other_topology.write_text(topology.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(MODULE.BootstrapError, match="topology selector"):
        MODULE.load_configuration(
            identity,
            other_topology,
            registry_path=registry,
            defaults_path=defaults,
            platform_vars_path=platform_vars,
        )


def test_configuration_rejects_generated_platform_from_another_identity(tmp_path: Path) -> None:
    identity = tmp_path / "identity.yml"
    registry = tmp_path / "registry.yml"
    defaults = tmp_path / "defaults.yml"
    topology = tmp_path / "topology.yml"
    platform_vars = tmp_path / "platform.yml"
    identity.write_text(
        "platform_domain: selected.example.net\nmanagement_ipv4: 192.0.2.10\n",
        encoding="utf-8",
    )
    registry.write_text(
        "platform_service_registry:\n  authentik:\n    service_type: docker_compose\n",
        encoding="utf-8",
    )
    defaults.write_text(
        """
openbao_runtime_secret_provisioner_approle_name: runtime-secret-provisioner
openbao_runtime_secret_protected_approle_names:
  - controller-automation
  - runtime-secret-provisioner
openbao_runtime_secret_namespace_overrides: {}
""".lstrip(),
        encoding="utf-8",
    )
    platform_vars.write_text(
        """
platform_generation:
  identity_overlay:
    platform_domain: another.example.net
openbao_controller_url: http://127.0.0.1:8201
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.BootstrapError, match="do not match the explicit identity"):
        MODULE.load_configuration(
            identity,
            topology,
            registry_path=registry,
            defaults_path=defaults,
            platform_vars_path=platform_vars,
        )


def test_apply_is_idempotent_preserves_valid_artifact_and_emits_non_secret_receipt(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)

    first = MODULE.reconcile(
        api,
        config,
        breakglass_password="breakglass-password",
        output_root=tmp_path,
        apply=True,
    )

    assert first["changed"] is True
    assert first["artifact_action"] == "created"
    assert len(api.configuration_mutations) == len(config.policies) + len(config.roles)
    expected_mutations = {("PUT", f"/v1/sys/policies/acl/{name}") for name in config.policies} | {
        ("POST", f"/v1/auth/approle/role/{name}") for name in config.roles
    }
    assert set(api.configuration_mutations) == expected_mutations
    assert all("*" not in path and "+" not in path for _, path in api.configuration_mutations)
    artifact_path = tmp_path / MODULE.ARTIFACT_FILENAME
    artifact_before = artifact_path.read_bytes()
    assert stat.S_IMODE(artifact_path.stat().st_mode) == 0o600
    receipt_path = tmp_path / MODULE.RECEIPT_FILENAME
    receipt_text = receipt_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert "generated-secret" not in receipt_text
    assert "role-id-runtime-secret-provisioner" not in receipt_text
    assert "breakglass-password" not in receipt_text
    receipt = json.loads(receipt_text)
    assert receipt["contracts"]["count"] == len(config.contracts)
    assert receipt["provisioner"]["login_verified"] is True
    assert receipt["provisioner"]["deny_capabilities_verified"] is True
    assert receipt["provisioner"]["deny_path_count"] > 0

    api.configuration_mutations.clear()
    second = MODULE.reconcile(
        api,
        config,
        breakglass_password="breakglass-password",
        output_root=tmp_path,
        apply=True,
    )

    assert second["changed"] is False
    assert second["artifact_action"] == "preserved"
    assert api.configuration_mutations == []
    assert artifact_path.read_bytes() == artifact_before


def test_approle_payload_omits_creation_only_local_secret_ids() -> None:
    desired = MODULE.DesiredRole(name="service-runtime", policy_name="service-runtime")

    assert desired.local_secret_ids is False
    assert "local_secret_ids" not in desired.api_payload


def test_apply_repairs_mutable_hostile_approle_security_fields(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)
    api.seed_desired_remote_state()
    desired = config.roles[MODULE.PROVISIONER_ROLE_NAME]
    hostile = dict(desired.api_payload)
    hostile.update(
        {
            "bind_secret_id": False,
            "token_period": "30s",
            "token_explicit_max_ttl": "24h",
            "token_type": "batch",
            "token_no_default_policy": True,
            "token_bound_cidrs": ["0.0.0.0/0"],
            "secret_id_bound_cidrs": ["0.0.0.0/0"],
        }
    )
    api.roles[MODULE.PROVISIONER_ROLE_NAME] = hostile
    api.add_provisioner_credential(role_id="existing-role-id", secret_id="existing-secret-id")
    _write_artifact(
        tmp_path / MODULE.ARTIFACT_FILENAME,
        role_id="existing-role-id",
        secret_id="existing-secret-id",
    )

    result = MODULE.reconcile(
        api,
        config,
        breakglass_password="breakglass-password",
        output_root=tmp_path,
        apply=True,
    )

    assert result["changed"] is True
    assert api.roles[MODULE.PROVISIONER_ROLE_NAME] == {
        **desired.api_payload,
        "local_secret_ids": desired.local_secret_ids,
    }
    assert ("POST", f"/v1/auth/approle/role/{MODULE.PROVISIONER_ROLE_NAME}") in api.configuration_mutations


def test_apply_refuses_unrepairable_local_secret_ids_drift(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)
    api.seed_desired_remote_state()
    api.roles[MODULE.PROVISIONER_ROLE_NAME]["local_secret_ids"] = True
    api.add_provisioner_credential(role_id="existing-role-id", secret_id="existing-secret-id")
    _write_artifact(
        tmp_path / MODULE.ARTIFACT_FILENAME,
        role_id="existing-role-id",
        secret_id="existing-secret-id",
    )

    with pytest.raises(MODULE.BootstrapError, match="did not retain the complete bounded policy/AppRole plan"):
        MODULE.reconcile(
            api,
            config,
            breakglass_password="breakglass-password",
            output_root=tmp_path,
            apply=True,
        )

    assert api.roles[MODULE.PROVISIONER_ROLE_NAME]["local_secret_ids"] is True


def test_check_mode_is_read_only_and_reports_no_change_evidence(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)
    api.seed_desired_remote_state()
    api.add_provisioner_credential(role_id="existing-role-id", secret_id="existing-secret-id")
    _write_artifact(
        tmp_path / MODULE.ARTIFACT_FILENAME,
        role_id="existing-role-id",
        secret_id="existing-secret-id",
    )

    result = MODULE.reconcile(
        api,
        config,
        breakglass_password="breakglass-password",
        output_root=tmp_path,
        apply=False,
    )

    assert result["status"] == "ok"
    assert result["converged"] is True
    assert result["changed"] is False
    assert result["receipt_emitted"] is False
    assert api.configuration_mutations == []
    assert not (tmp_path / MODULE.RECEIPT_FILENAME).exists()


def test_check_mode_does_not_create_a_missing_output_directory(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)
    missing = tmp_path / "missing-openbao-output"

    with pytest.raises(MODULE.BootstrapError, match="output directory is missing"):
        MODULE.reconcile(
            api,
            config,
            breakglass_password="breakglass-password",
            output_root=missing,
            apply=False,
        )

    assert not missing.exists()
    assert api.requests == []


def test_breakglass_capability_failure_happens_before_remote_mutation(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)
    api.admin_capabilities = ["read"]

    with pytest.raises(MODULE.BootstrapError, match="lacks a required bounded management capability"):
        MODULE.reconcile(
            api,
            config,
            breakglass_password="breakglass-password",
            output_root=tmp_path,
            apply=True,
        )

    assert api.configuration_mutations == []
    assert not (tmp_path / MODULE.ARTIFACT_FILENAME).exists()
    assert not (tmp_path / MODULE.RECEIPT_FILENAME).exists()


def test_foreign_artifact_fails_before_any_api_or_remote_mutation(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)
    _write_artifact(
        tmp_path / MODULE.ARTIFACT_FILENAME,
        role_id="foreign-role-id",
        secret_id="foreign-secret-id",
        role_name="controller-automation",
    )

    with pytest.raises(MODULE.BootstrapError, match="different identity"):
        MODULE.reconcile(
            api,
            config,
            breakglass_password="breakglass-password",
            output_root=tmp_path,
            apply=True,
        )

    assert api.requests == []
    assert api.configuration_mutations == []


def test_overbroad_provisioner_capability_blocks_artifact_and_receipt(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)
    _, denied = MODULE._provisioner_capability_expectations(config)
    api.provisioner_capabilities[denied[0]] = ["read"]

    with pytest.raises(MODULE.BootstrapError, match="outside its bounded contract"):
        MODULE.reconcile(
            api,
            config,
            breakglass_password="breakglass-password",
            output_root=tmp_path,
            apply=True,
        )

    assert not (tmp_path / MODULE.ARTIFACT_FILENAME).exists()
    assert not (tmp_path / MODULE.RECEIPT_FILENAME).exists()


def test_stale_designated_artifact_is_replaced_atomically_after_verification(tmp_path: Path) -> None:
    config = configuration()
    api = FakeAPI(config)
    artifact_path = tmp_path / MODULE.ARTIFACT_FILENAME
    _write_sensitive(artifact_path, "not-json\n")

    result = MODULE.reconcile(
        api,
        config,
        breakglass_password="breakglass-password",
        output_root=tmp_path,
        apply=True,
    )

    assert result["artifact_action"] == "refreshed"
    assert stat.S_IMODE(artifact_path.stat().st_mode) == 0o600
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["role_name"] == MODULE.PROVISIONER_ROLE_NAME
    assert artifact["auth_path"] == "approle"
    assert (tmp_path / MODULE.RECEIPT_FILENAME).exists()


def test_failed_remote_apply_invalidates_prior_success_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = configuration()
    api = FakeAPI(config)
    receipt_path = tmp_path / MODULE.RECEIPT_FILENAME
    _write_sensitive(receipt_path, '{"status":"previous-success"}\n')

    def fail_apply(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise MODULE.BootstrapError("simulated bounded apply failure")

    monkeypatch.setattr(MODULE, "_apply_remote_plan", fail_apply)

    with pytest.raises(MODULE.BootstrapError, match="simulated bounded apply failure"):
        MODULE.reconcile(
            api,
            config,
            breakglass_password="breakglass-password",
            output_root=tmp_path,
            apply=True,
        )

    assert not receipt_path.exists()
    superseded = list(tmp_path.glob(f".{MODULE.RECEIPT_FILENAME}.superseded-*"))
    assert len(superseded) == 1
    assert "previous-success" in superseded[0].read_text(encoding="utf-8")


def test_minted_credential_is_revoked_when_local_persistence_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = configuration()
    api = FakeAPI(config)
    api.seed_desired_remote_state()
    receipt_path = tmp_path / MODULE.RECEIPT_FILENAME
    _write_sensitive(receipt_path, '{"status":"previous-success"}\n')

    def fail_sensitive_write(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise MODULE.BootstrapError("simulated local persistence failure")

    monkeypatch.setattr(MODULE, "_atomic_sensitive_write", fail_sensitive_write)

    with pytest.raises(MODULE.BootstrapError, match="simulated local persistence failure"):
        MODULE.reconcile(
            api,
            config,
            breakglass_password="breakglass-password",
            output_root=tmp_path,
            apply=True,
        )

    assert api.revoked_accessors == ["accessor-1"]
    assert not (tmp_path / MODULE.ARTIFACT_FILENAME).exists()
    assert not receipt_path.exists()
    assert len(list(tmp_path.glob(f".{MODULE.RECEIPT_FILENAME}.superseded-*"))) == 1


def test_artifact_replace_detects_race_and_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / MODULE.ARTIFACT_FILENAME
    _write_sensitive(path, "original\n")
    snapshot, _ = MODULE._read_file_snapshot(path)

    def competing_writer() -> None:
        _write_sensitive(path, "competitor\n")

    with pytest.raises(MODULE.BootstrapError, match="changed concurrently"):
        MODULE._atomic_sensitive_write(
            path,
            b"replacement\n",
            expected_snapshot=snapshot,
            before_replace=competing_writer,
        )

    assert path.read_text(encoding="utf-8") == "competitor\n"


def test_artifact_create_detects_race_and_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / MODULE.ARTIFACT_FILENAME
    snapshot, _ = MODULE._read_file_snapshot(path)

    def competing_creator() -> None:
        _write_sensitive(path, "competitor\n")

    with pytest.raises(MODULE.BootstrapError, match="changed concurrently"):
        MODULE._atomic_sensitive_write(
            path,
            b"replacement\n",
            expected_snapshot=snapshot,
            before_replace=competing_creator,
        )

    assert path.read_text(encoding="utf-8") == "competitor\n"


def test_http_errors_discard_secret_bearing_response_bodies(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "server-returned-secret-material"

    def fail_open(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8201/v1/test",
            403,
            "Forbidden",
            {},
            io.BytesIO(json.dumps({"errors": [secret]}).encode("utf-8")),
        )

    api = MODULE.HTTPOpenBaoAPI("http://127.0.0.1:8201")
    monkeypatch.setattr(api.opener, "open", fail_open)

    with pytest.raises(MODULE.BootstrapError) as error:
        api.request("POST", "/v1/test", payload={"password": "local-secret"})

    assert secret not in str(error.value)
    assert "local-secret" not in str(error.value)


def test_http_client_rejects_redirects_before_token_can_change_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = MODULE.HTTPOpenBaoAPI("http://127.0.0.1:8201")
    assert any(isinstance(handler, MODULE.NoRedirectHandler) for handler in api.opener.handlers)
    calls: list[str] = []

    def redirect_once(request: Any, **kwargs: Any) -> Any:
        del kwargs
        calls.append(request.full_url)
        raise urllib.error.HTTPError(
            request.full_url,
            302,
            "Found",
            {"Location": "https://attacker.invalid/collect"},
            io.BytesIO(b""),
        )

    monkeypatch.setattr(api.opener, "open", redirect_once)

    with pytest.raises(MODULE.BootstrapError, match="returned HTTP 302") as error:
        api.request("GET", "/v1/test", token="sensitive-token")

    assert calls == ["http://127.0.0.1:8201/v1/test"]
    assert "attacker.invalid" not in str(error.value)
    assert "sensitive-token" not in str(error.value)


def test_sensitive_file_reader_rejects_non_0600_password_file(tmp_path: Path) -> None:
    password_file = tmp_path / "breakglass-password.txt"
    password_file.write_text("secret-password\n", encoding="utf-8")
    password_file.chmod(0o644)

    with pytest.raises(MODULE.BootstrapError, match="mode 0600"):
        MODULE._read_breakglass_password(password_file)


def test_cli_paths_are_bound_to_the_shared_controller_local_openbao_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_local = tmp_path / ".local"
    monkeypatch.setattr(MODULE, "local_overlay_root", lambda _repo_root: shared_local)
    output_root = shared_local / "openbao"
    password_file = output_root / "breakglass-password.txt"

    selected_output, selected_password = MODULE._validate_controller_paths(output_root, password_file)

    assert selected_output == output_root.resolve()
    assert selected_password == password_file.resolve()
    with pytest.raises(MODULE.BootstrapError, match="shared controller-local"):
        MODULE._validate_controller_paths(tmp_path / "other", password_file)
    with pytest.raises(MODULE.BootstrapError, match="governed controller-local"):
        MODULE._validate_controller_paths(output_root, tmp_path / "other-password.txt")


def test_ssh_tunnel_command_uses_only_selector_derived_hosts_and_loopback_forward() -> None:
    config = configuration()
    key_file = Path("/tmp/operator key")

    command = MODULE._build_ssh_tunnel_command(config, key_file, local_port=18201)

    assert command[0] == "/usr/bin/ssh"
    assert command[-1] == "ops@10.10.10.92"
    assert command[command.index("-L") + 1] == "127.0.0.1:18201:127.0.0.1:8201"
    proxy_option = next(item for item in command if item.startswith("ProxyCommand="))
    assert "ops@192.0.2.10" in proxy_option
    assert "StrictHostKeyChecking=yes" in proxy_option
    assert "operator key" in proxy_option
    assert config.api_url not in " ".join(command)
    assert "shell=" not in " ".join(command)


def test_ssh_private_key_rejects_symlink_and_insecure_mode(tmp_path: Path) -> None:
    key_file = tmp_path / "bootstrap.id_ed25519"
    _write_sensitive(key_file, "private-key-material\n")
    assert MODULE._validate_ssh_private_key(key_file) == key_file

    symlink = tmp_path / "bootstrap-link"
    symlink.symlink_to(key_file)
    with pytest.raises(MODULE.BootstrapError, match="regular operator-owned mode-0600"):
        MODULE._validate_ssh_private_key(symlink)

    key_file.chmod(0o644)
    with pytest.raises(MODULE.BootstrapError, match="regular operator-owned mode-0600"):
        MODULE._validate_ssh_private_key(key_file)


def test_ssh_tunnel_is_cleaned_up_after_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_file = tmp_path / "bootstrap.id_ed25519"
    _write_sensitive(key_file, "private-key-material\n")
    processes: list[Any] = []

    class FakeProcess:
        def __init__(self) -> None:
            self.running = True
            self.terminated = False
            self.killed = False

        def poll(self) -> int | None:
            return None if self.running else 0

        def terminate(self) -> None:
            self.terminated = True
            self.running = False

        def wait(self, *, timeout: float) -> int:
            assert timeout == MODULE.SSH_TUNNEL_STOP_TIMEOUT_SECONDS
            self.running = False
            return 0

        def kill(self) -> None:
            self.killed = True
            self.running = False

    def fake_popen(command: list[str], **kwargs: Any) -> FakeProcess:
        assert command[0] == MODULE.SSH_BINARY
        assert kwargs.get("shell") is None
        process = FakeProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(MODULE, "_reserve_loopback_port", lambda: 18201)
    monkeypatch.setattr(MODULE.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(MODULE, "_wait_for_ssh_tunnel", lambda _process, _port: None)

    with MODULE._open_ssh_tunnel(configuration(), key_file) as tunnel_url:
        assert tunnel_url == "http://127.0.0.1:18201"

    assert processes[0].terminated is True
    assert processes[0].killed is False

    def fail_wait(_process: Any, _port: int) -> None:
        raise MODULE.BootstrapError("simulated tunnel failure")

    monkeypatch.setattr(MODULE, "_wait_for_ssh_tunnel", fail_wait)
    with (
        pytest.raises(MODULE.BootstrapError, match="simulated tunnel failure"),
        MODULE._open_ssh_tunnel(configuration(), key_file),
    ):
        raise AssertionError("the failed tunnel must not yield")

    assert processes[1].terminated is True
    assert processes[1].killed is False
