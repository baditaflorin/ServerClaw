from __future__ import annotations

import json
from pathlib import Path

import vmid_allocator


def test_parse_range_parses_expected_bounds() -> None:
    assert vmid_allocator.parse_range("9100:9199") == (9100, 9199)


def test_allocate_free_vmid_skips_used_values() -> None:
    assert vmid_allocator.allocate_free_vmid({9100, 9101, 9103}, 9100, 9105) == 9102


def test_parse_cluster_vmids_accepts_int_and_string_values() -> None:
    payload = {"data": [{"vmid": 9100}, {"vmid": "9101"}, {"vmid": "bad"}]}
    assert vmid_allocator.parse_cluster_vmids(payload) == {9100, 9101}


def test_read_api_credentials_uses_token_file(tmp_path: Path) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps(
            {
                "api_url": "https://proxmox.example.invalid:8006/api2/json",
                "full_token_id": "lv3-automation@pve!primary",
                "value": "secret",
            }
        )
    )
    endpoint, api_token = vmid_allocator.read_api_credentials(token_file=token_path)
    assert endpoint == "https://proxmox.example.invalid:8006/api2/json"
    assert api_token == "lv3-automation@pve!primary=secret"
