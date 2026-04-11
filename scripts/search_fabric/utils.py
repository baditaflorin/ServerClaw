from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


UTC = UTC

METADATA_PATTERN = re.compile(r"^-\s+(?P<key>[^:]+):\s+(?P<value>.+?)\s*$")
H1_PATTERN = re.compile(r"^#\s+(?P<title>.+?)\s*$")
WORD_PATTERN = re.compile(r"[a-z0-9]+")
ELLIPSIS = "..."
MAX_BODY_CHARS = 2000


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return default


def load_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        if path.name == "search-synonyms.yaml":
            return parse_synonyms_yaml(raw)
        return default
    return yaml.safe_load(raw)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def normalize_text(value: str) -> str:
    return " ".join(WORD_PATTERN.findall(value.lower()))


def tokenize(value: str) -> list[str]:
    return WORD_PATTERN.findall(value.lower())


def trigrams(value: str) -> set[str]:
    normalized = normalize_text(value).replace(" ", "")
    if not normalized:
        return set()
    if len(normalized) < 3:
        return {normalized}
    return {normalized[index : index + 3] for index in range(len(normalized) - 2)}


def similarity(left: str, right: str) -> float:
    left_trigrams = trigrams(left)
    right_trigrams = trigrams(right)
    if not left_trigrams or not right_trigrams:
        return 0.0
    overlap = len(left_trigrams & right_trigrams)
    return overlap / max(len(left_trigrams | right_trigrams), 1)


def truncate_body(text: str, *, max_chars: int = MAX_BODY_CHARS) -> str:
    collapsed = "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - len(ELLIPSIS)].rstrip() + ELLIPSIS


def sha256_text(*parts: str) -> str:
    payload = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def first_heading(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        match = H1_PATTERN.match(line.strip())
        if match:
            return match.group("title").strip()
    return fallback


def metadata_from_markdown(markdown: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in markdown.splitlines():
        match = METADATA_PATTERN.match(line.strip())
        if not match:
            if metadata:
                break
            continue
        key = normalize_text(match.group("key")).replace(" ", "_")
        metadata[key] = match.group("value").strip()
    return metadata


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {flatten_text(item)}" for key, item in value.items())
    if isinstance(value, Iterable):
        return "\n".join(flatten_text(item) for item in value)
    return str(value)


def parse_synonyms_yaml(raw: str) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    active_list: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "schema_version: 1.0.0" or stripped == "groups:":
            continue
        if stripped.startswith("- canonical:"):
            if current is not None:
                groups.append(current)
            current = {"canonical": stripped.split(":", 1)[1].strip(), "aliases": [], "expand": []}
            active_list = None
            continue
        if current is None:
            continue
        if stripped.startswith("aliases:"):
            inline = stripped.split(":", 1)[1].strip()
            if inline.startswith("[") and inline.endswith("]"):
                current["aliases"] = [item.strip() for item in inline[1:-1].split(",") if item.strip()]
                active_list = None
            else:
                active_list = "aliases"
            continue
        if stripped.startswith("expand:"):
            inline = stripped.split(":", 1)[1].strip()
            if inline.startswith("[") and inline.endswith("]"):
                current["expand"] = [item.strip() for item in inline[1:-1].split(",") if item.strip()]
                active_list = None
            else:
                active_list = "expand"
            continue
        if stripped.startswith("- ") and active_list:
            current[active_list].append(stripped[2:].strip())
    if current is not None:
        groups.append(current)
    return {"groups": groups}
