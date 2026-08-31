import os
import shutil
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "roles" / "authentik_runtime"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
OAUTH_TASKS_PATH = ROLE_ROOT / "tasks" / "oauth_clients.yml"
VERIFY_PATH = ROLE_ROOT / "tasks" / "verify.yml"
META_PATH = ROLE_ROOT / "meta" / "argument_specs.yml"
COMPOSE_PATH = ROLE_ROOT / "templates" / "docker-compose.yml.j2"
CTMPL_PATH = ROLE_ROOT / "templates" / "runtime.env.ctmpl.j2"
STATIC_ENV_PATH = ROLE_ROOT / "templates" / "runtime.env.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_defaults_are_generic_pinned_and_fail_safe() -> None:
    defaults = load_yaml(DEFAULTS_PATH)

    assert "platform_topology_host" in defaults["authentik_service_topology"]
    assert defaults["authentik_internal_port"] == "{{ platform_service_registry.authentik.internal_port }}"
    assert defaults["authentik_container_port"] == 9000
    assert defaults["authentik_legacy_env_file"] == "{{ authentik_site_dir }}/.env"
    assert defaults["authentik_secret_bootstrap_mode"] == "preserve"
    assert defaults["authentik_local_artifact_dir"] == "{{ repo_shared_local_root }}/authentik"
    assert defaults["authentik_bootstrap_email"] == "{{ platform_operator_email }}"
    assert defaults["authentik_private_url"] == "http://127.0.0.1:{{ authentik_internal_port }}"
    assert defaults["authentik_image"] == "{{ container_image_catalog.images.authentik_runtime.ref }}"
    assert "@sha256:" in defaults["authentik_postgres_image"]
    assert "@sha256:" in defaults["authentik_redis_image"]
    assert defaults["authentik_openbao_policy_name"].startswith("{{ platform_identity.config_prefix }}")
    assert defaults["authentik_oauth_reconcile_clients"] == []


def test_secret_adoption_is_allowlisted_and_never_overwrites_drift() -> None:
    tasks = load_yaml(TASKS_PATH)
    names = [task["name"] for task in tasks]
    adoption = next(
        task for task in tasks if task["name"] == "Adopt and verify the allowlisted Authentik legacy secrets"
    )
    script = adoption["ansible.builtin.shell"]

    assert adoption["when"] == "authentik_secret_bootstrap_mode == 'adopt_legacy'"
    assert adoption["no_log"] is True
    assert '"{{ authentik_legacy_env_backup_file }}"' in script
    assert "AUTHENTIK_SECRET_KEY" in script
    assert "AUTHENTIK_POSTGRESQL__PASSWORD" in script
    assert "AUTHENTIK_BOOTSTRAP_TOKEN" in script
    assert "AUTHENTIK_BOOTSTRAP_PASSWORD" in script
    assert 'values.get("POSTGRES_PASSWORD")' in script
    assert "os.O_EXCL" in script
    assert "os.O_NOFOLLOW" in script
    assert "destination.lstat()" in script
    assert "stat.S_ISREG(metadata.st_mode)" in script
    assert "metadata.st_uid != 0 or metadata.st_gid != 0" in script
    assert "destination.read_bytes() != expected" in script
    assert "canonical Authentik secret differs from legacy source" in script
    assert "openssl rand" not in script
    assert script.index("existing_destinations = set()") < script.index("changed = 0")
    assert script.index("canonical Authentik secret differs from legacy source") < script.index("changed = 0")
    assert script.index("changed = 0") < script.index("descriptor = os.open")

    partial = next(task for task in tasks if task["name"] == "Reject partial Authentik secret state in preserve mode")
    assert partial["when"] == "authentik_secret_bootstrap_mode == 'preserve'"
    assert names.index("Require an exact protected Authentik legacy backup before adoption") < names.index(
        "Adopt and verify the allowlisted Authentik legacy secrets"
    )
    assert names.index("Require an exact Authentik compose rollback snapshot before first adoption") < names.index(
        "Adopt and verify the allowlisted Authentik legacy secrets"
    )

    generation = next(
        task for task in tasks if task["name"] == "Generate Authentik secrets only for an explicitly new deployment"
    )
    assert generation["when"] == "authentik_secret_bootstrap_mode == 'generate'"
    assert generation["changed_when"] == ("(authentik_secret_generation.stdout | default('') | trim) == 'changed'")
    assert ".results" not in generation["changed_when"]


