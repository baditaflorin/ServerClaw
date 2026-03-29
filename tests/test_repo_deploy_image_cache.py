import importlib.util
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "repo_deploy_image_cache.py"
SPEC = importlib.util.spec_from_file_location("repo_deploy_image_cache", SCRIPT_PATH)
repo_deploy_image_cache = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(repo_deploy_image_cache)

ROLE_ROOT = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "repo_deploy_image_cache"
)


def test_current_profile_catalog_validates_and_builds_a_plan() -> None:
    payload = repo_deploy_image_cache.load_profile_catalog()
    repo_deploy_image_cache.validate_profile_catalog(payload)
    plan = repo_deploy_image_cache.build_plan(payload)

    assert plan["profile_count"] == 1
    assert [entry["ref"] for entry in plan["seed_images"]] == [
        "docker.io/library/postgres:17.4-alpine3.21",
        "mirror.gcr.io/library/alpine:3.21.3",
        "mirror.gcr.io/library/golang:1.25.0-alpine3.21",
        "mirror.gcr.io/library/node:22.14.0-bookworm-slim",
        "mirror.gcr.io/nginxinc/nginx-unprivileged:1.27.5-alpine3.21",
    ]


def test_build_plan_deduplicates_image_refs_across_profiles() -> None:
    payload = {
        "$schema": "docs/schema/repo-deploy-base-image-profiles.schema.json",
        "schema_version": "1.0.0",
        "profiles": [
            {
                "id": "profile-a",
                "name": "Profile A",
                "description": "A",
                "deployment_lane": "coolify",
                "allowed_build_packs": ["dockercompose"],
                "freshness_hours": 24,
                "bundles": [
                    {
                        "id": "bundle-a",
                        "concern": "runtime_base",
                        "images": [
                            {"id": "alpine-runtime", "ref": "mirror.gcr.io/library/alpine:3.21.3"},
                        ],
                    }
                ],
            },
            {
                "id": "profile-b",
                "name": "Profile B",
                "description": "B",
                "deployment_lane": "coolify",
                "allowed_build_packs": ["dockerfile"],
                "freshness_hours": 12,
                "bundles": [
                    {
                        "id": "bundle-b",
                        "concern": "runtime_base",
                        "images": [
                            {"id": "alpine-runtime-b", "ref": "mirror.gcr.io/library/alpine:3.21.3"},
                        ],
                    }
                ],
            },
        ],
    }

    plan = repo_deploy_image_cache.build_plan(payload)
    assert plan["seed_images"] == [
        {
            "ref": "mirror.gcr.io/library/alpine:3.21.3",
            "image_ids": ["alpine-runtime", "alpine-runtime-b"],
            "profile_ids": ["profile-a", "profile-b"],
            "bundle_ids": ["bundle-a", "bundle-b"],
            "concerns": ["runtime_base"],
            "freshness_hours": 12,
        }
    ]


def test_warm_and_verify_emit_a_receipt(monkeypatch, tmp_path: Path) -> None:
    plan = {
        "schema_version": "1.0.0",
        "generated_at": "2026-03-30T10:00:00Z",
        "profile_count": 1,
        "profiles": [],
        "seed_images": [
            {
                "ref": "mirror.gcr.io/library/alpine:3.21.3",
                "image_ids": ["alpine-runtime"],
                "profile_ids": ["profile-a"],
                "bundle_ids": ["bundle-a"],
                "concerns": ["runtime_base"],
                "freshness_hours": 24,
            }
        ],
    }
    plan_file = tmp_path / "seed-plan.json"
    receipt_file = tmp_path / "warm-status.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    def fake_run(argv, text, capture_output, check):  # type: ignore[no-untyped-def]
        assert argv == ["docker", "pull", "mirror.gcr.io/library/alpine:3.21.3"]
        return repo_deploy_image_cache.subprocess.CompletedProcess(
            argv,
            0,
            stdout="Status: Downloaded newer image for mirror.gcr.io/library/alpine:3.21.3\n",
            stderr="",
        )

    monkeypatch.setattr(repo_deploy_image_cache.subprocess, "run", fake_run)

    receipt = repo_deploy_image_cache.warm_plan(
        plan,
        plan_file=plan_file,
        receipt_file=receipt_file,
        required=True,
    )

    assert receipt["result"] == "pass"
    assert receipt["changed_count"] == 1
    written = json.loads(receipt_file.read_text(encoding="utf-8"))
    repo_deploy_image_cache.verify_receipt(
        plan=plan,
        receipt=written,
        required=True,
        max_age_seconds=3600,
    )


def test_role_installs_a_timer_and_verifies_freshness() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    verify_tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "verify.yml").read_text())
    service_template = (ROLE_ROOT / "templates" / "lv3-repo-deploy-image-cache.service.j2").read_text()
    timer_template = (ROLE_ROOT / "templates" / "lv3-repo-deploy-image-cache.timer.j2").read_text()

    assert defaults["repo_deploy_image_cache_runtime_root"] == "/opt/repo-deploy-image-cache"
    assert defaults["repo_deploy_image_cache_timer_name"] == "lv3-repo-deploy-image-cache.timer"
    assert defaults["repo_deploy_image_cache_on_calendar"] == "hourly"
    assert [task["name"] for task in tasks][-1] == "Verify repo deploy image cache freshness and timer state"
    assert verify_tasks[0]["ansible.builtin.command"]["argv"][2] == "verify"
    assert "--max-age-seconds" in verify_tasks[0]["ansible.builtin.command"]["argv"]
    assert "ExecStart=/usr/bin/python3 {{ repo_deploy_image_cache_script_path }} warm" in service_template
    assert "OnCalendar={{ repo_deploy_image_cache_on_calendar }}" in timer_template
