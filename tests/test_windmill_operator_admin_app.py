from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windmill_defaults_seed_operator_admin_scripts_and_app() -> None:
    defaults_text = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml"
    ).read_text()
    defaults = yaml.safe_load(
        defaults_text
    )

    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    raw_app_paths = {entry["path"] for entry in defaults["windmill_seed_raw_apps"]}

    assert {
        "f/lv3/operator_onboard",
        "f/lv3/operator_offboard",
        "f/lv3/sync_operators",
        "f/lv3/quarterly_access_review",
        "f/lv3/operator_roster",
        "f/lv3/operator_inventory",
    }.issubset(script_paths)
    assert "f/lv3/operator_access_admin" in raw_app_paths
    assert defaults["windmill_bootstrap_identity_email"] == "superadmin_secret@windmill.dev"
    assert defaults["windmill_bootstrap_identity_username"] == "superadmin_secret"
    assert defaults["windmill_bootstrap_identity_login_type"] == "password"
    assert defaults["windmill_service_topology"] == (
        "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('windmill') }}"
    )
    assert defaults["windmill_server_port"] == "{{ hostvars['proxmox_florin'].platform_port_assignments.windmill_server_port }}"
    assert defaults["windmill_host_proxy_port"] == "{{ hostvars['proxmox_florin'].platform_port_assignments.windmill_host_proxy_port }}"
    assert defaults["windmill_private_base_url"] == "http://{{ windmill_service_topology.private_ip }}:{{ windmill_server_port }}"
    assert defaults["windmill_base_url"] == "http://{{ hostvars['proxmox_florin'].management_tailscale_ipv4 }}:{{ windmill_host_proxy_port }}"
    assert defaults["windmill_healthcheck_script_path"] == "f/lv3/windmill_healthcheck"
    assert defaults["windmill_validation_gate_status_script_path"] == "f/lv3/gate-status"
    assert "inventory_dir" in defaults["windmill_worker_checkout_repo_root_local_dir"]
    assert "playbook_dir" in defaults["windmill_worker_checkout_repo_root_local_dir"]
    assert defaults["windmill_worker_checkout_integrity_files"] == [
        "Makefile",
        "scripts/policy_checks.py",
        "scripts/policy_toolchain.py",
        "scripts/command_catalog.py",
        "scripts/gate_status.py",
        "config/windmill/scripts/gate-status.py",
    ]
    assert {
        "README.md",
        "VERSION",
        "ansible.cfg",
        "callback_plugins",
        "changelog.md",
        "collections",
        "config",
        "docs",
        "filter_plugins",
        "inventory",
        "Makefile",
        "mkdocs.yml",
        "migrations",
        "playbooks",
        "policy",
        "platform",
        "pytest.ini",
        "receipts",
        "requirements",
        "scripts",
        "versions",
        "windmill",
        "workstreams.yaml",
        "roles",
    }.issubset(set(defaults["windmill_worker_checkout_sync_paths"]))
    assert defaults["windmill_worker_checkout_checksum_file"] == "{{ windmill_site_dir }}/worker-checkout.sha256"
    assert defaults["windmill_worker_checkout_manifest_remote_file"] == "{{ windmill_site_dir }}/worker-checkout-files.txt"
    assert "windmill_worker_checkout_prune_preserve_paths" in defaults_text
    assert "windmill_worker_repo_mutable_files" in defaults_text
    assert "windmill_worker_runtime_writable_directories" in defaults_text
    assert "windmill_worker_repo_secret_directories" in defaults_text
    assert "windmill_worker_repo_secret_files" in defaults_text
    assert "windmill_worker_proxmox_api_token_payload_dir" in defaults_text
    assert "windmill_worker_superadmin_secret_file" in defaults_text
    assert defaults["windmill_worker_superadmin_secret_dir"] == "{{ windmill_worker_repo_checkout_host_path }}/.local/windmill"
    assert defaults["windmill_worker_superadmin_secret_file"] == "{{ windmill_worker_superadmin_secret_dir }}/superadmin-secret.txt"
    assert defaults["windmill_runtime_api_base_url"] == "http://127.0.0.1:{{ windmill_server_port }}"
    assert defaults["windmill_worker_api_base_url"] == "http://windmill_server:8000"
    assert defaults["windmill_seed_job_timeout_seconds"] == 120
    mutable_directories = {frozenset(item.items()) for item in defaults["windmill_worker_repo_mutable_directories"]}
    assert {
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/state", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/state/operator-access", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/state/idempotency", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/state/execution-lanes", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/scheduler", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/fault-injection", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/network-impairment-matrix", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/integration-tests", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/governed-command/logs", "mode": "0777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/governed-command/receipts", "mode": "0777"}.items()),
    }.issubset(mutable_directories)
    mutable_files = {frozenset(item.items()) for item in defaults["windmill_worker_repo_mutable_files"]}
    assert {
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/config/operators.yaml", "mode": "0666"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/state/execution-lanes/registry.json", "mode": "0666"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/state/execution-lanes/registry.lock", "mode": "0666"}.items()),
    }.issubset(mutable_files)
    assert defaults["windmill_worker_repo_secret_directories"] == [
        {"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/keycloak", "mode": "0700"},
        {"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/openbao", "mode": "0700"},
    ]
    assert defaults["windmill_worker_repo_secret_files"][0]["path"] == (
        "{{ windmill_worker_repo_checkout_host_path }}/.local/keycloak/bootstrap-admin-password.txt"
    )
    assert defaults["windmill_worker_repo_secret_files"][1]["path"] == (
        "{{ windmill_worker_repo_checkout_host_path }}/.local/openbao/init.json"
    )
    assert defaults["windmill_operator_manager_env"]["LV3_OPERATOR_MANAGER_SURFACE"] == "windmill"
    assert defaults["windmill_openbao_runtime_network"] == "openbao_default"
    assert defaults["windmill_operator_manager_env"]["LV3_OPENBAO_URL"] == "http://lv3-openbao:8201"
    assert "KEYCLOAK_BOOTSTRAP_PASSWORD" in defaults["windmill_operator_manager_env"]
    assert "OPENBAO_INIT_JSON" in defaults["windmill_operator_manager_env"]
    assert {
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/receipts/fixtures", "mode": "1777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local", "mode": "0755"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures", "mode": "1777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures/reaper-runs", "mode": "1777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures/runtime", "mode": "1777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures/archive", "mode": "1777"}.items()),
        frozenset({"path": "{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures/locks", "mode": "1777"}.items()),
    } == {frozenset(item.items()) for item in defaults["windmill_worker_runtime_writable_directories"]}
    weekly_schedule = next(entry for entry in defaults["windmill_seed_schedules"] if entry["path"] == "f/lv3/build_cache_maintenance_weekly")
    assert weekly_schedule["schedule"] == "0 0 4 * * 7"
    quarterly_schedule = next(
        entry for entry in defaults["windmill_seed_schedules"] if entry["path"] == "f/lv3/quarterly_access_review_every_monday_0900"
    )
    assert quarterly_schedule["schedule"] == "0 0 9 * * 1"
    assert quarterly_schedule["timezone"] == "Europe/Bucharest"
    assert quarterly_schedule["args"]["schedule_guard"] == "first_monday_of_quarter"