def test_legacy_backup_is_exact_regular_root_owned_and_nonempty() -> None:
    tasks = load_yaml(TASKS_PATH)
    names = [task["name"] for task in tasks]
    source_stat = next(task for task in tasks if task["name"] == "Inspect the Authentik legacy environment")
    source_guard = next(
        task for task in tasks if task["name"] == "Require a safe Authentik legacy source before adoption"
    )
    preexisting_stat = next(
        task for task in tasks if task["name"] == "Inspect any pre-existing Authentik legacy environment backup"
    )
    preexisting_guard = next(
        task for task in tasks if task["name"] == "Reject an unsafe pre-existing Authentik legacy environment backup"
    )
    backup = next(
        task for task in tasks if task["name"] == "Preserve the Authentik legacy environment before one-time adoption"
    )
    backup_stat = next(task for task in tasks if task["name"] == "Inspect the preserved Authentik legacy environment")
    backup_guard = next(
        task for task in tasks if task["name"] == "Require an exact protected Authentik legacy backup before adoption"
    )

    assert source_stat["ansible.builtin.stat"]["get_checksum"] is True
    assert source_stat["ansible.builtin.stat"]["checksum_algorithm"] == "sha256"
    assert preexisting_stat["ansible.builtin.stat"]["follow"] is False
    assert preexisting_guard["no_log"] is True
    assert names.index(preexisting_guard["name"]) < names.index(backup["name"])
    assert backup["ansible.builtin.copy"]["force"] is False
    assert backup["ansible.builtin.copy"]["remote_src"] is True
    assert backup_stat["ansible.builtin.stat"]["checksum_algorithm"] == "sha256"
    assert source_guard["no_log"] is True
    assert backup_guard["no_log"] is True

    conditions = backup_guard["ansible.builtin.assert"]["that"]
    assert any("isreg" in condition for condition in conditions)
    assert any("islnk" in condition for condition in conditions)
    assert any("uid" in condition and "== 0" in condition for condition in conditions)
    assert any("gid" in condition and "== 0" in condition for condition in conditions)
    assert any("mode" in condition and "0600" in condition for condition in conditions)
    assert any("size" in condition and "> 0" in condition for condition in conditions)
    assert any("checksum" in condition and "authentik_legacy_env_state" in condition for condition in conditions)


