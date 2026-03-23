import sys
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "provision-subdomain.yml"


class ProvisionSubdomainPlaybookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.playbook = yaml.safe_load(PLAYBOOK_PATH.read_text())
        self.tasks = self.playbook[0]["tasks"]

    def test_controller_defaults_are_loaded_without_namespacing(self) -> None:
        include_vars_task = next(
            task for task in self.tasks if task["name"] == "Load controller defaults"
        )

        self.assertEqual(
            include_vars_task["ansible.builtin.include_vars"]["file"],
            "{{ inventory_defaults_path }}",
        )
        self.assertNotIn("name", include_vars_task["ansible.builtin.include_vars"])

    def test_playbook_uses_canonical_hetzner_zone_variable(self) -> None:
        serialized_tasks = yaml.safe_dump(self.tasks)

        self.assertIn("hetzner_dns_zone_name", serialized_tasks)
        self.assertNotIn("subdomain_inventory_defaults.hetzner_dns_zone_name", serialized_tasks)


if __name__ == "__main__":
    unittest.main()
