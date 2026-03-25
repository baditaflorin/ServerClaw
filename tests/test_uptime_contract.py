from __future__ import annotations

import json
from pathlib import Path

import uptime_contract


def test_generated_monitors_match_repo_file() -> None:
    catalog = uptime_contract.load_health_probe_catalog()
    monitors = uptime_contract.build_uptime_monitors(catalog)
    rendered = uptime_contract.render_uptime_monitors(monitors)

    assert rendered == uptime_contract.UPTIME_MONITORS_PATH.read_text(encoding="utf-8")
    assert any(monitor["name"] == "Windmill Private" for monitor in monitors)
    assert any(monitor["name"] == "Homepage Public" for monitor in monitors)


def test_outputs_match_detects_stale_file(tmp_path: Path) -> None:
    output_path = tmp_path / "monitors.json"
    output_path.write_text(json.dumps([]) + "\n", encoding="utf-8")

    assert not uptime_contract.outputs_match(output_path=output_path)