def test_legacy_compose_backup_is_exact_protected_and_precedes_adoption() -> None:
    defaults = load_yaml(DEFAULTS_PATH)
    tasks = load_yaml(TASKS_PATH)
    names = [task["name"] for task in tasks]
    source_stat = next(
        task for task in tasks if task["name"] == "Inspect the current Authentik compose rollback source"
    )
    source_guard = next(
        task for task in tasks if task["name"] == "Require a safe Authentik compose rollback source before adoption"
    )
    preexisting_backup_stat = next(
        task for task in tasks if task["name"] == "Inspect any pre-existing Authentik compose rollback file"
    )
    preexisting_backup_guard = next(
        task for task in tasks if task["name"] == "Reject an unsafe pre-existing Authentik compose rollback file"
    )
    resume_guard = next(
        task
        for task in tasks
        if task["name"] == "Refuse an Authentik adoption resume without its original compose rollback"
    )
    backup = next(
        task for task in tasks if task["name"] == "Preserve the Authentik compose file before one-time adoption"
    )
    backup_stat = next(
        task for task in tasks if task["name"] == "Inspect the preserved Authentik compose rollback file"
    )
    backup_guard = next(
        task for task in tasks if task["name"] == "Require a protected Authentik compose rollback backup"
    )
    exact_guard = next(
        task
        for task in tasks
        if task["name"] == "Require an exact Authentik compose rollback snapshot before first adoption"
    )

    assert defaults["authentik_legacy_compose_backup_file"] == ("{{ authentik_compose_file }}.pre-openbao-adoption")
    assert source_stat["ansible.builtin.stat"]["follow"] is False
    assert source_stat["ansible.builtin.stat"]["get_checksum"] is True
    assert source_stat["ansible.builtin.stat"]["checksum_algorithm"] == "sha256"
    assert backup["ansible.builtin.copy"]["remote_src"] is True
    assert backup["ansible.builtin.copy"]["force"] is False
    assert backup["ansible.builtin.copy"]["owner"] == "root"
    assert backup["ansible.builtin.copy"]["group"] == "root"
    assert backup["ansible.builtin.copy"]["mode"] == "0600"
    assert backup_stat["ansible.builtin.stat"]["follow"] is False
    assert backup_stat["ansible.builtin.stat"]["checksum_algorithm"] == "sha256"
    assert source_guard["no_log"] is True
    assert preexisting_backup_stat["ansible.builtin.stat"]["follow"] is False
    assert preexisting_backup_guard["no_log"] is True
    assert names.index(preexisting_backup_guard["name"]) < names.index(backup["name"])
    assert resume_guard["no_log"] is True
    assert "authentik_current_compose_is_openbao_managed" in resume_guard["when"][1]
    assert backup_guard["no_log"] is True
    assert exact_guard["no_log"] is True

    backup_conditions = backup_guard["ansible.builtin.assert"]["that"]
    assert any("isreg" in condition for condition in backup_conditions)
    assert any("islnk" in condition for condition in backup_conditions)
    assert any("uid" in condition and "== 0" in condition for condition in backup_conditions)
    assert any("gid" in condition and "== 0" in condition for condition in backup_conditions)
    assert any("mode" in condition and "0600" in condition for condition in backup_conditions)
    assert any("size" in condition and "> 0" in condition for condition in backup_conditions)
    exact_conditions = exact_guard["ansible.builtin.assert"]["that"]
    assert any("size" in condition and "authentik_legacy_compose_state" in condition for condition in exact_conditions)
    assert any(
        "checksum" in condition and "authentik_legacy_compose_state" in condition for condition in exact_conditions
    )
    assert "not (authentik_current_compose_is_openbao_managed" in exact_guard["when"][1]
    assert names.index(resume_guard["name"]) < names.index(backup["name"])
    assert names.index(exact_guard["name"]) < names.index("Adopt and verify the allowlisted Authentik legacy secrets")
    assert names.index(exact_guard["name"]) < names.index("Render the Authentik compose file")


