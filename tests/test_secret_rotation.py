import datetime as dt
import sys
import unittest
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
                "default_event_subject": "credentials.rotated",
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
                    "event_subject": "credentials.rotated",
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
                    "event_subject": "credentials.rotated",
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


if __name__ == "__main__":
    unittest.main()
