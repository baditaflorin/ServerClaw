from pathlib import Path
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "fleet_runner_private_0mcp_transport"
)
PLAYBOOK = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "fleet-runner-private-0mcp-transport.yml"
)
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "fleet-runner-private-0mcp-transport.md"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_private_transport_defaults_are_closed_to_the_builder_and_vm180() -> None:
    assert load_yaml(ROLE_ROOT / "defaults" / "main.yml") == {
        "fleet_runner_private_0mcp_transport_target_host": "0docker_builder",
        "fleet_runner_private_0mcp_transport_dir": "/etc/fleet-runner",
        "fleet_runner_private_0mcp_transport_file": "/etc/fleet-runner/private-0mcp-transport.json",
        "fleet_runner_private_0mcp_known_hosts_dir": "/etc/fleet-runner/known_hosts",
        "fleet_runner_private_0mcp_known_hosts_file": "/etc/fleet-runner/known_hosts/0mcp-vm180",
        "fleet_runner_private_0mcp_global_known_hosts_file": "/etc/fleet-runner/known_hosts/empty-global",
        "fleet_runner_private_0mcp_ssh_config_file": "/etc/ssh/ssh_config.d/90-fleet-runner-private-0mcp.conf",
        "fleet_runner_private_0mcp_wrapper_file": "/usr/local/sbin/fleet-runner-private-0mcp",
        "fleet_runner_private_0mcp_bastion": "root@203.0.113.1:2222",
        "fleet_runner_private_0mcp_dockerhost": "claude-ops@10.10.10.80",
        "fleet_runner_private_0mcp_compose_root": "/opt/services",
    }


def test_private_transport_rejects_retargeting_before_writing() -> None:
    tasks = load_yaml(ROLE_ROOT / "tasks" / "main.yml")
    names = [task["name"] for task in tasks]
    guard = tasks[0]["ansible.builtin.assert"]

    assert names[0] == "Reject private 0mcp transport convergence outside the designated Builder LXC108"
    assert names.index("Reject private 0mcp transport convergence outside the designated Builder LXC108") < names.index(
        "Ensure the root-only private transport parent exists"
    )
    assert "inventory_hostname == '0docker_builder'" in guard["that"]
    assert "fleet_runner_private_0mcp_known_hosts_dir == '/etc/fleet-runner/known_hosts'" in guard["that"]
    assert (
        "fleet_runner_private_0mcp_global_known_hosts_file == '/etc/fleet-runner/known_hosts/empty-global'"
        in guard["that"]
    )
    assert "fleet_runner_private_0mcp_bastion == 'root@203.0.113.1:2222'" in guard["that"]
    assert "fleet_runner_private_0mcp_dockerhost == 'claude-ops@10.10.10.80'" in guard["that"]