def test_interrupted_generate_mode_resumes_and_reports_current_item_changes(tmp_path: Path) -> None:
    tasks = load_yaml(TASKS_PATH)
    partial_guard = next(
        task for task in tasks if task["name"] == "Reject partial Authentik secret state in preserve mode"
    )
    legacy_guard = next(
        task for task in tasks if task["name"] == "Reject secret generation over a legacy Authentik environment"
    )
    data_guard = next(
        task
        for task in tasks
        if task["name"] == "Require absent PostgreSQL data before new Authentik secret generation"
    )
    partial_validator = next(
        task
        for task in tasks
        if task["name"] == "Validate an interrupted Authentik generated secret set before resuming"
    )
    generation = next(
        task for task in tasks if task["name"] == "Generate Authentik secrets only for an explicitly new deployment"
    )

    assert partial_guard["when"] == "authentik_secret_bootstrap_mode == 'preserve'"
    assert legacy_guard["when"] == "authentik_secret_bootstrap_mode == 'generate'"
    assert "authentik_existing_secret_file_count | int < 4" in data_guard["when"]
    assert partial_validator["changed_when"] is False
    assert partial_validator["no_log"] is True
    assert "[0-9a-f]{64}" in " ".join(partial_validator["ansible.builtin.command"]["argv"])
    assert generation["changed_when"] == ("(authentik_secret_generation.stdout | default('') | trim) == 'changed'")

    existing_secret = tmp_path / "already-generated"
    missing_secret = tmp_path / "resume-generation"
    existing_secret.write_text(f"{'a' * 64}\n", encoding="utf-8")
    existing_secret.chmod(0o600)
    generation["loop"] = [
        {"name": "already_generated", "remote_file": str(existing_secret)},
        {"name": "resume_generation", "remote_file": str(missing_secret)},
    ]

    playbook = [
        {
            "name": "Exercise interrupted Authentik generation",
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": {
                "authentik_secret_bootstrap_mode": "generate",
                "authentik_existing_secret_file_count": 1,
                "authentik_legacy_env_state": {"stat": {"exists": False}},
                "authentik_postgres_data_state": {"stat": {"exists": False, "islnk": False}},
                "authentik_secret_file_states_before": {
                    "results": [
                        {
                            "item": {"name": "already_generated", "remote_file": str(existing_secret)},
                            "stat": {"exists": True},
                        }
                    ]
                },
            },
            "tasks": [partial_guard, legacy_guard, data_guard, partial_validator, generation],
        }
    ]
    playbook_path = tmp_path / "generation-resume.yml"
    playbook_path.write_text(yaml.safe_dump(playbook, sort_keys=False), encoding="utf-8")
    ansible_config = tmp_path / "ansible.cfg"
    ansible_config.write_text(
        "[defaults]\n"
        "host_key_checking = False\n"
        "retry_files_enabled = False\n"
        "stdout_callback = default\n"
        "interpreter_python = auto_silent\n",
        encoding="utf-8",
    )
    local_temp = tmp_path / "ansible-local"
    remote_temp = tmp_path / "ansible-remote"
    local_temp.mkdir()
    remote_temp.mkdir()
    ansible_playbook = shutil.which("ansible-playbook")
    assert ansible_playbook is not None
    environment = os.environ.copy()
    environment.update(
        {
            "ANSIBLE_CONFIG": str(ansible_config),
            "ANSIBLE_LOCAL_TEMP": str(local_temp),
            "ANSIBLE_REMOTE_TEMP": str(remote_temp),
            "ANSIBLE_NOCOLOR": "1",
        }
    )

    def run_generation() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [ansible_playbook, "-i", "localhost,", str(playbook_path)],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    first = run_generation()
    assert first.returncode == 0, first.stderr + first.stdout
    assert "changed=1" in first.stdout
    assert missing_secret.exists()
    assert missing_secret.stat().st_mode & 0o777 == 0o600

    second = run_generation()
    assert second.returncode == 0, second.stderr + second.stdout
    assert "changed=0" in second.stdout


def test_local_secret_mirroring_prevalidates_and_never_overwrites_drift() -> None:
    tasks = load_yaml(TASKS_PATH)
    names = [task["name"] for task in tasks]
    inspect_name = "Inspect existing local Authentik secret mirrors"
    shape_name = "Reject unsafe existing local Authentik secret mirrors"
    read_name = "Read existing local Authentik secret mirrors before any copy"
    drift_name = "Refuse drift in any existing local Authentik secret mirror"
    mirror_name = "Mirror the Authentik runtime secrets to the control machine"
    reinspect_name = "Reinspect local Authentik secret mirrors after copy"
    readback_name = "Read back local Authentik secret mirrors after copy"
    verify_name = "Require protected exact local Authentik secret mirrors"

    assert names.index(inspect_name) < names.index(shape_name) < names.index(read_name) < names.index(drift_name)
    assert names.index(drift_name) < names.index(mirror_name) < names.index(reinspect_name)
    assert names.index(reinspect_name) < names.index(readback_name) < names.index(verify_name)

    shape_guard = next(task for task in tasks if task["name"] == shape_name)
    drift_guard = next(task for task in tasks if task["name"] == drift_name)
    mirror = next(task for task in tasks if task["name"] == mirror_name)
    final_guard = next(task for task in tasks if task["name"] == verify_name)

    assert mirror["ansible.builtin.copy"]["force"] is False
    assert mirror["ansible.builtin.copy"]["mode"] == "0600"
    assert mirror["no_log"] is True
    assert drift_guard["no_log"] is True
    assert "item.content | b64decode" in drift_guard["ansible.builtin.assert"]["that"][0]
    assert "item.item.value ~ '\\n'" in drift_guard["ansible.builtin.assert"]["that"][0]
    assert "item.item.value" in drift_guard["ansible.builtin.assert"]["that"][0]

    shape_conditions = shape_guard["ansible.builtin.assert"]["that"]
    assert any("isreg" in condition for condition in shape_conditions)
    assert any("islnk" in condition for condition in shape_conditions)
    assert any("size" in condition and "> 0" in condition for condition in shape_conditions)
    assert any("mode" in condition and "0600" in condition for condition in shape_conditions)
    final_conditions = final_guard["ansible.builtin.assert"]["that"]
    assert any("item.content | b64decode" in condition for condition in final_conditions)
    assert any("item.item.value ~ '\\n'" in condition for condition in final_conditions)
    assert final_guard["no_log"] is True


