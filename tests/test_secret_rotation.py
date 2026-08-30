import datetime as dt
import json
import os
import sys
import unittest
from unittest import mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import secret_rotation  # noqa: E402


class SecretRotationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secret_manifest = {
            "secrets": {
                "bootstrap_ssh_private_key": {
                    "path": "/tmp/bootstrap-key",
                },
                "windmill_database_password": {"path": "/tmp/windmill-db"},
                "windmill_superadmin_secret": {"path": "/tmp/windmill-superadmin"},
            }
        }
        self.catalog = {
            "schema_version": "1.0.0",
            "secrets": [
                {
                    "id": "windmill_database_password",
                    "owner_service": "windmill",
                    "storage_contract": "controller-local-secrets",
                    "storage_ref": "windmill_database_password",
                    "rotation_period_days": 30,
                    "warning_window_days": 7,
                    "last_rotated_at": "2026-03-01",
                    "rotation_mode": "repo_automated",
                },
                {
                    "id": "windmill_superadmin_secret",
                    "owner_service": "windmill",
                    "storage_contract": "controller-local-secrets",
                    "storage_ref": "windmill_superadmin_secret",
                    "rotation_period_days": 30,
                    "warning_window_days": 7,
                    "last_rotated_at": "2026-03-01",
                    "rotation_mode": "repo_automated",
                },
            ],
            "rotation_metadata": {
                "state_source": "openbao_kv_metadata",
                "value_field": "value",
                "last_rotated_metadata_key": "lv3_last_rotated",
                "rotated_by_metadata_key": "lv3_last_rotated_by",
                "default_event_subject": "secret.rotation.completed",
                "default_glitchtip_component": "secret-rotation",
            },
            "rotation_contracts": {
                "windmill_database_password": {
                    "owner": "Windmill PostgreSQL runtime",
                    "service": "windmill",
                    "secret_type": "database_password",
                    "risk_level": "low",
                    "approval_mode": "auto",
                    "command_contract": "rotate-secret-low-risk",
                    "rotation_period_days": 30,
                    "warning_window_days": 7,
                    "last_rotated": "2026-03-01T00:00:00Z",
                    "seed_controller_secret_id": "windmill_database_password",
                    "value_generator": "base64_24",
                    "openbao_path": "services/windmill/database-password",
                    "openbao_field": "value",
                    "apply_target": "windmill_database",
                    "event_subject": "secret.rotation.completed",
                    "glitchtip_component": "windmill",
                },
                "windmill_superadmin_secret": {
                    "owner": "Windmill bootstrap admin surface",
                    "service": "windmill",
                    "secret_type": "admin_token",
                    "risk_level": "high",
                    "approval_mode": "approval_required",
                    "command_contract": "rotate-secret-high-risk",
                    "rotation_period_days": 30,
                    "warning_window_days": 7,
                    "last_rotated": None,
                    "seed_controller_secret_id": "windmill_superadmin_secret",
                    "value_generator": "hex_32",
                    "openbao_path": "services/windmill/superadmin-secret",
                    "openbao_field": "value",
                    "apply_target": "windmill_superadmin",
                    "event_subject": "secret.rotation.completed",
                    "glitchtip_component": "windmill",
                },
            },
        }

    def test_validate_secret_catalog_accepts_valid_catalog(self) -> None:
        secret_rotation.validate_secret_catalog(self.catalog, self.secret_manifest)

    def test_validate_secret_catalog_rejects_high_risk_auto_secret(self) -> None:
        invalid = {
            **self.catalog,
            "rotation_contracts": {
                **self.catalog["rotation_contracts"],
                "windmill_superadmin_secret": {
                    **self.catalog["rotation_contracts"]["windmill_superadmin_secret"],
                    "approval_mode": "auto",
                },
            },
        }
        with self.assertRaisesRegex(ValueError, "approval_required"):
            secret_rotation.validate_secret_catalog(invalid, self.secret_manifest)

    def test_rotation_due_uses_warning_window_threshold(self) -> None:
        now = dt.datetime(2026, 3, 25, tzinfo=dt.timezone.utc)
        self.assertTrue(
            secret_rotation.rotation_due(
                self.catalog["rotation_contracts"]["windmill_database_password"],
                now=now,
            )
        )

    def test_rotation_due_without_last_rotated_requires_initial_rotation(self) -> None:
        now = dt.datetime(2026, 3, 2, tzinfo=dt.timezone.utc)
        self.assertTrue(
            secret_rotation.rotation_due(
                self.catalog["rotation_contracts"]["windmill_superadmin_secret"],
                now=now,
            )
        )

    def test_build_playbook_command_sets_expected_vars(self) -> None:
        command, env = secret_rotation.build_playbook_command(
            "windmill_database_password",
            mode="plan",
            force=False,
            approve_high_risk=False,
            new_value=None,
            bootstrap_key_path=secret_rotation.resolve_bootstrap_key(self.secret_manifest),
        )
        self.assertIn("secret_rotation_secret_id=windmill_database_password", command)
        self.assertIn("secret_rotation_mode=plan", command)
        self.assertIn("/tmp/bootstrap-key", command)
        self.assertEqual(env["ANSIBLE_HOST_KEY_CHECKING"], "False")

    def test_build_playbook_command_injects_the_explicit_identity_selector(self) -> None:
        command, _ = secret_rotation.build_playbook_command(
            "windmill_database_password",
            mode="plan",
            force=False,
            approve_high_risk=False,
            new_value=None,
            bootstrap_key_path="/tmp/bootstrap-key",
            identity_overlay_path="/tmp/identity.yml",
        )
        self.assertIn("@/tmp/identity.yml", command)

    def test_run_rotation_applies_and_restores_ansible_environment(self) -> None:
        secret = {
            "approval_mode": "auto",
            "event_subject": "secret.rotation.completed",
            "service": "mail-platform",
            "owner": "test",
            "risk_level": "low",
            "command_contract": "rotate-secret-low-risk",
            "glitchtip_component": "mail-platform",
        }
        manifest = {
            "secrets": {
                "bootstrap_ssh_private_key": {"path": "/tmp/bootstrap-key"},
            }
        }
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        observed_host_key_checking = []

        def fake_run_command(*_args, **_kwargs):
            observed_host_key_checking.append(os.environ.get("ANSIBLE_HOST_KEY_CHECKING"))
            return completed

        with (
            mock.patch.dict(os.environ, {"ANSIBLE_HOST_KEY_CHECKING": "True"}),
            mock.patch.object(secret_rotation, "resolve_identity_overlay_path", return_value=None),
            mock.patch.object(secret_rotation, "run_command", side_effect=fake_run_command) as run,
        ):
            self.assertEqual(
                secret_rotation.run_rotation(
                    "mail_platform_server_mailbox_password",
                    secret,
                    secret_manifest=manifest,
                    mode="plan",
                    force=False,
                    approve_high_risk=False,
                    new_value=None,
                ),
                0,
            )
            self.assertEqual(observed_host_key_checking, ["False"])
            self.assertEqual(os.environ["ANSIBLE_HOST_KEY_CHECKING"], "True")
            run.assert_called_once()

    def test_build_glitchtip_event_carries_rotation_context(self) -> None:
        rotation_event = secret_rotation.build_rotation_event(
            "windmill_superadmin_secret",
            self.catalog["rotation_contracts"]["windmill_superadmin_secret"],
            status="failed",
            mode="apply",
            command=["ansible-playbook", "playbooks/secret-rotation.yml"],
        )
        event = secret_rotation.build_glitchtip_event(
            "windmill_superadmin_secret",
            self.catalog["rotation_contracts"]["windmill_superadmin_secret"],
            rotation_event,
            "example failure",
        )
        self.assertEqual(event["tags"]["secret_id"], "windmill_superadmin_secret")
        self.assertEqual(event["extra"]["error"], "example failure")
        self.assertEqual(rotation_event["subject"], "secret.rotation.failed")

    def test_rotation_playbooks_target_the_canonical_runtime_control_host(self) -> None:
        for relative_path in (
            "playbooks/secret-rotation.yml",
            "collections/ansible_collections/lv3/platform/playbooks/secret-rotation.yml",
        ):
            playbook = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("hosts: runtime-control", playbook)
            self.assertNotIn("hosts: docker-runtime", playbook)
            self.assertIn("now(utc=true", playbook)
            self.assertNotIn("ansible_date_time.iso8601", playbook)
            self.assertIn("secret_rotation_breakglass_password_path", playbook)
            self.assertIn("openbao_secret_rotation_approle", playbook)
            self.assertIn("/v1/auth/approle/role/secret-rotation/secret-id", playbook)
            self.assertIn("secret_rotation_openbao_token", playbook)
            self.assertIn(
                'secret_rotation_new_value: "{{ secret_rotation_effective_value }}"',
                playbook,
            )
            self.assertIn(
                "secret_rotation_selected_secret.openbao_field: secret_rotation_effective_value",
                playbook,
            )
            self.assertNotIn(
                '"{{ secret_rotation_selected_secret.openbao_field }}": "{{ secret_rotation_effective_value }}"',
                playbook,
            )
            self.assertNotIn("root_token", playbook)
            self.assertNotIn("secret_rotation_openbao_init_payload", playbook)
            self.assertIn("secret_rotation_repo_shared_root ~ '/'", playbook)
            self.assertIn("--git-common-dir", playbook)

    def test_rotation_workflow_requires_breakglass_not_root_material(self) -> None:
        workflows = json.loads((REPO_ROOT / "config/workflow-catalog.json").read_text(encoding="utf-8"))
        required = workflows["workflows"]["rotate-secret"]["preflight"]["required_secret_ids"]
        self.assertIn("openbao_breakglass_password", required)
        self.assertNotIn("openbao_init_payload", required)

        manifest = json.loads((REPO_ROOT / "config/controller-local-secrets.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["secrets"]["openbao_secret_rotation_approle"]["path"],
            ".local/openbao/secret-rotation-approle.json",
        )


if __name__ == "__main__":
    unittest.main()
