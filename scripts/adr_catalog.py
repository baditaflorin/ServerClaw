#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
from typing import Any

from controller_automation_toolkit import repo_path


ADR_DIR = repo_path("docs", "adr")


def resolve_service_adr_path(service: dict[str, Any], *, adr_dir: Path = ADR_DIR) -> Path | None:
    adr_file = service.get("adr_file")
    if isinstance(adr_file, str) and adr_file.strip():
        return repo_path(adr_file)

    adr = service.get("adr")
    if not isinstance(adr, str) or not adr.strip():
        return None

    matches = sorted(adr_dir.glob(f"{adr}-*.md"))
    if not matches:
        return None
    return matches[0]
