from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

publisher = importlib.import_module("publish_to_serverclaw")


def test_public_inventory_template_matches_sanitized_proxmox_host_name() -> None:
    """Keep the Tier A host template compatible with Tier C host-name replacement."""
    config = yaml.safe_load((REPO_ROOT / "config" / "publication-sanitization.yaml").read_text(encoding="utf-8"))
    host_replacement = next(
        entry["replacement"] for entry in config["string_replacements"] if entry["pattern"] == "proxmox[_-]florin"
    )
    inventory = yaml.safe_load((REPO_ROOT / "publication" / "templates" / "hosts.yml").read_text(encoding="utf-8"))
    children = inventory["all"]["children"]

    assert host_replacement in children["production"]["hosts"]
    assert host_replacement in children["proxmox_hosts"]["hosts"]


def test_public_tier_a_templates_do_not_bypass_private_name_sanitization() -> None:
    """Tier A templates are copied verbatim, so they must already be generic."""
    config = yaml.safe_load((REPO_ROOT / "config" / "publication-sanitization.yaml").read_text(encoding="utf-8"))
    private_name_patterns = {
        "platform_server",
        "proxmox[_-]florin",
    }

    for entry in config["file_replacements"]:
        template = REPO_ROOT / entry["template"]
        content = template.read_text(encoding="utf-8")
        for pattern in private_name_patterns:
            assert re.search(pattern, content) is None, f"{template} still contains private host naming"


def test_publication_sanitizes_private_primary_guest_network() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "publication-sanitization.yaml").read_text(encoding="utf-8"))
    network_replacement = next(
        entry for entry in config["string_replacements"] if entry["pattern"] == "10\\.20\\.10\\."
    )

    assert re.sub(network_replacement["pattern"], network_replacement["replacement"], "http://10.10.10.92:9010") == (
        "http://10.10.10.92:9010"
    )


def test_publication_regenerates_derived_artifacts_after_template_replacement(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], **kwargs: object) -> None:
        calls.append((command, kwargs["cwd"]))

    monkeypatch.setattr(publisher, "run", fake_run)

    publisher.regenerate_public_derived_artifacts(tmp_path)

    assert calls == [
        (["make", "generate-platform-vars"], tmp_path),
        (["make", "generate-platform-vars"], tmp_path),
    ]


def test_publication_branch_snapshot_is_based_on_current_public_main(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], **kwargs: object) -> None:
        calls.append((command, kwargs["cwd"]))

    monkeypatch.setattr(publisher, "run", fake_run)

    publisher.base_branch_snapshot_on_public_main(tmp_path)

    assert calls == [
        (["git", "fetch", "serverclaw", "main"], tmp_path),
        (["git", "reset", "--soft", "serverclaw/main"], tmp_path),
    ]
