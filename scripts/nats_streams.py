#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from controller_automation_toolkit import emit_cli_error, load_yaml, repo_path
from drift_lib import connect_nats, load_controller_context, nats_tunnel, resolve_nats_credentials
from platform.events import build_envelope

CONFIG_PATH = repo_path("config", "nats-streams.yaml")
DEFAULT_NATS_URL = "nats://127.0.0.1:{port}"


@dataclass(frozen=True)
class DesiredStream:
    name: str
    subjects: tuple[str, ...]
    retention: str
    max_age_seconds: int
    storage: str
    replicas: int
    discard: str
    duplicate_window_seconds: int
    description: str | None = None


def parse_duration(value: str) -> int:
    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    raw = value.strip().lower()
    if len(raw) < 2 or raw[-1] not in units:
        raise ValueError(f"unsupported duration '{value}'")
    amount = int(raw[:-1])
    return amount * units[raw[-1]]


def load_desired_streams(path: Path = CONFIG_PATH) -> list[DesiredStream]:
    payload = load_yaml(path)
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams:
        raise ValueError("config/nats-streams.yaml must define at least one stream")
    desired: list[DesiredStream] = []
    for entry in streams:
        if not isinstance(entry, dict):
            raise ValueError("each stream entry must be a mapping")
        desired.append(
            DesiredStream(
                name=str(entry["name"]),
                subjects=tuple(str(subject) for subject in entry.get("subjects", [])),
                retention=str(entry["retention"]),
                max_age_seconds=parse_duration(str(entry["max_age"])),
                storage=str(entry["storage"]),
                replicas=int(entry["replicas"]),
                discard=str(entry["discard"]),
                duplicate_window_seconds=parse_duration(str(entry["duplicate_window"])),
                description=str(entry["description"]) if entry.get("description") else None,
            )
        )
    return desired


def stream_config_kwargs(stream: DesiredStream) -> dict[str, Any]:
    from nats.js.api import DiscardPolicy, RetentionPolicy, StorageType

    kwargs: dict[str, Any] = {
        "name": stream.name,
        "subjects": list(stream.subjects),
        "retention": RetentionPolicy(stream.retention),
        "max_age": stream.max_age_seconds,
        "storage": StorageType(stream.storage),
        "num_replicas": stream.replicas,
        "discard": DiscardPolicy(stream.discard),
        "duplicate_window": stream.duplicate_window_seconds,
    }
    if stream.description:
        kwargs["description"] = stream.description
    return kwargs


def describe_live_stream(info: Any) -> dict[str, Any]:
    config = info.config

    def scalar(value: Any) -> Any:
        return getattr(value, "value", value)

    return {
        "name": config.name,
        "subjects": list(config.subjects or []),
        "retention": scalar(config.retention) if config.retention else None,
        "max_age_seconds": int(config.max_age or 0),
        "storage": scalar(config.storage) if config.storage else None,
        "replicas": config.num_replicas,
        "discard": scalar(config.discard) if config.discard else None,
        "duplicate_window_seconds": int(config.duplicate_window or 0),
        "description": config.description,
    }


def describe_desired_stream(stream: DesiredStream) -> dict[str, Any]:
    return asdict(stream) | {"subjects": list(stream.subjects)}


def diff_streams(desired: DesiredStream, live: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    desired_payload = describe_desired_stream(desired)
    if live is None:
        return {key: {"desired": value, "live": None} for key, value in desired_payload.items()}
    diff: dict[str, dict[str, Any]] = {}
    for key, desired_value in desired_payload.items():
        live_value = live.get(key)
        if live_value != desired_value:
            diff[key] = {"desired": desired_value, "live": live_value}
    return diff


async def fetch_stream_info(js: Any, stream_name: str) -> Any | None:
    from nats.js.errors import NotFoundError

    try:
        return await js.stream_info(stream_name)
    except NotFoundError:
        return None


async def check_streams_async(*, apply: bool) -> list[dict[str, Any]]:
    desired_streams = load_desired_streams()
    context = load_controller_context()
    credentials = resolve_nats_credentials(context)
    results: list[dict[str, Any]] = []

    with nats_tunnel(context) as local_port:
        nc = await connect_nats(DEFAULT_NATS_URL.format(port=local_port), credentials)
        js = nc.jetstream()
        try:
            for desired in desired_streams:
                live_info = await fetch_stream_info(js, desired.name)
                live_description = describe_live_stream(live_info) if live_info else None
                diff = diff_streams(desired, live_description)
                action = "none"
                if diff and apply:
                    from nats.js.api import StreamConfig

                    config = StreamConfig(**stream_config_kwargs(desired))
                    if live_info is None:
                        await js.add_stream(config=config)
                        action = "created"
                    else:
                        await js.update_stream(config=config)
                        action = "updated"
                    refreshed = await js.stream_info(desired.name)
                    live_description = describe_live_stream(refreshed)
                    diff = diff_streams(desired, live_description)
                elif diff:
                    action = "drift"

                results.append(
                    {
                        "name": desired.name,
                        "action": action,
                        "desired": describe_desired_stream(desired),
                        "live": live_description,
                        "diff": diff,
                    }
                )
        finally:
            await nc.close()

    return results


async def smoke_publish_async() -> dict[str, Any]:
    context = load_controller_context()
    credentials = resolve_nats_credentials(context)
    subject = "platform.findings.observation"
    payload = {
        "check": "adr-0124-live-apply-smoke",
        "severity": "ok",
        "summary": "ADR 0124 live apply smoke publish",
        "details": "Controller-side verification publish for the PLATFORM_EVENTS stream.",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": str(uuid.uuid4()),
    }
    envelope = build_envelope(subject, payload, actor_id="operator/nats-streams")

    with nats_tunnel(context) as local_port:
        nc = await connect_nats(DEFAULT_NATS_URL.format(port=local_port), credentials)
        js = nc.jetstream()
        try:
            ack = await js.publish(subject, json.dumps(envelope, separators=(",", ":")).encode())
            return {
                "subject": subject,
                "stream": ack.stream,
                "seq": ack.seq,
                "duplicate": ack.duplicate,
            }
        finally:
            await nc.close()


def print_results(results: list[dict[str, Any]]) -> None:
    for result in results:
        print(f"{result['name']}: {result['action']}")
        if result["diff"]:
            print(json.dumps(result["diff"], indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or apply repo-managed NATS JetStream streams.")
    parser.add_argument("--apply", action="store_true", help="Apply stream changes to the live NATS runtime.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    parser.add_argument(
        "--smoke-publish",
        action="store_true",
        help="Publish one canonical ADR-0124 smoke event after the stream check.",
    )
    args = parser.parse_args()

    try:
        results = asyncio.run(check_streams_async(apply=args.apply))
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("NATS streams", exc)

    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        print_results(results)

    smoke_failure = False
    if args.smoke_publish:
        try:
            smoke_result = asyncio.run(smoke_publish_async())
        except Exception as exc:  # noqa: BLE001
            smoke_failure = True
            if args.json:
                print(json.dumps({"smoke_publish_error": str(exc)}, indent=2, sort_keys=True))
            else:
                print(f"smoke_publish_error: {exc}")
        else:
            if args.json:
                print(json.dumps({"smoke_publish": smoke_result}, indent=2, sort_keys=True))
            else:
                print(f"smoke_publish: {json.dumps(smoke_result, sort_keys=True)}")

    has_drift = any(result["diff"] for result in results)
    return 1 if has_drift or smoke_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
