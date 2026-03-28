from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .ledger import LedgerWriter
from .repo import load_json, repo_path


SCHEMA_PATH = repo_path("docs", "schema", "mutation-audit-event.json")
DEFAULT_LOCAL_SINK_PATH = repo_path(".local", "state", "mutation-audit", "mutation-audit.jsonl")
DEFAULT_LOKI_LABELS = {"job": "mutation-audit"}
ALLOWED_ACTOR_CLASSES = {"operator", "agent", "service", "automation"}
ALLOWED_SURFACES = {"ansible", "windmill", "openbao", "nats", "command-catalog", "manual"}
ALLOWED_OUTCOMES = {"success", "failure", "rejected"}
ACTION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_str(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_enum(value: Any, path: str, allowed: set[str]) -> str:
    value = require_str(value, path)
    if value not in allowed:
        raise ValueError(f"{path} must be one of {sorted(allowed)}")
    return value


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_correlation_id(surface: str, action: str) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{surface}:{action}:{timestamp}"


def validate_iso8601(value: str, path: str) -> str:
    normalized = value.replace("Z", "+00:00")
    try:
        dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{path} must use ISO-8601 date-time format") from exc
    return value


def load_mutation_audit_schema() -> dict[str, Any]:
    return load_json(SCHEMA_PATH)


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    event = require_mapping(event, "mutation audit event")
    validate_iso8601(require_str(event.get("ts"), "mutation audit event.ts"), "mutation audit event.ts")

    actor = require_mapping(event.get("actor"), "mutation audit event.actor")
    require_enum(actor.get("class"), "mutation audit event.actor.class", ALLOWED_ACTOR_CLASSES)
    require_str(actor.get("id"), "mutation audit event.actor.id")

    action = require_str(event.get("action"), "mutation audit event.action")
    if not ACTION_PATTERN.match(action):
        raise ValueError("mutation audit event.action must use lowercase identifier format")

    require_enum(event.get("surface"), "mutation audit event.surface", ALLOWED_SURFACES)
    require_str(event.get("target"), "mutation audit event.target")
    require_enum(event.get("outcome"), "mutation audit event.outcome", ALLOWED_OUTCOMES)
    require_str(event.get("correlation_id"), "mutation audit event.correlation_id")
    require_str(event.get("evidence_ref"), "mutation audit event.evidence_ref", allow_empty=True)

    unexpected = sorted(
        set(event.keys()) - {"ts", "actor", "surface", "action", "target", "outcome", "correlation_id", "evidence_ref"}
    )
    if unexpected:
        raise ValueError(f"mutation audit event contains unsupported keys: {', '.join(unexpected)}")
    return event


def build_event(
    *,
    actor_class: str,
    actor_id: str,
    surface: str,
    action: str,
    target: str,
    outcome: str,
    correlation_id: str | None = None,
    evidence_ref: str = "",
    ts: str | None = None,
) -> dict[str, Any]:
    event = {
        "ts": ts or utc_now_iso(),
        "actor": {"class": actor_class, "id": actor_id},
        "surface": surface,
        "action": action,
        "target": target,
        "outcome": outcome,
        "correlation_id": correlation_id or default_correlation_id(surface, action),
        "evidence_ref": evidence_ref,
    }
    return validate_event(event)


def resolve_local_sink_path(file_path: str | None = None) -> Path | None:
    candidate = file_path if file_path is not None else os.environ.get("LV3_MUTATION_AUDIT_FILE")
    if candidate is None:
        return DEFAULT_LOCAL_SINK_PATH
    candidate = candidate.strip()
    if not candidate or candidate.lower() == "off":
        return None
    return Path(candidate).expanduser()


def resolve_loki_url(loki_url: str | None = None) -> str | None:
    candidate = loki_url if loki_url is not None else os.environ.get("LV3_MUTATION_AUDIT_LOKI_URL")
    if candidate is None:
        return None
    candidate = candidate.strip()
    if not candidate or candidate.lower() == "off":
        return None
    return candidate


def resolve_loki_labels(extra_labels: dict[str, str] | None, event: dict[str, Any]) -> dict[str, str]:
    labels = dict(DEFAULT_LOKI_LABELS)
    labels.update(
        {
            "surface": event["surface"],
            "outcome": event["outcome"],
            "actor_class": event["actor"]["class"],
        }
    )
    env_labels = os.environ.get("LV3_MUTATION_AUDIT_LOKI_LABELS", "").strip()
    if env_labels:
        parsed = require_mapping(json.loads(env_labels), "LV3_MUTATION_AUDIT_LOKI_LABELS")
        for key, value in parsed.items():
            labels[require_str(key, "LV3_MUTATION_AUDIT_LOKI_LABELS key")] = require_str(
                value, f"LV3_MUTATION_AUDIT_LOKI_LABELS.{key}"
            )
    if extra_labels:
        for key, value in extra_labels.items():
            labels[require_str(key, "loki label key")] = require_str(value, f"loki label {key}")
    return labels


def append_event_to_file(event: dict[str, Any], sink_path: Path) -> None:
    sink_path.parent.mkdir(parents=True, exist_ok=True)
    with sink_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def push_event_to_loki(event: dict[str, Any], loki_url: str, labels: dict[str, str]) -> None:
    timestamp_ns = str(int(dt.datetime.fromisoformat(event["ts"].replace("Z", "+00:00")).timestamp() * 1_000_000_000))
    payload = {
        "streams": [
            {
                "stream": labels,
                "values": [[timestamp_ns, json.dumps(event, sort_keys=True)]],
            }
        ]
    }
    request = urllib.request.Request(
        loki_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status >= 300:
                raise RuntimeError(f"Loki push failed with HTTP {response.status}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Loki push failed: {exc}") from exc


def emit_event(
    event: dict[str, Any],
    *,
    file_path: str | None = None,
    loki_url: str | None = None,
    loki_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    event = validate_event(event)
    sink_path = resolve_local_sink_path(file_path)
    if sink_path is not None:
        append_event_to_file(event, sink_path)

    resolved_loki_url = resolve_loki_url(loki_url)
    if resolved_loki_url:
        push_event_to_loki(event, resolved_loki_url, resolve_loki_labels(loki_labels, event))

    ledger_dsn = os.environ.get("LV3_LEDGER_DSN", "").strip()
    if ledger_dsn and ledger_dsn.lower() != "off":
        LedgerWriter(dsn=ledger_dsn).write_mutation_audit_event(event)

    return event


def emit_event_best_effort(
    event: dict[str, Any],
    *,
    context: str,
    stderr: Any = sys.stderr,
    file_path: str | None = None,
    loki_url: str | None = None,
    loki_labels: dict[str, str] | None = None,
) -> bool:
    try:
        emit_event(event, file_path=file_path, loki_url=loki_url, loki_labels=loki_labels)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Mutation audit warning ({context}): {exc}", file=stderr)
        return False
    return True
