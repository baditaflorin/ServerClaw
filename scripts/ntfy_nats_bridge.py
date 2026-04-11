#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def resolve_repo_root(script_path: Path | None = None) -> Path:
    candidate = (script_path or Path(__file__)).resolve()
    for parent in (candidate.parent, *candidate.parents):
        if (parent / "platform" / "__init__.py").exists() and (parent / "config").is_dir():
            return parent
    raise RuntimeError(f"Unable to resolve repository root from {candidate}")


REPO_ROOT = resolve_repo_root()

if str(REPO_ROOT / "scripts") not in os.sys.path:
    os.sys.path.insert(0, str(REPO_ROOT / "scripts"))

from controller_automation_toolkit import emit_cli_error, load_yaml


TOPIC_REGISTRY_PATH = REPO_ROOT / "config" / "ntfy" / "topics.yaml"
DEFAULT_STREAM = "PLATFORM_EVENTS"


def load_bridge_config(path: Path) -> dict[str, Any]:
    payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML object")
    windmill = payload.get("windmill")
    if not isinstance(windmill, dict):
        raise ValueError(f"{path}.windmill must be an object")
    bridge = windmill.get("bridge")
    if not isinstance(bridge, dict):
        raise ValueError(f"{path}.windmill.bridge must be an object")
    subjects = bridge.get("subjects")
    if not isinstance(subjects, list) or not subjects:
        raise ValueError(f"{path}.windmill.bridge.subjects must be a non-empty list")
    return bridge


def build_notification_message(subject: str, payload: Any, sequence_id: str) -> str:
    return json.dumps(
        {
            "subject": subject,
            "sequence_id": sequence_id,
            "payload": payload,
        },
        indent=2,
        sort_keys=True,
    )


async def connect_jetstream(nats_url: str, username: str, password: str):
    from nats.aio.client import Client as NATS

    async def error_cb(error: Exception) -> None:
        recorded_errors.append(error)

    nc = NATS()
    recorded_errors: list[Exception] = []
    nc._lv3_recorded_errors = recorded_errors
    await nc.connect(
        servers=[nats_url],
        user=username,
        password=password,
        error_cb=error_cb,
        connect_timeout=5,
        allow_reconnect=False,
        max_reconnect_attempts=0,
        reconnect_time_wait=0,
    )
    return nc, nc.jetstream()


def ensure_runtime_dependency() -> None:
    try:
        import nats  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised in Windmill, not local tests
        raise RuntimeError("nats-py is required") from exc


async def run_bridge_async(
    *,
    repo_root: Path,
    registry_path: Path,
    publish_script: Path,
    nats_url: str,
    nats_username: str,
    nats_password: str,
    ntfy_base_url: str,
    ntfy_token: str,
    dedupe_state_file: Path,
    max_messages_per_subject: int,
) -> dict[str, Any]:
    bridge = load_bridge_config(registry_path)
    nc, js = await connect_jetstream(nats_url, nats_username, nats_password)
    processed: list[dict[str, Any]] = []
    try:
        for item in bridge["subjects"]:
            subject = item["subject"]
            consumer = item["consumer"]
            sub = await js.pull_subscribe(subject, durable=consumer, stream=DEFAULT_STREAM)
            try:
                messages = await sub.fetch(batch=max_messages_per_subject, timeout=1)
            except TimeoutError:
                messages = []

            for msg in messages:
                metadata = getattr(msg, "metadata", None)
                stream_sequence = getattr(getattr(metadata, "sequence", None), "stream", None)
                sequence_id = f"{consumer}-{stream_sequence or 'unknown'}"
                try:
                    payload = json.loads(msg.data.decode("utf-8"))
                except json.JSONDecodeError:
                    payload = {"raw": msg.data.decode("utf-8", errors="replace")}

                message = build_notification_message(subject, payload, sequence_id)
                command = [
                    "python3",
                    str(publish_script),
                    "--registry",
                    str(registry_path),
                    "--publisher",
                    "windmill",
                    "--topic",
                    item["topic"],
                    "--base-url",
                    ntfy_base_url,
                    "--token",
                    ntfy_token,
                    "--title",
                    item["title"],
                    "--priority",
                    str(item["priority"]),
                    "--tags",
                    ",".join(item.get("tags", [])),
                    "--message",
                    message,
                    "--sequence-id",
                    sequence_id,
                    "--dedupe-state-file",
                    str(dedupe_state_file),
                    "--dedupe-window-seconds",
                    str(int(bridge.get("dedupe_window_seconds", 0))),
                ]
                result = subprocess.run(
                    command,
                    cwd=repo_root,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ntfy publish failed")
                await msg.ack()
                processed.append(
                    {
                        "subject": subject,
                        "topic": item["topic"],
                        "consumer": consumer,
                        "sequence_id": sequence_id,
                    }
                )
        return {"status": "ok", "processed": processed}
    finally:
        await nc.drain()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bridge selected NATS subjects into governed ntfy topics.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--registry", type=Path, default=TOPIC_REGISTRY_PATH)
    parser.add_argument("--publish-script", type=Path, default=REPO_ROOT / "scripts" / "ntfy_publish.py")
    parser.add_argument("--nats-url", default=os.environ.get("LV3_NATS_URL", ""))
    parser.add_argument("--nats-username", default=os.environ.get("LV3_NATS_USERNAME", ""))
    parser.add_argument("--nats-password", default=os.environ.get("LV3_NATS_PASSWORD", ""))
    parser.add_argument("--ntfy-base-url", default=os.environ.get("LV3_NTFY_BASE_URL", ""))
    parser.add_argument("--ntfy-token", default=os.environ.get("LV3_NTFY_TOKEN", ""))
    parser.add_argument(
        "--dedupe-state-file",
        type=Path,
        default=REPO_ROOT / ".local" / "state" / "ntfy" / "windmill-nats-bridge.json",
    )
    parser.add_argument("--max-messages-per-subject", type=int, default=10)
    args = parser.parse_args(argv)

    try:
        ensure_runtime_dependency()
        for value, label in [
            (args.nats_url, "--nats-url"),
            (args.nats_username, "--nats-username"),
            (args.nats_password, "--nats-password"),
            (args.ntfy_base_url, "--ntfy-base-url"),
            (args.ntfy_token, "--ntfy-token"),
        ]:
            if not value.strip():
                raise ValueError(f"{label} is required")
        result = asyncio.run(
            run_bridge_async(
                repo_root=args.repo_root,
                registry_path=args.registry,
                publish_script=args.publish_script,
                nats_url=args.nats_url,
                nats_username=args.nats_username,
                nats_password=args.nats_password,
                ntfy_base_url=args.ntfy_base_url,
                ntfy_token=args.ntfy_token,
                dedupe_state_file=args.dedupe_state_file,
                max_messages_per_subject=args.max_messages_per_subject,
            )
        )
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("ntfy NATS bridge", exc)


if __name__ == "__main__":
    raise SystemExit(main())
