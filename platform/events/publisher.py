from __future__ import annotations

import asyncio
import json
from typing import Any

from platform.retry import async_with_retry, policy_for_surface
from platform.timeouts import resolve_timeout_seconds

from .taxonomy import build_envelope


NATS_CONNECT_TIMEOUT_SECONDS = resolve_timeout_seconds("liveness_probe", 5)
NATS_PUBLISH_POLICY = policy_for_surface("nats_publish")


async def connect_nats(nats_url: str, credentials: dict[str, str] | None = None) -> Any:
    from nats.aio.client import Client as NATS

    kwargs: dict[str, Any] = {
        "servers": [nats_url],
        "connect_timeout": NATS_CONNECT_TIMEOUT_SECONDS,
        "allow_reconnect": False,
        "max_reconnect_attempts": 0,
        "reconnect_time_wait": 0,
    }
    if credentials:
        kwargs.update(credentials)

    async def connect_once() -> Any:
        nc = NATS()
        await nc.connect(**kwargs)
        return nc

    return await async_with_retry(
        connect_once,
        policy=NATS_PUBLISH_POLICY,
        error_context=f"nats connect {nats_url}",
    )


async def publish_nats_events_async(
    records: list[dict[str, Any]],
    *,
    nats_url: str,
    credentials: dict[str, str] | None = None,
) -> None:
    nc = await connect_nats(nats_url, credentials)
    try:
        for record in records:
            subject = str(record.get("subject") or record.get("event") or "").strip()
            if not subject:
                raise ValueError("NATS record must define subject or event")
            payload = record.get("payload")
            if not isinstance(payload, dict):
                payload = dict(record)
                payload.pop("subject", None)
                payload.pop("actor_id", None)
                payload.pop("context_id", None)
                payload.pop("ts", None)
            envelope = build_envelope(
                subject,
                payload,
                actor_id=str(record.get("actor_id") or "").strip() or None,
                context_id=str(record.get("context_id") or "").strip() or None,
                ts=record.get("ts") or record.get("generated_at") or record.get("occurred_at") or record.get("collected_at"),
            )
            await async_with_retry(
                lambda subject=subject, envelope=envelope: nc.publish(
                    subject,
                    json.dumps(envelope, separators=(",", ":")).encode(),
                ),
                policy=NATS_PUBLISH_POLICY,
                error_context=f"nats publish {subject}",
            )
            await async_with_retry(
                lambda: nc.flush(timeout=NATS_CONNECT_TIMEOUT_SECONDS),
                policy=NATS_PUBLISH_POLICY,
                error_context="nats flush",
            )
    finally:
        await nc.drain()


def publish_nats_events(
    records: list[dict[str, Any]],
    *,
    nats_url: str,
    credentials: dict[str, str] | None = None,
) -> None:
    if not records:
        return
    asyncio.run(publish_nats_events_async(records, nats_url=nats_url, credentials=credentials))
