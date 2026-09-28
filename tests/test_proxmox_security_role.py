from pathlib import Path

import yaml
from jinja2 import Environment


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "proxmox_security" / "tasks" / "main.yml"
COLLECTION_ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "proxmox_security"
    / "tasks"
    / "main.yml"
)


def test_acme_plugin_detection_uses_json_output_and_parsed_conditions() -> None:
    for path in (ROLE_TASKS, COLLECTION_ROLE_TASKS):
        task_text = path.read_text()
        assert "pvenode\n      - acme\n      - plugin\n      - list\n      - --output-format\n      - json" in task_text
        assert "map(attribute='plugin')" in task_text
        assert "is not contains(proxmox_acme_plugin_id)" in task_text
        assert "is contains(proxmox_acme_plugin_id)" in task_text


def test_cluster_firewall_renders_declared_tailnet_tcp_exception() -> None:
    template_path = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "proxmox_security"
        / "templates"
        / "cluster.fw.j2"
    )
    rendered = (
        Environment(trim_blocks=True)
        .from_string(template_path.read_text(encoding="utf-8"))
        .render(
            proxmox_management_allowed_sources=["100.64.0.1/32"],
            proxmox_management_allowed_tcp_ports=[],
            proxmox_cluster_additional_tcp_rules=[
                {"source": "100.64.0.42/32", "port": 9100},
                {"source": "100.64.0.43/32", "port": 9101},
            ],
            proxmox_public_ingress_tcp_ports=[],
        )
    )

    assert "IN ACCEPT -p tcp -dport 9100 -source 100.64.0.42/32" in rendered.splitlines()
    assert "IN ACCEPT -p tcp -dport 9101 -source 100.64.0.43/32" in rendered.splitlines()
    assert "IN ACCEPT -p tcp -dport 9100 -source +management" not in rendered


def test_host_firewall_preserves_existing_live_host_rules() -> None:
    template_path = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "proxmox_security"
        / "templates"
        / "host.fw.j2"
    )
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text())
    rules = host_vars["proxmox_host_additional_tcp_rules"]
    rendered = (
        Environment(trim_blocks=True)
        .from_string(template_path.read_text(encoding="utf-8"))
        .render(proxmox_host_additional_tcp_rules=rules)
    )

    assert any(rule["port"] == 18021 for rule in rules)
    assert any(rule["port"] == 9101 for rule in rules)
    rendered_rules = [line for line in rendered.splitlines() if line.startswith("IN ACCEPT")]
    assert rendered_rules == [
        "IN ACCEPT -i vmbr20 -source 10.10.10.71/32 -dest 10.10.10.1 -p tcp -dport 18021 # Allow the Coolify app VM to reach the private Tailscale-relayed API key verifier",
        "IN ACCEPT -source 100.114.37.21/32 -p tcp -dport 9101 # Allow capacity-controller access to the Proxmox metrics proxy",
    ]


def test_firewall_policy_tag_is_limited_to_proxmox_firewall_tasks() -> None:
    tasks = yaml.safe_load(COLLECTION_ROLE_TASKS.read_text(encoding="utf-8"))
    firewall_tag = "proxmox_firewall_policy"
    boundary = next(
        index for index, task in enumerate(tasks) if task.get("name") == "Render break-glass sshd port drop-in"
    )

    assert all(firewall_tag in task.get("tags", []) for task in tasks[:boundary])
    assert all(firewall_tag not in task.get("tags", []) for task in tasks[boundary:])


def test_proxmox_security_role_copies_stay_in_sync() -> None:
    for collection_path, root_path in (
        (
            COLLECTION_ROLE_TASKS,
            REPO_ROOT / "roles" / "proxmox_security" / "tasks" / "main.yml",
        ),
        (
            REPO_ROOT
            / "collections"
            / "ansible_collections"
            / "lv3"
            / "platform"
            / "roles"
            / "proxmox_security"
            / "templates"
            / "host.fw.j2",
            REPO_ROOT / "roles" / "proxmox_security" / "templates" / "host.fw.j2",
        ),
    ):
        assert collection_path.read_bytes() == root_path.read_bytes()
