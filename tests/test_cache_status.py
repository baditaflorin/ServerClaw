import json
from pathlib import Path

from cache_status import load_manifest, render_summary, summarize_manifest


def test_summarize_manifest_marks_warm_components() -> None:
    manifest = {
        "docker_images": [{"image": "registry.lv3.org/check-runner/python:3.12"}],
        "pip_cache_size_mb": 512,
        "packer_plugins": ["github.com/hashicorp/proxmox"],
        "ansible_collections": ["community.general"],
        "last_warmed": "2026-03-23T10:00:00Z",
        "warnings": [],
    }
    rows = summarize_manifest(manifest)
    assert rows[0]["status"] == "warm"
    assert rows[1]["detail"] == "512 MB"
    assert rows[3]["detail"] == "1 collection(s)"


def test_render_summary_includes_warnings() -> None:
    manifest = {
        "docker_images": [],
        "pip_cache_size_mb": 0,
        "packer_plugins": [],
        "ansible_collections": [],
        "last_warmed": None,
        "warnings": ["check-runner manifest missing"],
    }
    output = render_summary(manifest)
    assert "warnings" in output
    assert "check-runner manifest missing" in output


def test_load_manifest_reads_json_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "build-cache-manifest.json"
    manifest_path.write_text(json.dumps({"docker_images": [], "warnings": []}))
    assert load_manifest(manifest_path)["docker_images"] == []
