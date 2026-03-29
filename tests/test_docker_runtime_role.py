from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "tasks"
    / "main.yml"
)
ROLE_DEFAULTS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "defaults"
    / "main.yml"
)
ROLE_VERIFY = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "tasks"
    / "verify.yml"
)
COMMON_DOCKER_BRIDGE_CHAINS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "docker_bridge_chains.yml"
)
FIREWALL_TEMPLATE = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "linux_guest_firewall"
    / "templates"
    / "nftables.conf.j2"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_defaults() -> dict:
    return yaml.safe_load(ROLE_DEFAULTS.read_text())


def load_verify() -> list[dict]:
    return yaml.safe_load(ROLE_VERIFY.read_text())


def load_common_docker_bridge_chains() -> list[dict]:
    return yaml.safe_load(COMMON_DOCKER_BRIDGE_CHAINS.read_text())


def test_docker_runtime_patches_nftables_before_starting_docker() -> None:
    task_names = [task["name"] for task in load_tasks()]
    assert task_names.index("Apply Docker bridge forward-compat rules live without reloading nftables") < task_names.index(
        "Ensure Docker service is enabled and running"
    )


def test_docker_runtime_rechecks_nat_and_forward_chains() -> None:
    tasks = load_tasks()
    defaults = load_defaults()
    task_names = {task["name"] for task in tasks}
    assert "Flush Docker handlers before chain health checks" in task_names
    assert "Reset Docker failed state before nat-chain recovery restart" in task_names
    assert "Ensure Docker bridge networking chains are present" in task_names
    ensure_task = next(task for task in tasks if task["name"] == "Ensure Docker bridge networking chains are present")
    include_role = ensure_task["ansible.builtin.include_role"]
    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "docker_bridge_chains"
    assert ensure_task["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert ensure_task["vars"]["common_docker_bridge_chains_require_nat_chain"] == "{{ docker_runtime_require_nat_chain }}"
    assert defaults["docker_runtime_chain_recheck_retries"] == 30
    assert defaults["docker_runtime_chain_recheck_delay_seconds"] == 2
    assert ensure_task["vars"]["common_docker_bridge_chains_retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert ensure_task["vars"]["common_docker_bridge_chains_delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    reset_task = next(task for task in tasks if task["name"] == "Reset Docker failed state before nat-chain recovery restart")
    assert reset_task["ansible.builtin.command"] == "systemctl reset-failed docker.service"
    assert reset_task["changed_when"] is False


def test_common_docker_bridge_chains_warms_control_socket_before_restarting() -> None:
    tasks = load_common_docker_bridge_chains()
    task_names = {task["name"] for task in tasks}
    assert "Warm the Docker control socket before chain health checks" in task_names
    assert "Wait briefly for Docker bridge chains to recover after daemon activation" in task_names
    assert "Restart Docker when required bridge chains are missing" in task_names
    info_ready = next(task for task in tasks if task["name"] == "Warm the Docker control socket before chain health checks")
    chain_wait = next(
        task for task in tasks if task["name"] == "Wait briefly for Docker bridge chains to recover after daemon activation"
    )
    restart_task = next(task for task in tasks if task["name"] == "Restart Docker when required bridge chains are missing")
    nat_recheck = next(task for task in tasks if task["name"] == "Recheck Docker nat chain after health evaluation")
    forward_recheck = next(task for task in tasks if task["name"] == "Recheck Docker forward chain after health evaluation")
    nat_verify = next(task for task in tasks if task["name"] == "Verify Docker nat chain after retry loop")
    forward_verify = next(task for task in tasks if task["name"] == "Verify Docker forward chain after retry loop")
    nat_assert = next(task for task in tasks if task["name"] == "Assert Docker nat chain is present after health evaluation")
    forward_assert = next(
        task for task in tasks if task["name"] == "Assert Docker forward chain is present after health evaluation"
    )

    assert info_ready["ansible.builtin.command"]["argv"] == [
        "docker",
        "info",
        "--format",
        "{{ '{{.ServerVersion}}' }}",
    ]
    assert info_ready["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert info_ready["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert info_ready["until"] == "common_docker_bridge_chains_info_ready.rc == 0"
    assert "iptables -t nat -S DOCKER" in chain_wait["ansible.builtin.shell"]
    assert "iptables -t filter -S DOCKER-FORWARD" in chain_wait["ansible.builtin.shell"]
    assert "sleep {{ common_docker_bridge_chains_delay }}" in chain_wait["ansible.builtin.shell"]
    assert chain_wait["failed_when"] is False
    assert any(".get('rc', 1)" in condition for condition in restart_task["when"])
    assert nat_recheck["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert nat_recheck["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert nat_recheck["until"] == "common_docker_bridge_chains_nat_recheck.rc == 0"
    assert forward_recheck["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert forward_recheck["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert forward_recheck["until"] == "common_docker_bridge_chains_forward_recheck.rc == 0"
    assert nat_verify["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert nat_verify["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert nat_verify["until"] == "common_docker_bridge_chains_nat_verify.rc == 0"
    assert forward_verify["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert forward_verify["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert forward_verify["until"] == "common_docker_bridge_chains_forward_verify.rc == 0"
    assert nat_assert["ansible.builtin.assert"]["that"] == ["common_docker_bridge_chains_nat_verify.rc == 0"]
    assert forward_assert["ansible.builtin.assert"]["that"] == ["common_docker_bridge_chains_forward_verify.rc == 0"]


def test_docker_runtime_patches_nftables_rule_block_once() -> None:
    tasks = load_tasks()
    daemon_stat = next(task for task in tasks if task["name"] == "Check whether the current Docker daemon config exists")
    daemon_slurp = next(task for task in tasks if task["name"] == "Read the current Docker daemon config")
    daemon_fact = next(task for task in tasks if task["name"] == "Record whether Docker currently has live-restore enabled")
    daemon_render = next(task for task in tasks if task["name"] == "Render Docker daemon configuration")
    build_rules = next(task for task in tasks if task["name"] == "Build the Docker bridge forward-compat rule block")
    patch_rules = next(task for task in tasks if task["name"] == "Patch nftables forward policy for Docker bridge egress")
    assert_rules = next(task for task in tasks if task["name"] == "Assert the Docker bridge forward-compat rule is present")
    live_rules = next(
        task for task in tasks if task["name"] == "Apply Docker bridge forward-compat rules live without reloading nftables"
    )

    assert "docker_runtime_container_forward_rule_lines" in build_rules["ansible.builtin.set_fact"]
    assert daemon_stat["ansible.builtin.stat"]["path"] == "/etc/docker/daemon.json"
    assert daemon_slurp["when"] == "docker_runtime_daemon_config_stat.stat.exists"
    assert "docker_runtime_previous_live_restore_enabled" in daemon_fact["ansible.builtin.set_fact"]
    assert daemon_render["register"] == "docker_runtime_daemon_config_render"
    assert "docker_runtime_container_forward_rule_lines" in build_rules["ansible.builtin.set_fact"]
    assert "docker_runtime_container_forward_rule_block" in build_rules["ansible.builtin.set_fact"]
    assert patch_rules["ansible.builtin.lineinfile"]["line"] == "    ip saddr {{ item }} accept"
    assert patch_rules["ansible.builtin.lineinfile"]["insertafter"] == (
        r"^\s*ct state (established,related|related,established) accept$"
    )
    assert patch_rules["loop"] == "{{ docker_runtime_container_forward_source_cidrs | reverse | list }}"
    assert assert_rules["loop"] == "{{ docker_runtime_container_forward_source_cidrs }}"
    assert live_rules["loop"] == "{{ docker_runtime_container_forward_source_cidrs }}"
    assert live_rules["ansible.builtin.command"]["argv"][:6] == ["nft", "add", "rule", "inet", "filter", "forward"]


def test_linux_guest_firewall_template_includes_all_docker_forward_compat_cidrs() -> None:
    template = FIREWALL_TEMPLATE.read_text()
    assert "docker_runtime_container_forward_source_cidrs" in template
    assert "172.16.0.0/12" in template
    assert "192.168.0.0/16" in template


def test_docker_runtime_pins_public_edge_hostnames_and_address_pools() -> None:
    tasks = load_tasks()
    pin_hosts = next(task for task in tasks if task["name"] == "Pin public edge hostnames to the internal edge for Docker guests")

    assert pin_hosts["loop"] == "{{ docker_runtime_public_edge_host_aliases | default([]) }}"


def test_docker_runtime_defaults_pin_governed_resolvers_and_registry_mirror() -> None:
    defaults = load_defaults()
    daemon_config = defaults["docker_runtime_daemon_config"]
    controller_repo_root = defaults["docker_runtime_controller_repo_root"]

    assert defaults["docker_runtime_registry_mirrors"] == ["https://mirror.gcr.io"]
    assert "ansible.builtin.pipe" in controller_repo_root
    assert "git -C " in controller_repo_root
    assert "rev-parse --show-toplevel" in controller_repo_root
    assert defaults["docker_runtime_publication_assurance_helper_local_path"] == (
        "{{ docker_runtime_controller_repo_root }}/scripts/docker_publication_assurance.py"
    )
    assert defaults["docker_runtime_publication_assurance_script_path"] == "/usr/local/bin/lv3-docker-publication-assurance"
    assert defaults["docker_runtime_publication_assurance_helper_source"] == (
        "{{ inventory_dir ~ '/../scripts/docker_publication_assurance.py' }}"
    )
    assert defaults["docker_runtime_insecure_registries"] == []
    assert daemon_config["live-restore"] is False
    assert daemon_config["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert daemon_config["registry-mirrors"] == "{{ docker_runtime_registry_mirrors }}"
    assert daemon_config["insecure-registries"] == "{{ docker_runtime_insecure_registries }}"
    assert daemon_config["default-address-pools"] == [
        {"base": "172.16.0.0/12", "size": 24},
        {"base": "192.168.0.0/16", "size": 24},
        {"base": "10.200.0.0/16", "size": 24},
    ]


def test_docker_runtime_installs_publication_assurance_helper_before_chain_checks() -> None:
    tasks = load_tasks()
    install_task = next(task for task in tasks if task["name"] == "Install the Docker publication assurance helper")
    nftables_check_task = next(task for task in tasks if task["name"] == "Check whether nftables config exists")

    assert install_task["ansible.builtin.copy"]["dest"] == "{{ docker_runtime_publication_assurance_script_path }}"
    assert install_task["ansible.builtin.copy"]["content"] == (
        "{{ lookup('ansible.builtin.file', docker_runtime_publication_assurance_helper_local_path) }}"
    )
    assert tasks.index(install_task) < tasks.index(nftables_check_task)


def test_docker_runtime_waits_out_background_apt_maintenance() -> None:
    tasks = load_tasks()
    prereq_task = next(task for task in tasks if task["name"] == "Install Docker repository prerequisites")
    remove_conflicts_task = next(task for task in tasks if task["name"] == "Remove conflicting Docker packages")
    install_runtime_task = next(task for task in tasks if task["name"] == "Install Docker runtime packages")

    prereq_apt = prereq_task["ansible.builtin.apt"]
    remove_conflicts_apt = remove_conflicts_task["ansible.builtin.apt"]
    install_runtime_apt = install_runtime_task["ansible.builtin.apt"]

    assert prereq_apt["name"] == "{{ docker_runtime_prereq_packages }}"
    assert prereq_apt["state"] == "present"
    assert prereq_apt["update_cache"] is True
    assert prereq_apt["lock_timeout"] == 300
    assert prereq_apt["force_apt_get"] is True

    assert remove_conflicts_apt["name"] == "{{ docker_runtime_conflicting_packages }}"
    assert remove_conflicts_apt["state"] == "absent"
    assert remove_conflicts_apt["lock_timeout"] == 300

    assert install_runtime_apt["name"] == "{{ docker_runtime_engine_packages }}"
    assert install_runtime_apt["state"] == "present"
    assert install_runtime_apt["update_cache"] is True
    assert install_runtime_apt["lock_timeout"] == 300
    assert install_runtime_apt["force_apt_get"] is True


def test_docker_runtime_verify_checks_publication_assurance_helper_is_executable() -> None:
    verify_tasks = load_verify()
    verify_task = next(
        task for task in verify_tasks if task["name"] == "Verify the Docker publication assurance helper is installed"
    )

    assert verify_task["ansible.builtin.command"]["argv"] == [
        "test",
        "-x",
        "{{ docker_runtime_publication_assurance_script_path }}",
    ]
    assert verify_task["changed_when"] is False
