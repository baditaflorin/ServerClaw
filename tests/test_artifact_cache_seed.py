import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "artifact_cache_seed.py"
SPEC = importlib.util.spec_from_file_location("artifact_cache_seed", SCRIPT_PATH)
artifact_cache_seed = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(artifact_cache_seed)


def test_iter_image_refs_collects_ref_and_image_fields() -> None:
    payload = {
        "images": {"homepage": {"ref": "ghcr.io/gethomepage/homepage:v1@sha256:abc"}},
        "checks": [{"image": "docker.io/library/nginx:1.29.1@sha256:def"}],
    }
    assert artifact_cache_seed.iter_image_refs(payload) == [
        "ghcr.io/gethomepage/homepage:v1@sha256:abc",
        "docker.io/library/nginx:1.29.1@sha256:def",
    ]


def test_build_seed_plan_rewrites_supported_refs_to_mirror_endpoints(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "images": {
                    "homepage": {"ref": "ghcr.io/gethomepage/homepage:v1@sha256:abc"},
                    "nginx": {"ref": "docker.io/library/nginx:1.29.1@sha256:def"},
                }
            }
        )
    )
    plan = artifact_cache_seed.build_seed_plan(
        [catalog],
        {
            "docker.io": "10.10.10.30:5001",
            "ghcr.io": "10.10.10.30:5002",
        },
    )
    assert plan["seed_images"] == [
        {
            "registry_host": "ghcr.io",
            "source_ref": "ghcr.io/gethomepage/homepage:v1@sha256:abc",
            "mirror_ref": "10.10.10.30:5002/gethomepage/homepage:v1@sha256:abc",
        },
        {
            "registry_host": "docker.io",
            "source_ref": "docker.io/library/nginx:1.29.1@sha256:def",
            "mirror_ref": "10.10.10.30:5001/library/nginx:1.29.1@sha256:def",
        },
    ]
    assert plan["unsupported_images"] == []


def test_build_seed_plan_reports_unsupported_registry_hosts(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"images": {"runner": {"ref": "registry.example.com/check-runner/python:3.12"}}}))
    plan = artifact_cache_seed.build_seed_plan([catalog], {"docker.io": "http://10.10.10.30:5001"})
    assert plan["seed_images"] == []
    assert plan["unsupported_images"] == [
        {
            "registry_host": "registry.example.com",
            "source_ref": "registry.example.com/check-runner/python:3.12",
        }
    ]


def test_build_seed_plan_accepts_mirror_values_with_url_schemes(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"images": {"nginx": {"ref": "docker.io/library/nginx:1.29.1@sha256:def"}}}))
    plan = artifact_cache_seed.build_seed_plan([catalog], {"docker.io": "http://10.10.10.30:5001"})

    assert plan["seed_images"] == [
        {
            "registry_host": "docker.io",
            "source_ref": "docker.io/library/nginx:1.29.1@sha256:def",
            "mirror_ref": "10.10.10.30:5001/library/nginx:1.29.1@sha256:def",
        }
    ]