def test_private_transport_uses_pinned_hosts_and_strict_ssh() -> None:
    known_hosts = (ROLE_ROOT / "templates" / "0mcp-vm180.known_hosts.j2").read_text(encoding="utf-8")
    ssh_config = (ROLE_ROOT / "templates" / "90-fleet-runner-private-0mcp.conf.j2").read_text(encoding="utf-8")
    wrapper = (ROLE_ROOT / "templates" / "fleet-runner-private-0mcp.j2").read_text(encoding="utf-8")
    tasks = load_yaml(ROLE_ROOT / "tasks" / "main.yml")
    final_assert = next(
        task["ansible.builtin.assert"]
        for task in tasks
        if task["name"] == "Require fixed root-only private 0mcp transport permissions"
    )
    ssh_parent_assert = next(
        task["ansible.builtin.assert"]
        for task in tasks
        if task["name"] == "Require a safe system SSH configuration parent"
    )
    ssh_resolution_assert = next(
        task["ansible.builtin.assert"]
        for task in tasks
        if task["name"] == "Require strict pinned known-host resolution for the private transport"
    )

    fingerprint_result = subprocess.run(
        ["ssh-keygen", "-lf", "-"],
        input=known_hosts,
        text=True,
        capture_output=True,
        check=True,
    )
    assert set(fingerprint_result.stdout.splitlines()) == {
        "256 SHA256:6rqvLTKsVHl+GTAqtLCZIBRoT/EsJheBDzgAumAZjxU [203.0.113.1]:2222 (ED25519)",
        "3072 SHA256:pApkuLDTCjH4HuClPBr1v7oCR3DGpMRiD5ykEU5jpws [203.0.113.1]:2222 (RSA)",
        "256 SHA256:4aBQZ77B25FCoGZImRo3lgtjxKNKseZMz5dwXU/VInc [203.0.113.1]:2222 (ECDSA)",
        "256 SHA256:DTGcd2S9XtcrAGIp5LLcF6BJVLVsV9dvOcIdcRdai/A 10.10.10.80 (ED25519)",
        "3072 SHA256:0cO+Yc6azxnkfIr7M4g0nmRqyOTSqDu6jzkfYw525iI 10.10.10.80 (RSA)",
        "256 SHA256:K4jtunHD/5U4B8k52YVFmI96KemddTy9lh2meaSlwPs 10.10.10.80 (ECDSA)",
    }
    assert "UserKnownHostsFile {{ fleet_runner_private_0mcp_known_hosts_file }}" in ssh_config
    assert "GlobalKnownHostsFile {{ fleet_runner_private_0mcp_global_known_hosts_file }}" in ssh_config
    assert "StrictHostKeyChecking yes" in ssh_config
    assert "ProxyCommand" not in ssh_config
    assert "StrictHostKeyChecking no" not in ssh_config
    assert "fleet_runner_private_0mcp_ssh_config.stdout_lines" in ssh_resolution_assert["that"][0]
    assert "in fleet_runner_private_0mcp_ssh_config.stdout_lines" in ssh_resolution_assert["that"][1]
    assert "in fleet_runner_private_0mcp_ssh_config.stdout_lines" in ssh_resolution_assert["that"][2]
    assert "FLEET_PRIVATE_0MCP_TRANSPORT_FILE={{ fleet_runner_private_0mcp_transport_file }}" in wrapper
    assert '"$@"' in wrapper
    assert "fleet_runner_private_0mcp_files_after.results[2].stat.mode == '0600'" in final_assert["that"]
    assert "fleet_runner_private_0mcp_files_after.results[3].stat.mode == '0644'" in final_assert["that"]
    assert "fleet_runner_private_0mcp_files_after.results[4].stat.mode == '0400'" in final_assert["that"]
    assert "fleet_runner_private_0mcp_files_after.results[5].stat.mode == '0644'" in final_assert["that"]
    assert "fleet_runner_private_0mcp_files_after.results[6].stat.mode == '0750'" in final_assert["that"]
    assert "fleet_runner_private_0mcp_files_after.results[1].stat.pw_name == 'root'" in final_assert["that"]
    assert "fleet_runner_private_0mcp_files_after.results[1].stat.gr_name == 'root'" in final_assert["that"]
    assert "not (fleet_runner_private_0mcp_ssh_config_dir.stat.islnk | default(false))" in ssh_parent_assert["that"]
    assert (
        "fleet_runner_private_0mcp_ssh_config_dir.stat.mode is match('^0[0-7][0145][0145]$')"
        in ssh_parent_assert["that"]
    )


def test_private_transport_playbook_is_closed_to_the_builder() -> None:
    playbook = load_yaml(PLAYBOOK)
    assert len(playbook) == 1
    assert playbook[0]["hosts"] == "0docker_builder"
    assert playbook[0]["become"] is True
    assert playbook[0]["roles"] == [{"role": "lv3.platform.fleet_runner_private_0mcp_transport"}]


def test_runbook_documents_fail_closed_non_secret_contract() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "non-secret" in runbook
    assert "`0docker_builder`" in runbook
    assert "`StrictHostKeyChecking=yes`" in runbook
    assert "SSH private key" in runbook
