#!/usr/bin/env python3
"""Allocate free Proxmox VMIDs for ephemeral fixtures."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RANGE = "910:979"
DEFAULT_SECRET_MANIFEST = REPO_ROOT / "config" / "controller-local-secrets.json"


def parse_range(value: str) -> tuple[int, int]:
    start_text, separator, end_text = value.partition(":")
    if separator != ":":
        raise ValueError("VMID range must look like 910:979")
    start = int(start_text)
    end = int(end_text)
    if start <= 0 or end <= 0 or start > end:
        raise ValueError("VMID range must be positive and ascending")
    return start, end


def default_token_file(manifest_path: Path = DEFAULT_SECRET_MANIFEST) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return Path(manifest["secrets"]["proxmox_api_token_payload"]["path"])


def read_api_credentials(
    *,
    endpoint: str | None = None,
    api_token: str | None = None,
    token_file: Path | None = None,
) -> tuple[str, str]:
    resolved_endpoint = endpoint or os.environ.get("TF_VAR_proxmox_endpoint")
    resolved_token = api_token or os.environ.get("TF_VAR_proxmox_api_token")
    payload_path = token_file or default_token_file()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    return (
        resolved_endpoint or payload["api_url"],
        resolved_token or f"{payload['full_token_id']}={payload['value']}",
    )


def proxmox_api_insecure() -> bool:
    return os.environ.get("LV3_PROXMOX_API_INSECURE", "").strip().lower() in {"1", "true", "yes", "on"}


def proxmox_urlopen(request: urllib.request.Request, *, timeout: int):
    if proxmox_api_insecure():
        return urllib.request.urlopen(request, timeout=timeout, context=ssl._create_unverified_context())
    return urllib.request.urlopen(request, timeout=timeout)


def parse_cluster_vmids(payload: dict[str, Any]) -> set[int]:
    used_vmids: set[int] = set()
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        vmid = item.get("vmid")
        if isinstance(vmid, int):
            used_vmids.add(vmid)
        elif isinstance(vmid, str) and vmid.isdigit():
            used_vmids.add(int(vmid))
    return used_vmids


def fetch_cluster_vmids(endpoint: str, api_token: str) -> set[int]:
    api_root = endpoint.rstrip("/")
    request = urllib.request.Request(
        f"{api_root}/cluster/resources?type=vm",
        headers={"Authorization": f"PVEAPIToken={api_token}"},
    )
    with proxmox_urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_cluster_vmids(payload)


def allocate_free_vmid(used_vmids: set[int], start: int, end: int) -> int:
    for candidate in range(start, end + 1):
        if candidate not in used_vmids:
            return candidate
    raise RuntimeError(f"No free VMIDs remain in range {start}:{end}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--range", default=DEFAULT_RANGE, dest="vmid_range")
    parser.add_argument("--endpoint")
    parser.add_argument("--api-token")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument(
        "--used-vmid",
        action="append",
        default=[],
        help="Additional VMID already reserved outside Proxmox.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start, end = parse_range(args.vmid_range)
    endpoint, api_token = read_api_credentials(
        endpoint=args.endpoint,
        api_token=args.api_token,
        token_file=args.token_file,
    )
    used_vmids = fetch_cluster_vmids(endpoint, api_token)
    used_vmids.update(int(value) for value in args.used_vmid)
    print(allocate_free_vmid(used_vmids, start, end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
