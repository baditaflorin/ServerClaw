import sys
import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import identity_yaml  # noqa: E402
import validation_toolkit  # noqa: E402


class ValidationToolkitTests(unittest.TestCase):
    def test_require_int_accepts_legacy_positional_bounds(self) -> None:
        self.assertEqual(validation_toolkit.require_int(5, "field", 1, 10), 5)

    def test_require_int_rejects_out_of_range_legacy_positional_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "field must be <= 10"):
            validation_toolkit.require_int(11, "field", 1, 10)

    def test_load_identity_vars_prefers_repo_platform_package_when_stdlib_platform_is_preloaded(self) -> None:
        code = f"""
import importlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

repo_root = Path({str(REPO_ROOT)!r})
scripts_dir = repo_root / "scripts"
sys.path.insert(0, str(scripts_dir))
sys.modules["platform"] = importlib.import_module("platform")

import validation_toolkit

temp_dir = Path(tempfile.mkdtemp(prefix="validation-toolkit-subprocess-"))
repo = temp_dir / "repo"
identity_path = repo / "inventory" / "group_vars" / "all" / "identity.yml"
overlay_path = repo / ".local" / "identity.yml"
identity_path.parent.mkdir(parents=True)
overlay_path.parent.mkdir(parents=True)
identity_path.write_text("platform_domain: example.com\\n", encoding="utf-8")
overlay_path.write_text("platform_domain: example.com\\n", encoding="utf-8")

with patch.object(validation_toolkit, "_find_identity_path", return_value=identity_path):
    print(validation_toolkit.load_identity_vars()["platform_domain"])
"""

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "example.com")

    def test_load_yaml_with_identity_uses_shared_local_overlay_values(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="validation-toolkit-"))
        repo_root = temp_dir / "repo"
        identity_path = repo_root / "inventory" / "group_vars" / "all" / "identity.yml"
        host_vars_path = repo_root / "inventory" / "host_vars" / "proxmox-host.yml"
        overlay_path = repo_root / ".local" / "identity.yml"
        try:
            identity_path.parent.mkdir(parents=True)
            host_vars_path.parent.mkdir(parents=True)
            overlay_path.parent.mkdir(parents=True)
            identity_path.write_text(
                "platform_domain: example.com\nplatform_operator_name: Platform Operator\n",
                encoding="utf-8",
            )
            overlay_path.write_text(
                "platform_domain: example.com\nplatform_operator_name: Live Operator\n",
                encoding="utf-8",
            )
            host_vars_path.write_text(
                "public_hostname: agents.{{ platform_domain }}\noperator_name: '{{ platform_operator_name }}'\n",
                encoding="utf-8",
            )

            with patch.object(validation_toolkit, "_find_identity_path", return_value=identity_path):
                rendered = validation_toolkit.load_yaml_with_identity(host_vars_path)

            self.assertEqual(rendered["public_hostname"], "agents.example.com")
            self.assertEqual(rendered["operator_name"], "Live Operator")
        finally:
            for child in sorted(temp_dir.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()

    def test_identity_loaders_prefer_explicit_selector_over_shared_overlay(self) -> None:
        with tempfile.TemporaryDirectory(prefix="explicit-identity-selector-") as temp_value:
            repo_root = Path(temp_value) / "repo"
            identity_path = repo_root / "inventory" / "group_vars" / "all" / "identity.yml"
            shared_path = repo_root / ".local" / "identity.yml"
            explicit_path = repo_root / ".local" / "identity.yml.selected"
            identity_path.parent.mkdir(parents=True)
            shared_path.parent.mkdir(parents=True)
            identity_path.write_text("platform_domain: example.com\n", encoding="utf-8")
            shared_path.write_text("platform_domain: shared.example\n", encoding="utf-8")
            explicit_path.write_text("platform_domain: selected.example\n", encoding="utf-8")

            with (
                patch.dict("os.environ", {"PLATFORM_IDENTITY_OVERLAY": str(explicit_path)}),
                patch.object(validation_toolkit, "_find_identity_path", return_value=identity_path),
                patch.object(identity_yaml, "_find_identity_path", return_value=identity_path),
            ):
                self.assertEqual(validation_toolkit.load_identity_vars()["platform_domain"], "selected.example")
                self.assertEqual(identity_yaml.load_identity_vars()["platform_domain"], "selected.example")

    def test_resolve_public_domain_placeholders_uses_shared_local_overlay_values(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="validation-toolkit-"))
        repo_root = temp_dir / "repo"
        identity_path = repo_root / "inventory" / "group_vars" / "all" / "identity.yml"
        overlay_path = repo_root / ".local" / "identity.yml"
        try:
            identity_path.parent.mkdir(parents=True)
            overlay_path.parent.mkdir(parents=True)
            identity_path.write_text("platform_domain: example.com\n", encoding="utf-8")
            overlay_path.write_text("platform_domain: example.com\n", encoding="utf-8")

            payload = {
                "url": "https://api.example.com",
                "nested": [
                    {"fqdn": "chat.example.com"},
                    {"cert_path": "/etc/letsencrypt/live/{{ platform_config_prefix }}-edge/"},
                    {"label": "unchanged"},
                ],
            }

            with patch.object(validation_toolkit, "_find_identity_path", return_value=identity_path):
                resolved = validation_toolkit.resolve_public_domain_placeholders(payload)

            self.assertEqual(resolved["url"], "https://api.example.com")
            self.assertEqual(resolved["nested"][0]["fqdn"], "chat.example.com")
            self.assertEqual(resolved["nested"][1]["cert_path"], "/etc/letsencrypt/live/lv3-edge/")
            self.assertEqual(resolved["nested"][2]["label"], "unchanged")
        finally:
            for child in sorted(temp_dir.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()


if __name__ == "__main__":
    unittest.main()
