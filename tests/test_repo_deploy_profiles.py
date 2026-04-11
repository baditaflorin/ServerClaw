from __future__ import annotations

import json
from pathlib import Path

import repo_deploy_profiles as profiles


def write_catalog(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_deploy_repo_args_from_dockercompose_profile(tmp_path: Path) -> None:
    catalog_path = tmp_path / "repo-deploy-catalog.json"
    write_catalog(
        catalog_path,
        {
            "$schema": "docs/schema/repo-deploy-catalog.schema.json",
            "schema_version": "1.0.0",
            "profiles": [
                {
                    "id": "education-wemeshup-production",
                    "description": "Deploy education.",
                    "repo": "git@github.com:baditaflorin/education_wemeshup.git",
                    "branch": "main",
                    "source": "private-deploy-key",
                    "app_name": "education-wemeshup",
                    "project": "LV3 Apps",
                    "environment": "production",
                    "build_pack": "dockercompose",
                    "ports": "80",
                    "llm_assistance": "prohibited",
                    "docker_compose_location": "/compose.yaml",
                    "compose_domains": [{"service": "catalog-web", "domain": "education-wemeshup.apps.lv3.org"}],
                }
            ],
        },
    )

    _, profile = profiles.profile_by_id("education-wemeshup-production", path=catalog_path)
    args = profiles.build_deploy_repo_args(profile, wait=True, timeout=1800)

    assert "--repo" in args
    assert "git@github.com:baditaflorin/education_wemeshup.git" in args
    assert "--docker-compose-location" in args
    assert "/compose.yaml" in args
    assert "--compose-domain" in args
    assert "catalog-web=education-wemeshup.apps.lv3.org" in args
    assert "--wait" in args
    assert "--timeout" in args
    assert "1800" in args


def test_validate_repo_deploy_catalog_requires_compose_domain_for_dockercompose(tmp_path: Path) -> None:
    catalog_path = tmp_path / "repo-deploy-catalog.json"
    payload = {
        "$schema": "docs/schema/repo-deploy-catalog.schema.json",
        "schema_version": "1.0.0",
        "profiles": [
            {
                "id": "broken",
                "description": "Deploy education.",
                "repo": "git@github.com:baditaflorin/education_wemeshup.git",
                "branch": "main",
                "source": "private-deploy-key",
                "app_name": "education-wemeshup",
                "project": "LV3 Apps",
                "environment": "production",
                "build_pack": "dockercompose",
                "ports": "80",
                "llm_assistance": "prohibited",
                "docker_compose_location": "/compose.yaml",
                "compose_domains": [],
            }
        ],
    }
    write_catalog(catalog_path, payload)

    catalog = profiles.load_repo_deploy_catalog(catalog_path)
    try:
        profiles.validate_repo_deploy_catalog(catalog, path=catalog_path)
    except ValueError as exc:
        assert "compose_domains must not be empty" in str(exc)
    else:
        raise AssertionError("expected dockercompose profile validation to fail")
