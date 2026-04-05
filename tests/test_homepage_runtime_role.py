import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "homepage_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "homepage_runtime" / "tasks" / "main.yml"
TEMPLATE_PATH = REPO_ROOT / "roles" / "homepage_runtime" / "templates" / "docker-compose.yml.j2"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


class HomepageRuntimeRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
        self.tasks = yaml.safe_load(TASKS_PATH.read_text())
        self.template = TEMPLATE_PATH.read_text()
        self.host_vars_text = HOST_VARS_PATH.read_text()

    def test_defaults_bind_to_guest_address_and_public_host(self) -> None:
        self.assertEqual(self.defaults["homepage_bind_host"], "{{ ansible_host }}")
        self.assertEqual(self.defaults["homepage_loopback_bind_host"], "127.0.0.1")
        self.assertIn("{{ homepage_public_host }}", self.defaults["homepage_allowed_hosts"])
        self.assertIn("{{ homepage_bind_host }}:{{ homepage_port }}", self.defaults["homepage_allowed_hosts"])
        self.assertIn("{{ homepage_loopback_bind_host }}:{{ homepage_port }}", self.defaults["homepage_allowed_hosts"])

    def test_template_binds_private_port_and_mounts_generated_config(self) -> None:
        self.assertIn("{{ homepage_bind_host }}:{{ homepage_port }}:3000", self.template)
        self.assertIn("{{ homepage_loopback_bind_host }}:{{ homepage_port }}:3000", self.template)
        self.assertIn("HOMEPAGE_ALLOWED_HOSTS", self.template)
        self.assertIn("{{ homepage_config_dir }}:/app/config", self.template)

    def test_tasks_render_local_config_then_wait_on_bound_address(self) -> None:
        task_names = {task["name"] for task in self.tasks}
        self.assertIn("Render Homepage config from canonical repo catalogs", task_names)
        self.assertIn("Copy generated Homepage config to the guest", task_names)
        wait_task = next(task for task in self.tasks if task["name"] == "Wait for Homepage to listen locally")
        self.assertEqual(wait_task["ansible.builtin.wait_for"]["host"], "{{ homepage_bind_host }}")

    def test_inventory_declares_homepage_topology_and_firewall_access(self) -> None:
        self.assertIn("homepage_port: 3090", self.host_vars_text)
        self.assertIn("service_name: homepage", self.host_vars_text)
        self.assertIn("owning_vm: runtime-general-lv3", self.host_vars_text)
        self.assertIn("public_hostname: home.lv3.org", self.host_vars_text)
        self.assertIn(
            "upstream: \"http://{{ (proxmox_guests | selectattr('name', 'equalto', 'runtime-general-lv3') | map(attribute='ipv4') | first) }}:9080\"",
            self.host_vars_text,
        )
        self.assertIn("root_proxy_path: /homepage", self.host_vars_text)
        self.assertIn("port: 3090", self.host_vars_text)


if __name__ == "__main__":
    unittest.main()
