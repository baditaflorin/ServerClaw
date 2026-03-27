from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_namespace


def test_resolve_run_namespace_uses_explicit_run_id(tmp_path: Path) -> None:
    namespace = run_namespace.resolve_run_namespace(
        repo_root=tmp_path,
        run_id="ADR 0177 / parallel live apply",
    )

    assert namespace.run_id == "ADR 0177 / parallel live apply"
    assert namespace.run_slug == "adr-0177-parallel-live-apply"
    assert namespace.root.endswith(".local/runs/adr-0177-parallel-live-apply")
    assert namespace.ansible_tmp_dir.endswith("/ansible/tmp")
    assert namespace.tofu_dir.endswith("/tofu")
    assert namespace.receipts_dir.endswith("/receipts")


def test_shell_and_make_output_include_partitioned_paths(tmp_path: Path) -> None:
    namespace = run_namespace.resolve_run_namespace(repo_root=tmp_path, run_id="test-run")
    run_namespace.ensure_run_namespace(namespace)

    shell_payload = {}
    for line in run_namespace.shell_lines(namespace).splitlines():
        key, _, value = line.partition("=")
        shell_payload[key] = json.loads(value)

    assert shell_payload["LV3_RUN_ID"] == "test-run"
    assert shell_payload["LV3_RUN_NAMESPACE_ROOT"].endswith(".local/runs/test-run")
    assert shell_payload["LV3_RUN_ANSIBLE_TMP_DIR"].endswith("/ansible/tmp")
    assert shell_payload["LV3_RUN_TOFU_DIR"].endswith("/tofu")

    make_payload = {
        key.strip(): value.strip()
        for key, _, value in (line.partition(":=") for line in run_namespace.make_lines(namespace).splitlines())
    }
    assert make_payload["RUN_NAMESPACE_ROOT"].endswith(".local/runs/test-run")
    assert make_payload["RUN_NAMESPACE_ANSIBLE_LOG_PATH"].endswith("/logs/ansible.log")
