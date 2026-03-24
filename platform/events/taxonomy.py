from __future__ import annotations

import datetime as dt
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
EVENT_TAXONOMY_PATH = REPO_ROOT / "config" / "event-taxonomy.yaml"


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _require_string_list(value: Any, path: str) -> list[str]:
    items = _require_list(value, path)
    return [_require_str(item, f"{path}[{index}]") for index, item in enumerate(items)]


@lru_cache(maxsize=1)
def load_event_taxonomy(path: str | Path | None = None) -> dict[str, Any]:
    taxonomy_path = Path(path) if path is not None else EVENT_TAXONOMY_PATH
    data = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    if data is None:
        raise ValueError(f"{taxonomy_path} is empty")
    return _require_mapping(data, str(taxonomy_path))


@lru_cache(maxsize=1)
def load_topic_index(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    catalog = load_event_taxonomy(path)
    schema_version = _require_str(catalog.get("schema_version"), "event-taxonomy.schema_version")
    if schema_version != "1.0.0":
        raise ValueError("event-taxonomy.schema_version must be '1.0.0'")

    event_schema_version = _require_str(
        catalog.get("event_schema_version"),
        "event-taxonomy.event_schema_version",
    )
    domains = _require_mapping(catalog.get("domains"), "event-taxonomy.domains")

    topic_index: dict[str, dict[str, Any]] = {}
    for domain_name, domain_value in domains.items():
        domain = _require_mapping(domain_value, f"event-taxonomy.domains.{domain_name}")
        _require_str(domain.get("description"), f"event-taxonomy.domains.{domain_name}.description")
        topics = _require_list(domain.get("topics"), f"event-taxonomy.domains.{domain_name}.topics")
        if not topics:
            raise ValueError(f"event-taxonomy.domains.{domain_name}.topics must not be empty")

        for topic_index_value, topic_value in enumerate(topics):
            topic = _require_mapping(
                topic_value,
                f"event-taxonomy.domains.{domain_name}.topics[{topic_index_value}]",
            )
            name = _require_str(topic.get("name"), f"event-taxonomy topic {domain_name}[{topic_index_value}].name")
            if not name.startswith(f"platform.{domain_name}."):
                raise ValueError(
                    f"event-taxonomy topic '{name}' must start with 'platform.{domain_name}.'"
                )
            if name in topic_index:
                raise ValueError(f"duplicate event-taxonomy topic '{name}'")
            payload = _require_mapping(topic.get("payload"), f"event-taxonomy topic {name}.payload")
            required = _require_string_list(payload.get("required", []), f"event-taxonomy topic {name}.payload.required")
            topic_index[name] = {
                "domain": domain_name,
                "description": _require_str(topic.get("description"), f"event-taxonomy topic {name}.description"),
                "delivery": _require_str(topic.get("delivery"), f"event-taxonomy topic {name}.delivery"),
                "retention": _require_str(topic.get("retention"), f"event-taxonomy topic {name}.retention"),
                "status": _require_str(topic.get("status"), f"event-taxonomy topic {name}.status"),
                "producers": _require_string_list(topic.get("producers", []), f"event-taxonomy topic {name}.producers"),
                "payload_required": required,
                "event_schema_version": event_schema_version,
            }

    return topic_index


def validate_envelope_payload(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    topic_index = load_topic_index()
    spec = topic_index.get(topic)
    if spec is None:
        raise ValueError(f"unknown NATS topic '{topic}'")
    payload = _require_mapping(payload, f"payload for {topic}")
    missing = [key for key in spec["payload_required"] if key not in payload]
    if missing:
        raise ValueError(f"payload for {topic} is missing required keys: {', '.join(missing)}")
    return spec


def _isoformat(value: dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_envelope(
    topic: str,
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
    schema_ver: str | None = None,
    ts: str | dt.datetime | None = None,
    actor_id: str | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    spec = validate_envelope_payload(topic, payload)
    if ts is None:
        timestamp = _isoformat(dt.datetime.now(dt.timezone.utc))
    elif isinstance(ts, dt.datetime):
        timestamp = _isoformat(ts)
    else:
        timestamp = _require_str(ts, f"event timestamp for {topic}")

    envelope = {
        "event_id": event_id or str(uuid.uuid4()),
        "topic": topic,
        "schema_ver": schema_ver or spec["event_schema_version"],
        "ts": timestamp,
        "payload": payload,
    }
    if actor_id:
        envelope["actor_id"] = actor_id
    if context_id:
        envelope["context_id"] = context_id
    return envelope