def test_openbao_agent_must_freshly_render_before_application_start() -> None:
    tasks = load_yaml(TASKS_PATH)
    names = [task["name"] for task in tasks]

    helper_index = names.index("Prepare OpenBao agent runtime secret injection for Authentik")
    before_refresh_index = names.index("Inspect the Authentik runtime environment before OpenBao refresh")
    remove_index = names.index("Remove the transient Authentik runtime environment before agent verification")
    agent_index = names.index("Force-recreate the Authentik OpenBao agent")
    wait_index = names.index("Wait for a fresh Authentik environment rendered by OpenBao agent")
    assert_index = names.index("Assert the Authentik environment was freshly and safely rendered")
    recreate_index = names.index("Decide whether Authentik application services require forced recreation")
    app_index = names.index("Start the Authentik application services")

    assert helper_index < before_refresh_index < remove_index < agent_index < wait_index < assert_index
    assert assert_index < recreate_index < app_index
    assert "Render the Authentik environment file" not in names
    assert not STATIC_ENV_PATH.exists()

    helper = tasks[helper_index]
    assert "common_openbao_compose_env_legacy_env_files" not in helper.get("vars", {})
    agent = tasks[agent_index]
    assert "--force-recreate" in agent["ansible.builtin.command"]["argv"]
    assert agent["ansible.builtin.command"]["argv"][-1] == "openbao-agent"
    before_refresh = tasks[before_refresh_index]
    assert before_refresh["ansible.builtin.stat"]["follow"] is False
    assert before_refresh["ansible.builtin.stat"]["get_checksum"] is True
    assert before_refresh["ansible.builtin.stat"]["checksum_algorithm"] == "sha256"
    assert before_refresh["no_log"] is True
    rendered_stat = next(task for task in tasks if task["name"] == "Inspect the OpenBao-rendered Authentik environment")
    assert rendered_stat["ansible.builtin.stat"]["follow"] is False
    assert rendered_stat["ansible.builtin.stat"]["get_checksum"] is True
    assert rendered_stat["ansible.builtin.stat"]["checksum_algorithm"] == "sha256"
    rendered_assert = tasks[assert_index]["ansible.builtin.assert"]["that"]
    assert "authentik_rendered_env_state.stat.isreg | default(false)" in rendered_assert
    assert "not (authentik_rendered_env_state.stat.islnk | default(false))" in rendered_assert
    assert "authentik_rendered_env_state.stat.mode == '0600'" in rendered_assert
    assert "authentik_rendered_env_state.stat.pw_name == 'root'" in rendered_assert
    assert any("checksum" in condition for condition in rendered_assert)
    assert any("mtime" in condition for condition in rendered_assert)
    recreate = tasks[recreate_index]
    recreate_expression = recreate["ansible.builtin.set_fact"]["authentik_force_recreate_required"]
    assert "authentik_runtime_env_before_refresh.stat.checksum" in recreate_expression
    assert "authentik_rendered_env_state.stat.checksum" in recreate_expression
    assert recreate["no_log"] is True


