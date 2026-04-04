from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ntfy_publish.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ntfy_publish = _load_module(SCRIPT_PATH, "ntfy_publish")


def test_normalize_sequence_id_preserves_ntfy_safe_values() -> None:
    assert ntfy_publish.normalize_sequence_id("ws-0299-live-apply_20260403") == "ws-0299-live-apply_20260403"


def test_normalize_sequence_id_rewrites_invalid_characters_with_stable_hash_suffix() -> None:
    requested = "ansible:ansible:test-correlation:failure"

    normalized = ntfy_publish.normalize_sequence_id(requested)

    assert re.fullmatch(r"[-_A-Za-z0-9]{1,64}", normalized)
    assert ":" not in normalized
    assert normalized.endswith(f"-{hashlib.sha256(requested.encode('utf-8')).hexdigest()[:12]}")


def test_normalize_sequence_id_shortens_long_values() -> None:
    requested = "ansible-" + ("segment-" * 12) + "failure"

    normalized = ntfy_publish.normalize_sequence_id(requested)

    assert len(normalized) <= 64
    assert re.fullmatch(r"[-_A-Za-z0-9]{1,64}", normalized)


def test_main_dry_run_reports_normalized_sequence_id(capsys, tmp_path: Path) -> None:
    registry_path = tmp_path / "topics.yaml"
    registry_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0.0"',
                "publication:",
                '  public_base_url: "https://ntfy.example.com"',
                "topics:",
                "  platform-ansible-info:",
                '    default_title: "Ansible info"',
                "    default_tags:",
                "      - ops",
                "users:",
                "  ansible:",
                '    username: "ansible"',
                "    publish_topics:",
                "      - platform-ansible-info",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    requested_sequence_id = "ansible:ansible:test-correlation:success"

    exit_code = ntfy_publish.main(
        [
            "--registry",
            str(registry_path),
            "--secret-manifest",
            str(tmp_path / "missing-secrets.json"),
            "--publisher",
            "ansible",
            "--topic",
            "platform-ansible-info",
            "--message",
            "controller smoke",
            "--token",
            "test-token",
            "--sequence-id",
            requested_sequence_id,
            "--dry-run",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requested_sequence_id"] == requested_sequence_id
    assert payload["sequence_id"] == ntfy_publish.normalize_sequence_id(requested_sequence_id)
    assert payload["headers"]["X-Sequence-ID"] == payload["sequence_id"]


def test_read_secret_file_supports_repo_relative_paths(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    secret_file = repo_root / ".local" / "ntfy" / "publisher-token.txt"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("publisher-token\n", encoding="utf-8")

    monkeypatch.setattr(ntfy_publish, "REPO_ROOT", repo_root)

    assert ntfy_publish.read_secret_file(".local/ntfy/publisher-token.txt") == "publisher-token"
