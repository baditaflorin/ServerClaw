import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "nginx_edge_publication" / "tasks" / "main.yml"


class NginxEdgePublicationRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
        self.tasks = yaml.safe_load(TASKS_PATH.read_text())

    def test_defaults_enable_pinned_dns_hetzner_acme(self) -> None:
        self.assertEqual(self.defaults["public_edge_acme_challenge_method"], "dns-hetzner")
        self.assertEqual(self.defaults["public_edge_dns_hetzner_plugin_version"], "3.0.0")
        self.assertEqual(
            self.defaults["public_edge_dns_hetzner_credentials_file"],
            "/etc/letsencrypt/hetzner.ini",
        )
        self.assertEqual(
            self.defaults["public_edge_dns_hetzner_virtualenv"],
            "/opt/certbot-dns-hetzner",
        )

    def test_tasks_include_dns_hetzner_plugin_and_credentials_flow(self) -> None:
        task_names = {task["name"] for task in self.tasks}

        self.assertIn("Install the pinned Certbot Hetzner DNS plugin", task_names)
        self.assertIn(
            "Assert the Hetzner DNS credential file is available when DNS-01 is enabled",
            task_names,
        )


if __name__ == "__main__":
    unittest.main()