def test_operator_admin_raw_app_bundle_references_expected_backend_scripts() -> None:
    app_dir = REPO_ROOT / "config/windmill/apps/f/lv3/operator_access_admin.raw_app"
    app_config = yaml.safe_load((app_dir / "raw_app.yaml").read_text())
    package = json.loads((app_dir / "package.json").read_text())
    app_source = (app_dir / "App.tsx").read_text()

    assert app_config["summary"] == "LV3 operator access admin console"
    assert package["dependencies"]["react"] == "19.0.0"
    assert package["dependencies"]["windmill-client"] == "^1"
    assert "Operator Access Admin" in app_source
    assert "isRosterPayload" in app_source
    assert "candidate.status === \"ok\" && Array.isArray(candidate.operators)" in app_source
    assert "extractRosterError" in app_source
    roster_script = (REPO_ROOT / "config/windmill/scripts/operator-roster.py").read_text()
    onboard_script = (REPO_ROOT / "config/windmill/scripts/operator-onboard.py").read_text()
    offboard_script = (REPO_ROOT / "config/windmill/scripts/operator-offboard.py").read_text()
    sync_script = (REPO_ROOT / "config/windmill/scripts/sync-operators.py").read_text()
    inventory_script = (REPO_ROOT / "config/windmill/scripts/operator-inventory.py").read_text()
    for script_source in (roster_script, onboard_script, offboard_script, sync_script, inventory_script):
        assert "\"uv\"" in script_source
        assert "\"run\"" in script_source
        assert "\"--no-project\"" in script_source
        assert "\"pyyaml\"" in script_source
        assert "\"PYTHONPATH\"" in script_source
    assert "backend.create_operator" in app_source
    assert "backend.offboard_operator" in app_source
    assert "backend.sync_operators" in app_source
    assert "backend.operator_inventory" in app_source

    expected_backend_refs = {
        "list_operators.yaml": "f/lv3/operator_roster",
        "create_operator.yaml": "f/lv3/operator_onboard",
        "offboard_operator.yaml": "f/lv3/operator_offboard",
        "sync_operators.yaml": "f/lv3/sync_operators",
        "operator_inventory.yaml": "f/lv3/operator_inventory",
    }
    for file_name, expected_path in expected_backend_refs.items():
        payload = yaml.safe_load((app_dir / "backend" / file_name).read_text())
        assert payload["type"] == "script"
        assert payload["path"] == expected_path


