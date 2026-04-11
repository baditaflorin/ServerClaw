import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "warm-build-cache.py"
SPEC = importlib.util.spec_from_file_location("warm_build_cache", SCRIPT_PATH)
warm_build_cache = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(warm_build_cache)


def test_collect_check_runner_images_deduplicates_entries() -> None:
    manifest = {
        "lint-yaml": {"image": "registry.example.com/check-runner/ansible:2.17"},
        "lint-ansible": {"image": "registry.example.com/check-runner/ansible:2.17"},
        "type-check": {"image": "registry.example.com/check-runner/python:3.12"},
    }
    assert warm_build_cache.collect_check_runner_images(manifest) == [
        "registry.example.com/check-runner/ansible:2.17",
        "registry.example.com/check-runner/python:3.12",
    ]


def test_collect_requested_collections_parses_requirements_file() -> None:
    requirements_text = """
collections:
  - name: ansible.posix
  - name: community.general
"""
    assert warm_build_cache.collect_requested_collections(requirements_text) == [
        "ansible.posix",
        "community.general",
    ]


def test_find_packer_templates_scans_repo_tree(tmp_path: Path) -> None:
    packer_dir = tmp_path / "packer"
    packer_dir.mkdir()
    template = packer_dir / "debian-base.pkr.hcl"
    template.write_text("packer {}")
    assert warm_build_cache.find_packer_templates(tmp_path) == [template]


def test_write_manifest_persists_sorted_json(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    payload = {"warnings": [], "docker_images": []}
    warm_build_cache.write_manifest(manifest_path, payload)
    assert json.loads(manifest_path.read_text()) == payload


def test_run_command_handles_missing_binaries() -> None:
    result = warm_build_cache._run_command(["/definitely/missing/binary"])
    assert result.returncode == 127
    assert result.stderr
