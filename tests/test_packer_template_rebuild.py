import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "packer-template-rebuild.py"
SPEC = importlib.util.spec_from_file_location("packer_template_rebuild", SCRIPT_PATH)
packer_template_rebuild = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(packer_template_rebuild)


def test_calculate_template_digest_changes_with_template_content(tmp_path: Path) -> None:
    packer_dir = tmp_path / "packer"
    (packer_dir / "variables").mkdir(parents=True)
    (packer_dir / "templates").mkdir()
    (packer_dir / "scripts").mkdir()
    (tmp_path / "VERSION").write_text("1.2.3\n")
    (packer_dir / "variables" / "common.pkrvars.hcl").write_text("foo = 1\n")
    (packer_dir / "variables" / "lv3-debian-base.pkrvars.hcl").write_text("image = 1\n")
    (packer_dir / "variables" / "build-server.pkrvars.hcl").write_text("bar = 2\n")
    (packer_dir / "templates" / "lv3-debian-base.pkr.hcl").write_text("source {}\n")
    (packer_dir / "scripts" / "base-hardening.sh").write_text("#!/bin/sh\n")

    digest_a = packer_template_rebuild.calculate_template_digest(tmp_path, "lv3-debian-base")
    (packer_dir / "templates" / "lv3-debian-base.pkr.hcl").write_text("source { updated = true }\n")
    digest_b = packer_template_rebuild.calculate_template_digest(tmp_path, "lv3-debian-base")
    assert digest_a != digest_b


def test_update_manifest_sets_build_metadata(tmp_path: Path, monkeypatch) -> None:
    manifest = {
        "templates": {
            "lv3-debian-base": {
                "vmid": 9000,
                "name": "lv3-debian-base",
                "source_template": "bootstrap",
                "build_date": None,
                "version": None,
                "digest": None,
                "packer_commit": None,
            }
        }
    }
    packer_dir = tmp_path / "packer"
    (packer_dir / "variables").mkdir(parents=True)
    (packer_dir / "templates").mkdir()
    (packer_dir / "scripts").mkdir()
    (tmp_path / "VERSION").write_text("1.2.3\n")
    (packer_dir / "variables" / "common.pkrvars.hcl").write_text("foo = 1\n")
    (packer_dir / "variables" / "lv3-debian-base.pkrvars.hcl").write_text("image = 1\n")
    (packer_dir / "variables" / "build-server.pkrvars.hcl").write_text("bar = 2\n")
    (packer_dir / "templates" / "lv3-debian-base.pkr.hcl").write_text("source {}\n")
    (packer_dir / "scripts" / "base-hardening.sh").write_text("#!/bin/sh\n")

    def fake_run_command(command: list[str], *, cwd: Path, env=None):
        class Result:
            returncode = 0
            stdout = "abc123\n"
            stderr = ""

        return Result()

    monkeypatch.setattr(packer_template_rebuild, "run_command", fake_run_command)
    packer_template_rebuild.update_manifest(tmp_path, manifest, "lv3-debian-base")

    entry = manifest["templates"]["lv3-debian-base"]
    assert entry["version"] == "1.2.3"
    assert entry["packer_commit"] == "abc123"
    assert entry["digest"]
    assert entry["build_date"].endswith("Z")


def test_load_manifest_reads_json(tmp_path: Path) -> None:
    payload = {"templates": {"lv3-debian-base": {"vmid": 9000}}}
    manifest_path = tmp_path / "vm-template-manifest.json"
    manifest_path.write_text(json.dumps(payload))
    assert packer_template_rebuild.load_manifest(manifest_path) == payload