def test_operator_roster_script_returns_sanitized_roster(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    roster_path = repo_root / "config" / "operators.yaml"
    roster_path.parent.mkdir(parents=True)
    roster_path.write_text(
        yaml.safe_dump(
            {
                "operators": [
                    {
                        "id": "alice-example",
                        "name": "Alice Example",
                        "email": "alice@example.com",
                        "role": "admin",
                        "status": "active",
                        "notes": "primary operator",
                        "keycloak": {
                            "username": "alice.example",
                            "realm_roles": ["platform-admin"],
                            "groups": ["lv3-platform-admins"],
                        },
                        "ssh": {"public_keys": [{"name": "bootstrap", "fingerprint": "SHA256:test"}]},
                        "tailscale": {"login_email": "alice@example.com"},
                        "audit": {"onboarded_at": "2026-03-24T12:00:00Z"},
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    module = load_module(REPO_ROOT / "config/windmill/scripts/operator-roster.py", "operator_roster")
    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["operator_count"] == 1
    assert payload["active_count"] == 1
    assert payload["inactive_count"] == 0
    assert payload["operators"][0]["keycloak_username"] == "alice.example"
    assert payload["operators"][0]["ssh_enabled"] is True
    assert "public_keys" not in payload["operators"][0]


def test_operator_inventory_script_requires_operator_id() -> None:
    module = load_module(REPO_ROOT / "config/windmill/scripts/operator-inventory.py", "operator_inventory")
    payload = module.main(operator_id="")

    assert payload["status"] == "blocked"
    assert payload["reason"] == "operator_id is required"


def test_quarterly_access_review_script_supports_guard() -> None:
    module = load_module(REPO_ROOT / "config/windmill/scripts/quarterly-access-review.py", "quarterly_access_review")
    module._is_first_monday_of_quarter = lambda now=None: False

    payload = module.main(repo_path=str(REPO_ROOT), schedule_guard="first_monday_of_quarter")

    assert payload["status"] == "skipped"
    assert payload["schedule_guard"] == "first_monday_of_quarter"


def test_operator_onboard_wrapper_passes_emit_json_before_subcommand(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    workflow = repo_root / "scripts" / "operator_manager.py"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("# stub\n", encoding="utf-8")
    module = load_module(REPO_ROOT / "config/windmill/scripts/operator-onboard.py", "operator_onboard_wrapper")
    captured = {}

    def fake_run(command, cwd, env, text, capture_output, check):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"status": "ok"}), stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(name="Alice Example", email="alice@example.com", role="viewer", repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert captured["command"][:9] == [
        "uv",
        "run",
        "--no-project",
        "--with",
        "pyyaml",
        "python",
        str(workflow),
        "--emit-json",
        "onboard",
    ]


def test_operator_onboard_wrapper_reads_runtime_env_fallback(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    workflow = repo_root / "scripts" / "operator_manager.py"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("# stub\n", encoding="utf-8")
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text(
        "LV3_OPENBAO_URL=http://127.0.0.1:8201\nKEYCLOAK_BOOTSTRAP_PASSWORD=test-bootstrap\nOPENBAO_INIT_JSON={'root_token':'test'}\nIGNORED=value\n",
        encoding="utf-8",
    )
    module = load_module(REPO_ROOT / "config/windmill/scripts/operator-onboard.py", "operator_onboard_wrapper_runtime_env")
    monkeypatch.setattr(module, "RUNTIME_ENV_FILE", runtime_env)
    captured = {}

    def fake_run(command, cwd, env, text, capture_output, check):
        captured["env"] = env
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"status": "ok"}), stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(name="Alice Example", email="alice@example.com", role="viewer", repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert captured["env"]["LV3_OPENBAO_URL"] == "http://127.0.0.1:8201"
    assert captured["env"]["KEYCLOAK_BOOTSTRAP_PASSWORD"] == "test-bootstrap"
    assert captured["env"]["OPENBAO_INIT_JSON"] == "{'root_token':'test'}"
    assert "IGNORED" not in captured["env"]


def test_operator_onboard_wrapper_sets_openbao_url_without_runtime_env(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    workflow = repo_root / "scripts" / "operator_manager.py"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("# stub\n", encoding="utf-8")
    module = load_module(REPO_ROOT / "config/windmill/scripts/operator-onboard.py", "operator_onboard_wrapper_default_env")

    env = module.build_subprocess_env(repo_root)

    assert env["LV3_OPENBAO_URL"] == "http://lv3-openbao:8201"


def test_windmill_runtime_tasks_sync_raw_apps_via_wmill_cli() -> None:
    tasks = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml"
    ).read_text()
    verify_tasks = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml"
    ).read_text()
    compose_template = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/docker-compose.yml.j2"
    ).read_text()
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )

    assert "Ensure the Windmill bootstrap workspace identity is consistent" in tasks
    assert "INSERT INTO password" in tasks
    assert "Ensure the Windmill bootstrap workspace user is consistent" in tasks
    assert "INSERT INTO usr" in tasks
    assert "INSERT INTO usr_to_group" in tasks
    assert "Authenticate the Windmill bootstrap admin session" in tasks
    assert "/api/auth/login" in tasks
    assert "windmill_bootstrap_session_token" in tasks
    assert "Ensure the Windmill bootstrap admin login type matches the managed contract" in tasks
    assert "/api/users/set_login_type/" in tasks
    assert "Ensure the Windmill bootstrap admin password matches the managed secret" in tasks
    assert "/api/users/set_password_of/" in tasks
    assert 'Authorization: "Bearer {{ windmill_bootstrap_session_token }}"' in tasks
    assert "Sync repo-managed Windmill scripts" in tasks
    assert "scripts/sync_windmill_seed_scripts.py" in tasks
    assert "WINDMILL_TOKEN" in tasks
    assert "Sync repo-managed Windmill schedules" in tasks
    assert "scripts/sync_windmill_seed_schedules.py" in tasks
    assert "--path {{ windmill_healthcheck_script_path | quote }}" in tasks
    assert '$1 == "DATABASE_URL"' in tasks
    assert '. "{{ windmill_env_file }}"' not in tasks
    assert "Converge repo-managed Windmill schedule enabled flags" in tasks
    assert 'psql "${database_url}"' in tasks
    assert "become: true" in tasks
    assert "Sync repo-managed Windmill raw apps" in tasks
    assert "wmill sync push" in tasks
    assert "--skip-scripts" in tasks
    assert "--includes \"{{ item.sync_pattern }}\"" in tasks
    assert "--skip-branch-validation" in tasks
    assert "WM_TOKEN" in tasks
    assert 'WM_TOKEN: "{{ windmill_bootstrap_session_token }}"' in tasks
    assert "BASE_INTERNAL_URL" in tasks
    assert "windmill_runtime_api_base_url" in tasks
    assert "Build the local staging archive for the Windmill worker checkout" in tasks
    assert "COPYFILE_DISABLE=1" in tasks
    assert "COPY_EXTENDED_ATTRIBUTES_DISABLE=1" in tasks
    assert "--exclude='._*'" in tasks
    assert "--exclude='*/._*'" in tasks
    assert "--exclude='.DS_Store'" in tasks
    assert "--exclude='*/.DS_Store'" in tasks
    assert "changed_when: false" in tasks
    assert "Expand the staged Windmill worker checkout on the guest" in tasks
    assert "Find stale macOS metadata files in the Windmill worker checkout" in tasks
    assert "Remove stale macOS metadata files from the Windmill worker checkout" in tasks
    assert "Find stale Python bytecode files in the Windmill worker checkout" in tasks
    assert "Remove stale Python bytecode files from the Windmill worker checkout" in tasks
    assert "Find stale Python bytecode cache directories in the Windmill worker checkout" in tasks
    assert "Remove stale Python bytecode cache directories from the Windmill worker checkout" in tasks
    assert ".DS_Store" in tasks
    assert "._*" in tasks
    assert "__pycache__" in tasks
    assert "*.pyc" in tasks
    assert "-delete" in tasks
    assert "-exec rm -rf {} +" in tasks
    assert '{{ windmill_worker_repo_checkout_host_path }}/scripts' in tasks
    assert '{{ windmill_worker_repo_checkout_host_path }}/platform' in tasks
    assert "Ensure repo-backed Windmill runtime paths stay writable after checkout sync" in tasks
    assert "Ensure the Windmill worker checkout mutable directories exist with write access" in tasks
    assert "Ensure the Windmill worker checkout mutable files remain writable for Windmill jobs" in tasks
    assert "Ensure the Windmill worker checkout secret directories exist" in tasks
    assert "Mirror the Windmill worker checkout bootstrap secret files" in tasks
    assert "windmill_worker_repo_mutable_directories" in tasks
    assert "windmill_worker_repo_mutable_files" in tasks
    assert "windmill_worker_repo_secret_directories" in tasks
    assert "windmill_worker_repo_secret_files" in tasks
    assert "Ensure the worker checkout secret directory exists" in tasks
    assert "Mirror the Windmill superadmin secret into the worker checkout" in tasks
    assert "windmill_worker_superadmin_secret_dir" in tasks
    assert "windmill_worker_superadmin_secret_file" in tasks
    assert "windmill_worker_checkout_repo_root_local_dir" in tasks
    assert "windmill_worker_checkout_checksum_file" in tasks
    assert "windmill_worker_checkout_integrity_files" in tasks
    assert "Collect controller-side integrity checksums for Windmill worker checkout sentinels" in tasks
    assert "Collect guest-side integrity checksums for Windmill worker checkout sentinels" in tasks
    assert "Flag the Windmill worker checkout for refresh when integrity sentinels drift" in tasks
    assert "windmill_worker_checkout_integrity_mismatch" in tasks
    assert "windmill_worker_checkout_sync_paths" in tasks
    assert "Create a local manifest path for the Windmill worker checkout contents" in tasks
    assert "Render the local manifest for the Windmill worker checkout contents" in tasks
    assert "Copy the staged Windmill worker checkout manifest to the guest" in tasks
    assert "Prune stale immutable files from the Windmill worker checkout" in tasks
    assert "Removed stale immutable files from the Windmill worker checkout" in tasks
    assert "Remove the remote manifest for the Windmill worker checkout contents" in tasks
    assert "Remove the local manifest for the Windmill worker checkout contents" in tasks
    assert "windmill_worker_checkout_manifest_remote_file" in tasks
    assert "windmill_worker_checkout_prune_preserve_paths" in tasks
    assert "scripts/windmill_run_wait_result.py" in tasks
    assert "--payload-json" in tasks
    assert "--timeout {{ windmill_seed_job_timeout_seconds }}" in tasks
    assert "--path {{ windmill_validation_gate_status_script_path | quote }}" in verify_tasks
    assert "Run the Windmill validation gate status script" in verify_tasks
    assert "Assert the Windmill validation gate status result" in verify_tasks
    assert "delegate_to: localhost" in tasks
    assert "become: false" in tasks
    assert "Decide whether the Windmill worker checkout needs to be refreshed" in tasks
    assert "windmill_worker_checkout_checksum_file" in tasks
    assert "windmill_worker_checkout_repo_root_local_dir" in tasks
    assert "windmill_worker_checkout_sync_paths" in tasks
    assert defaults["windmill_worker_repo_checkout_host_path"] == "/srv/proxmox_florin_server"
    assert defaults["windmill_worker_repo_checkout_container_path"] == "/srv/proxmox_florin_server"
    assert "{{ windmill_worker_repo_checkout_host_path }}:{{ windmill_worker_repo_checkout_container_path }}" in compose_template
    assert "openbao_runtime" in compose_template
    assert "name: {{ windmill_openbao_runtime_network }}" in compose_template
    assert compose_template.count('user: "0:0"') >= 3
    runtime_template = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/windmill-runtime.env.j2"
    ).read_text()
    runtime_ctmpl_template = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/windmill-runtime.env.ctmpl.j2"
    ).read_text()
    assert "TF_VAR_proxmox_endpoint" in runtime_template
    assert "TF_VAR_proxmox_api_token" in runtime_template
    assert "LV3_WINDMILL_TOKEN={{ windmill_superadmin_secret }}" in runtime_template
    assert "{% for item in windmill_operator_manager_env" in runtime_template
    assert "TF_VAR_proxmox_endpoint" in runtime_ctmpl_template
    assert "TF_VAR_proxmox_api_token" in runtime_ctmpl_template
    assert 'LV3_WINDMILL_TOKEN=[[ with secret "kv/data/{{ windmill_openbao_secret_path }}" ]][[ .Data.data.LV3_WINDMILL_TOKEN ]][[ end ]]' in runtime_ctmpl_template
    assert "{% for item in windmill_operator_manager_env" in runtime_ctmpl_template
