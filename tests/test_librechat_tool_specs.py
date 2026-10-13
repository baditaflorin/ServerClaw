import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_librechat_tool_specs.py"
SPEC = importlib.util.spec_from_file_location("generate_librechat_tool_specs", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class LibreChatToolSpecTests(unittest.TestCase):
    def test_committed_specs_match_registry_generator_and_use_authentik(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            generated_dir = Path(temp_dir) / "librechat-tools"
            with (
                patch.object(GENERATOR, "OUTPUT_DIR", generated_dir),
                patch.object(sys, "argv", [str(SCRIPT_PATH), "--write"]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(GENERATOR.main(), 0)

            committed_dir = REPO_ROOT / "build" / "librechat-tools"
            expected_files = {
                "ops.openapi.json",
                "tasks.openapi.json",
                "docs.openapi.json",
                "admin.openapi.json",
                "accounts.openapi.json",
                "all.openapi.json",
            }
            self.assertEqual({path.name for path in generated_dir.glob("*.json")}, expected_files)
            for filename in sorted(expected_files):
                with self.subTest(spec=filename):
                    generated = json.loads((generated_dir / filename).read_text())
                    committed = json.loads((committed_dir / filename).read_text())
                    self.assertEqual(committed, generated)
                    if filename in {"accounts.openapi.json", "all.openapi.json"}:
                        self.assertNotIn("keycloak", json.dumps(committed).casefold())


if __name__ == "__main__":
    unittest.main()
