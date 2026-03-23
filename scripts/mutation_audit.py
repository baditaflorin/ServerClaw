#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Final

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


REPO_ROOT: Final[Path] = repo_path()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.ledger import LedgerWriter  # noqa: E402


SCHEMA_PATH: Final[Path] = repo_path("docs", "schema", "mutation-audit-event.json")
DEFAULT_LOCAL_SINK_PATH: Final[Path] = repo_path(
    ".local", "state", "mutation-audit", "mutation-audit.jsonl"
)
DEFAULT_LOKI_LABELS: Final[dict[str, str]] = {"job": "mutation-audit"}
ALLOWED_ACTOR_CLASSES: Final[set[str]] = {"operator", "agent", "service", "automation"}
ALLOWED_SURFACES: Final[set[str]] = {
    "ansible",
    "windmill",
    "openbao",
    "nats",
    "command-catalog",
    "manual",
}
ALLOWED_OUTCOMES: Final[set[str]] = {"success", "failure", "rejected"}
ACTION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


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


def validate_mutation_audit_schema(schema: dict[str, Any]) -> None:
    schema = require_mapping(schema, str(SCHEMA_PATH))
    require_str(schema.get("$schema"), "docs/schema/mutation-audit-event.json.$schema")
    if schema.get("type") != "object":
        raise ValueError("docs/schema/mutation-audit-event.json.type must be 'object'")
    if schema.get("additionalProperties") is not False:
        raise ValueError("docs/schema/mutation-audit-event.json.additionalProperties must be false")

    required = schema.get("required")
    if required != [
        "ts",
        "actor",
        "surface",
        "action",
        "target",
        "outcome",
        "correlation_id",
        "evidence_ref",
    ]:
        raise ValueError("docs/schema/mutation-audit-event.json.required must match the canonical event fields")

    properties = require_mapping(schema.get("properties"), "docs/schema/mutation-audit-event.json.properties")
    actor = require_mapping(properties.get("actor"), "docs/schema/mutation-audit-event.json.properties.actor")
    actor_props = require_mapping(
        actor.get("properties"),
        "docs/schema/mutation-audit-event.json.properties.actor.properties",
    )

    if set(actor_props.get("class", {}).get("enum", [])) != ALLOWED_ACTOR_CLASSES:
        raise ValueError("docs/schema/mutation-audit-event.json actor.class enum must match the canonical classes")
    if set(properties.get("surface", {}).get("enum", [])) != ALLOWED_SURFACES:
        raise ValueError("docs/schema/mutation-audit-event.json surface enum must match the canonical surfaces")
    if set(properties.get("outcome", {}).get("enum", [])) != ALLOWED_OUTCOMES:
        raise ValueError("docs/schema/mutation-audit-event.json outcome enum must match the canonical outcomes")


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

    unexpected = sorted(set(event.keys()) - {"ts", "actor", "surface", "action", "target", "outcome", "correlation_id", "evidence_ref"})
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
        "actor": {
            "class": actor_class,
            "id": actor_id,
        },
        "surface": surface,
        "action": action,
        "target": target,
        "outcome": outcome,
        "correlation_id": correlation_id or default_correlation_id(surface, action),
        "evidence_ref": evidence_ref,
    }
    return validate_event(event)


def resolve_local_sink_path(file_path: str | None = None) -> Path | None:
    candidate = file_path
    if candidate is None:
        candidate = os.environ.get("LV3_MUTATION_AUDIT_FILE")
    if candidate is None:
        return DEFAULT_LOCAL_SINK_PATH
    candidate = candidate.strip()
    if not candidate or candidate.lower() == "off":
        return None
    return Path(candidate).expanduser()


def resolve_loki_url(loki_url: str | None = None) -> str | None:
    candidate = loki_url
    if candidate is None:
        candidate = os.environ.get("LV3_MUTATION_AUDIT_LOKI_URL")
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
        parsed = json.loads(env_labels)
        parsed = require_mapping(parsed, "LV3_MUTATION_AUDIT_LOKI_LABELS")
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


def parse_loki_labels(value: str) -> dict[str, str]:
    parsed = json.loads(value)
    parsed = require_mapping(parsed, "--loki-labels")
    return {require_str(key, "--loki-labels key"): require_str(val, f"--loki-labels.{key}") for key, val in parsed.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or emit structured mutation audit events.")
    parser.add_argument("--validate-schema", action="store_true", help="Validate the canonical event schema.")
    parser.add_argument("--emit", action="store_true", help="Emit one mutation audit event.")
    parser.add_argument("--actor-class", help="Event actor class.")
    parser.add_argument("--actor-id", help="Event actor id.")
    parser.add_argument("--surface", default="manual", help="Mutation surface.")
    parser.add_argument("--action", help="Mutation action identifier.")
    parser.add_argument("--target", help="Mutation target.")
    parser.add_argument("--outcome", default="success", help="Mutation outcome.")
    parser.add_argument("--correlation-id", help="Correlation id.")
    parser.add_argument("--evidence-ref", default="", help="Receipt path or related evidence reference.")
    parser.add_argument("--file-path", help="Override the local JSONL sink path.")
    parser.add_argument("--loki-url", help="Override the Loki push URL.")
    parser.add_argument(
        "--loki-labels",
        help='JSON object with extra Loki labels, for example {"environment":"lab"}.',
    )
    args = parser.parse_args()

    try:
        if args.validate_schema:
            validate_mutation_audit_schema(load_mutation_audit_schema())
            print(f"Mutation audit schema OK: {SCHEMA_PATH}")
            return 0

        if args.emit:
            if not args.actor_class:
                raise ValueError("--emit requires --actor-class")
            if not args.actor_id:
                raise ValueError("--emit requires --actor-id")
            if not args.action:
                raise ValueError("--emit requires --action")
            if not args.target:
                raise ValueError("--emit requires --target")

            event = build_event(
                actor_class=args.actor_class,
                actor_id=args.actor_id,
                surface=args.surface,
                action=args.action,
                target=args.target,
                outcome=args.outcome,
                correlation_id=args.correlation_id,
                evidence_ref=args.evidence_ref,
            )
            emit_event(
                event,
                file_path=args.file_path,
                loki_url=args.loki_url,
                loki_labels=parse_loki_labels(args.loki_labels) if args.loki_labels else None,
            )
            print(json.dumps(event, indent=2))
            return 0

        parser.print_help()
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Mutation audit", exc)


if __name__ == "__main__":
    sys.exit(main())