def test_postgres_env_aliases_render_from_one_canonical_openbao_value() -> None:
    tasks = load_yaml(TASKS_PATH)
    payload_task = next(task for task in tasks if task["name"] == "Record the Authentik OpenBao secret payload")
    payload = payload_task["ansible.builtin.set_fact"]["authentik_runtime_secret_payload"]
    ctmpl_lines = CTMPL_PATH.read_text(encoding="utf-8").splitlines()
    authentik_password = next(line for line in ctmpl_lines if line.startswith("AUTHENTIK_POSTGRESQL__PASSWORD="))
    postgres_password = next(line for line in ctmpl_lines if line.startswith("POSTGRES_PASSWORD="))

    assert payload["AUTHENTIK_POSTGRESQL__PASSWORD"] == "{{ authentik_postgres_password }}"
    assert "POSTGRES_PASSWORD" not in payload
    assert ".Data.data.AUTHENTIK_POSTGRESQL__PASSWORD" in authentik_password
    assert ".Data.data.AUTHENTIK_POSTGRESQL__PASSWORD" in postgres_password
    assert ".Data.data.POSTGRES_PASSWORD" not in postgres_password
    assert payload_task["no_log"] is True


def test_oauth_reconciliation_applies_then_proves_no_change() -> None:
    tasks = load_yaml(OAUTH_TASKS_PATH)
    build = next(task for task in tasks if task["name"] == "Build the Authentik OAuth reconciler command")
    apply = next(
        task for task in tasks if task["name"] == "Apply the Authentik OAuth2 provider and application manifest"
    )
    prove = next(task for task in tasks if task["name"] == "Prove Authentik OAuth reconciliation is idempotent")
    expression = build["ansible.builtin.set_fact"]["authentik_oauth_reconcile_argv"]

    assert "--platform-domain" in expression
    assert "--token-file" in expression
    assert "map('regex_replace', '^', '--client=')" in expression
    assert "\\\\1" not in expression
    assert "--apply" not in expression
    assert apply["ansible.builtin.command"]["argv"] == ("{{ authentik_oauth_reconcile_argv + ['--apply'] }}")
    assert apply["delegate_to"] == "localhost"
    assert apply["no_log"] is True
    assert "from_json" in apply["changed_when"]
    assert prove["ansible.builtin.command"]["argv"] == (
        "{{ authentik_oauth_reconcile_argv + ['--check', '--expect-no-change'] }}"
    )
    assert prove["no_log"] is True


def test_health_and_compose_contract_match_live_runtime() -> None:
    verify = load_yaml(VERIFY_PATH)
    health = next(task for task in verify if task["name"] == "Verify the Authentik health endpoint")
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    ctmpl = CTMPL_PATH.read_text(encoding="utf-8")

    assert health["ansible.builtin.uri"]["status_code"] == 200
    assert health["until"] == "authentik_verify_health.status == 200"
    assert compose.startswith("# managed-by: role=authentik_runtime adr=0491")
    assert '"{{ ansible_host }}:{{ authentik_internal_port }}:{{ authentik_container_port }}"' in compose
    assert 'test "$(stat -c %a {{ authentik_env_file }})" = 600' in compose
    assert compose.count('AUTHENTIK_WEB__BASE_URL: "{{ authentik_public_url }}"') == 2
    assert "kv/data/{{ authentik_openbao_secret_path }}" in ctmpl


def test_argument_spec_exposes_secret_source_and_oauth_contract() -> None:
    options = load_yaml(META_PATH)["argument_specs"]["main"]["options"]

    assert options["authentik_secret_bootstrap_mode"]["choices"] == ["preserve", "adopt_legacy", "generate"]
    assert options["authentik_legacy_compose_backup_file"]["type"] == "path"
    assert options["authentik_oauth_reconcile_enabled"]["type"] == "bool"
    assert options["authentik_oauth_manifest_file"]["type"] == "path"
    assert options["authentik_oauth_reconcile_clients"]["elements"] == "str"
