from __future__ import annotations

import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_homepage_config  # noqa: E402


def _replace_example_domain(value, platform_domain: str):
    if isinstance(value, str):
        return value.replace("example.com", platform_domain)
    if isinstance(value, list):
        return [_replace_example_domain(item, platform_domain) for item in value]
    if isinstance(value, dict):
        return {key: _replace_example_domain(val, platform_domain) for key, val in value.items()}
    return value


def test_render_outputs_include_homepage_tile_and_bookmarks(monkeypatch) -> None:
    monkeypatch.setattr(generate_homepage_config, "apply_identity_domain_overlay", lambda payload: payload)
    outputs = generate_homepage_config.render_outputs()

    services = yaml.safe_load(outputs["services.yaml"])
    bookmarks = yaml.safe_load(outputs["bookmarks.yaml"])
    settings = yaml.safe_load(outputs["settings.yaml"])

    access_group = next(group["Access & Identity"] for group in services if "Access & Identity" in group)
    homepage_tile = next(item["Homepage"] for item in access_group if "Homepage" in item)

    assert homepage_tile["href"] == "https://home.example.com"
    assert homepage_tile["siteMonitor"] == "http://10.10.10.91:3090"
    assert homepage_tile["icon"] == "mdi-view-dashboard"

    quick_actions = next(group["Quick Actions"] for group in bookmarks if "Quick Actions" in group)
    ops_portal = next(item["Ops Portal"][0] for item in quick_actions if "Ops Portal" in item)

    assert ops_portal["abbr"] == "OP"
    assert ops_portal["href"] == "https://ops.example.com"
    assert settings["title"] == "LV3 Unified Dashboard"


def test_render_outputs_apply_identity_domain_overlay(monkeypatch) -> None:
    monkeypatch.setattr(
        generate_homepage_config,
        "apply_identity_domain_overlay",
        lambda payload: _replace_example_domain(payload, "example.com"),
    )

    outputs = generate_homepage_config.render_outputs()
    services = yaml.safe_load(outputs["services.yaml"])
    bookmarks = yaml.safe_load(outputs["bookmarks.yaml"])

    access_group = next(group["Access & Identity"] for group in services if "Access & Identity" in group)
    homepage_tile = next(item["Homepage"] for item in access_group if "Homepage" in item)
    quick_actions = next(group["Quick Actions"] for group in bookmarks if "Quick Actions" in group)
    ops_portal = next(item["Ops Portal"][0] for item in quick_actions if "Ops Portal" in item)

    assert homepage_tile["href"] == "https://home.example.com"
    assert ops_portal["href"] == "https://ops.example.com"


def test_render_outputs_serialize_expected_files(monkeypatch) -> None:
    monkeypatch.setattr(generate_homepage_config, "apply_identity_domain_overlay", lambda payload: payload)
    outputs = generate_homepage_config.render_outputs()

    assert sorted(outputs) == [
        "bookmarks.yaml",
        "custom.css",
        "services.yaml",
        "settings.yaml",
        "widgets.yaml",
    ]
    assert "box-shadow" in outputs["custom.css"]
