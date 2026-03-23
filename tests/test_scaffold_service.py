import json
import shutil
import sys
import unittest
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scaffold_service


REPO_ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD_TEMPLATE_SRC = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "_template"
    / "service_scaffold"
)


class ScaffoldServiceTests(unittest.TestCase):
    def build_repo(self, root: Path) -> None:
        (root / "docs" / "adr").mkdir(parents=True)
        (root / "docs" / "workstreams").mkdir(parents=True)
        (root / "docs" / "runbooks").mkdir(parents=True)
        (root / "playbooks" / "services").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
        (root / "inventory" / "host_vars").mkdir(parents=True)
        (
            root
            / "collections"
            / "ansible_collections"
            / "lv3"
            / "platform"
            / "roles"
            / "_template"
        ).mkdir(parents=True)
        shutil.copytree(
            SCAFFOLD_TEMPLATE_SRC,
            root
            / "collections"
            / "ansible_collections"
            / "lv3"
            / "platform"
            / "roles"
            / "_template"
            / "service_scaffold",
        )

        (root / "docs" / "adr" / "0001-bootstrap.md").write_text("# ADR 0001\n")
        (root / "workstreams.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0.0",
                    "workstreams": [],
                },
                sort_keys=False,
            )
        )
        (root / "inventory" / "host_vars" / "proxmox_florin.yml").write_text(
            yaml.safe_dump(
                {
                    "management_ipv4": "65.108.75.123",
                    "management_tailscale_ipv4": "100.118.189.95",
                    "proxmox_guests": [
                        {
                            "vmid": 120,
                            "name": "docker-runtime-lv3",
                            "role": "docker-runtime",
                            "template_key": "lv3-ops-base",
                            "ipv4": "10.10.10.20",
                        }
                    ],
                    "lv3_service_topology": {
                        "docker_runtime": {
                            "service_name": "docker-runtime",
                            "owning_vm": "docker-runtime-lv3",
                            "private_ip": "{{ (proxmox_guests | selectattr('name', 'equalto', 'docker-runtime-lv3') | map(attribute='ipv4') | first) }}",
                            "exposure_model": "informational-only",
                            "observability": {
                                "guest_dashboard": True,
                                "service_telemetry": True,
                            },
                        }
                    },
                },
                sort_keys=False,
            )
        )
        (root / "config" / "service-capability-catalog.json").write_text(
            json.dumps(
                {
                    "$schema": "docs/schema/service-capability-catalog.schema.json",
                    "schema_version": "1.0.0",
                    "services": [
                        {
                            "id": "docker_runtime",
                            "name": "Docker Runtime",
                            "description": "Runtime VM.",
                            "category": "infrastructure",
                            "lifecycle_status": "active",
                            "vm": "docker-runtime-lv3",
                            "vmid": 120,
                            "internal_url": "ssh://ops@10.10.10.20",
                            "exposure": "informational-only",
                            "health_probe_id": "docker_runtime",
                            "adr": "0023",
                            "runbook": "docs/runbooks/configure-docker-runtime.md",
                            "tags": ["runtime"],
                            "environments": {
                                "production": {
                                    "status": "active",
                                    "url": "ssh://ops@10.10.10.20",
                                }
                            },
                        }
                    ],
                },
                indent=2,
            )
            + "\n"
        )
        (root / "config" / "subdomain-catalog.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "reserved_prefixes": [
                        {"prefix": "ops", "owner_adr": "0074"},
                    ],
                    "subdomains": [],
                },
                indent=2,
            )
            + "\n"
        )
        (root / "config" / "health-probe-catalog.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "services": {
                        "docker_runtime": {
                            "service_name": "docker-runtime",
                            "owning_vm": "docker-runtime-lv3",
                            "role": "docker_runtime",
                            "verify_file": "roles/docker_runtime/tasks/verify.yml",
                            "liveness": {
                                "kind": "systemd",
                                "description": "docker daemon",
                                "timeout_seconds": 30,
                                "retries": 1,
                                "delay_seconds": 0,
                                "unit": "docker",
                                "expected_state": "active",
                            },
                            "readiness": {
                                "kind": "command",
                                "description": "docker info",
                                "timeout_seconds": 30,
                                "retries": 1,
                                "delay_seconds": 0,
                                "argv": ["docker", "info"],
                                "success_rc": 0,
                            },
                            "uptime_kuma": {"enabled": False, "reason": "local only"},
                        }
                    },
                },
                indent=2,
            )
            + "\n"
        )
        (root / "config" / "secret-catalog.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "secrets": [],
                },
                indent=2,
            )
            + "\n"
        )
        (root / "config" / "image-catalog.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "images": {},
                },
                indent=2,
            )
            + "\n"
        )
        (root / "config" / "controller-local-secrets.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "secrets": {},
                },
                indent=2,
            )
            + "\n"
        )

    def test_scaffold_creates_role_docs_and_catalog_entries(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.build_repo(root)

            exit_code = scaffold_service.main(
                [
                    "--repo-root",
                    str(root),
                    "--name",
                    "test-echo",
                    "--description",
                    "Echo test service.",
                    "--category",
                    "automation",
                    "--vm",
                    "docker-runtime-lv3",
                    "--port",
                    "8181",
                    "--subdomain",
                    "test-echo.lv3.org",
                    "--exposure",
                    "private-only",
                    "--image",
                    "docker.io/hashicorp/http-echo:latest",
                    "--today",
                    "2026-03-23",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(
                (
                    root
                    / "collections"
                    / "ansible_collections"
                    / "lv3"
                    / "platform"
                    / "roles"
                    / "test_echo_runtime"
                    / "tasks"
                    / "verify.yml"
                ).is_file()
            )
            self.assertTrue((root / "playbooks" / "test-echo.yml").is_file())
            self.assertTrue((root / "playbooks" / "services" / "test-echo.yml").is_file())
            self.assertTrue((root / "docs" / "adr" / "0002-test-echo.md").is_file())
            self.assertTrue((root / "docs" / "workstreams" / "adr-0002-test-echo.md").is_file())
            self.assertTrue((root / "docs" / "runbooks" / "configure-test-echo.md").is_file())

            service_catalog = json.loads((root / "config" / "service-capability-catalog.json").read_text())
            service_entry = next(item for item in service_catalog["services"] if item["id"] == "test_echo")
            self.assertEqual(service_entry["lifecycle_status"], "planned")
            self.assertEqual(service_entry["health_probe_id"], "test_echo")
            self.assertEqual(service_entry["secret_catalog_ids"], ["test_echo_admin_token"])
            self.assertIn("TODO", service_entry["notes"])

            subdomains = json.loads((root / "config" / "subdomain-catalog.json").read_text())["subdomains"]
            subdomain_entry = next(item for item in subdomains if item["fqdn"] == "test-echo.lv3.org")
            self.assertEqual(subdomain_entry["target"], "100.118.189.95")
            self.assertEqual(subdomain_entry["target_port"], 8181)

            health_catalog = json.loads((root / "config" / "health-probe-catalog.json").read_text())
            self.assertFalse(health_catalog["services"]["test_echo"]["uptime_kuma"]["enabled"])
            self.assertIn("TODO", health_catalog["services"]["test_echo"]["uptime_kuma"]["reason"])

            host_vars_text = (root / "inventory" / "host_vars" / "proxmox_florin.yml").read_text()
            self.assertIn("test_echo:", host_vars_text)
            self.assertIn("service_name: test-echo", host_vars_text)

            image_catalog = json.loads((root / "config" / "image-catalog.json").read_text())
            self.assertEqual(image_catalog["images"]["test_echo_runtime"]["tag"], "TODO-pin-tag")

    def test_scaffold_rejects_reserved_prefix_without_allowlist(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.build_repo(root)
            exit_code = scaffold_service.main(
                [
                    "--repo-root",
                    str(root),
                    "--name",
                    "ops-dashboard",
                    "--subdomain",
                    "ops.lv3.org",
                    "--today",
                    "2026-03-23",
                ]
            )
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
