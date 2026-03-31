#!/usr/bin/env python3
"""Resolve worker-local integration overrides for Windmill-managed jobs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def _normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized.rstrip("/")


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_proc_env_var(*names: str, proc_environ_path: Path = Path("/proc/1/environ")) -> str | None:
    if not proc_environ_path.exists():
        return None
    try:
        entries = proc_environ_path.read_bytes().split(b"\0")
    except OSError:
        return None
    for name in names:
        prefix = f"{name}=".encode("utf-8")
        for entry in entries:
            if entry.startswith(prefix):
                return _normalize_url(entry.split(b"=", 1)[1].decode("utf-8", errors="ignore"))
    return None


def _base_url_from_probe_url(value: str | None) -> str | None:
    normalized = _normalize_url(value)
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def resolve_windmill_integration_url(repo_root: Path) -> str | None:
    explicit = _normalize_url(os.environ.get("LV3_INTEGRATION_WINDMILL_URL"))
    if explicit:
        return explicit

    worker_override = _normalize_url(os.environ.get("LV3_WINDMILL_BASE_URL")) or _read_proc_env_var(
        "LV3_WINDMILL_BASE_URL"
    )
    if worker_override:
        return worker_override

    catalog = _load_json(repo_root / "config" / "health-probe-catalog.json")
    services = catalog.get("services")
    if not isinstance(services, dict):
        return None
    windmill = services.get("windmill")
    if not isinstance(windmill, dict):
        return None
    for probe_kind in ("liveness", "readiness"):
        probe = windmill.get(probe_kind)
        if not isinstance(probe, dict):
            continue
        url = _base_url_from_probe_url(probe.get("url") if isinstance(probe.get("url"), str) else None)
        if url:
            return url
    return None


def integration_env_overrides(repo_root: Path) -> dict[str, str]:
    overrides: dict[str, str] = {}
    windmill_url = resolve_windmill_integration_url(repo_root)
    if windmill_url:
        overrides["LV3_INTEGRATION_WINDMILL_URL"] = windmill_url
    return overrides
