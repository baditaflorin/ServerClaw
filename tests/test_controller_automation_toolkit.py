from __future__ import annotations

from pathlib import Path

import controller_automation_toolkit as toolkit


def test_yaml_fallback_keeps_colon_scalars_in_lists(tmp_path: Path) -> None:
    payload_path = tmp_path / "operators.yaml"
    payload_path.write_text(
        """
operators:
  - tailscale:
      tags:
        - tag:platform-operator
        - https://example.com/path
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = toolkit._load_yaml_without_pyyaml(payload_path)

    assert payload["operators"][0]["tailscale"]["tags"] == [
        "tag:platform-operator",
        "https://example.com/path",
    ]


def test_yaml_fallback_still_parses_inline_list_mappings(tmp_path: Path) -> None:
    payload_path = tmp_path / "items.yaml"
    payload_path.write_text(
        """
items:
  - id: sample
    enabled: true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = toolkit._load_yaml_without_pyyaml(payload_path)

    assert payload["items"] == [{"id": "sample", "enabled": True}]
