from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
LEDGER_EVENT_TYPES_PATH = REPO_ROOT / "config" / "ledger-event-types.yaml"
LEDGER_DSN_ENV = "LV3_LEDGER_DSN"


def ensure_scripts_on_path() -> None:
    scripts_dir = str(SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def load_module_from_repo(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(module_name, module)
    spec.loader.exec_module(module)
    return module


def load_event_type_registry(path: Path = LEDGER_EVENT_TYPES_PATH) -> list[str]:
    event_types: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if not line.startswith("- "):
            raise ValueError(f"{path} must contain a YAML list of event types")
        value = line[2:].strip()
        if not value:
            raise ValueError(f"{path} contains an empty event type entry")
        event_types.append(value)
    if not event_types:
        raise ValueError(f"{path} does not define any event types")
    if len(set(event_types)) != len(event_types):
        raise ValueError(f"{path} contains duplicate event types")
    return event_types


def normalize_timestamp(value: dt.datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    raise TypeError(f"unsupported timestamp value: {value!r}")


def dumps_jsonb(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def loads_jsonb(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped[0] in "[{":
            return json.loads(stripped)
    return value


def row_to_mapping(cursor: Any, row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    description = getattr(cursor, "description", None) or []
    columns = [column[0] for column in description]
    return dict(zip(columns, row, strict=False))


def normalize_event_row(cursor: Any, row: Any) -> dict[str, Any]:
    payload = row_to_mapping(cursor, row)
    for key in ("before_state", "after_state", "receipt", "metadata"):
        payload[key] = loads_jsonb(payload.get(key))
    return payload


def resolve_connection(
    *,
    dsn: str | None = None,
    connection: Any = None,
    connect: Callable[[str], Any] | None = None,
) -> tuple[Any, bool]:
    if connection is not None:
        return connection, False

    resolved_dsn = (dsn or os.environ.get(LEDGER_DSN_ENV, "")).strip()
    if not resolved_dsn or resolved_dsn.lower() == "off":
        raise RuntimeError(f"{LEDGER_DSN_ENV} is not configured")

    if connect is None:
        try:
            import psycopg2  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg2 is required for ledger database access") from exc
        connect = psycopg2.connect

    return connect(resolved_dsn), True
