from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml

from .classification import ClassifiedError, RetryClass, classify_error


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "retry-policies.yaml"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    multiplier: float = 2.0
    jitter: bool = True
    transient_max: int = 2


@dataclass(frozen=True)
class RetrySurfacePolicies:
    policies: dict[str, RetryPolicy]

    def get(self, surface: str, *, fallback: RetryPolicy | None = None) -> RetryPolicy:
        return self.policies.get(surface, fallback or DEFAULT_POLICY)


DEFAULT_POLICY = RetryPolicy()
DEFAULT_SURFACE_POLICIES = RetrySurfacePolicies(
    policies={
        "external_api": RetryPolicy(max_attempts=5, base_delay_s=2.0, max_delay_s=120.0, multiplier=2.0, jitter=True),
        "internal_api": RetryPolicy(max_attempts=4, base_delay_s=0.5, max_delay_s=30.0, multiplier=2.0, jitter=True),
        "ansible_ssh": RetryPolicy(max_attempts=3, base_delay_s=5.0, max_delay_s=30.0, multiplier=2.0, jitter=False),
        "nats_publish": RetryPolicy(max_attempts=3, base_delay_s=0.1, max_delay_s=5.0, multiplier=2.0, jitter=True),
        "workflow_execution": RetryPolicy(
            max_attempts=2,
            base_delay_s=10.0,
            max_delay_s=60.0,
            multiplier=2.0,
            jitter=True,
        ),
    }
)


class MaxRetriesExceeded(RuntimeError):
    def __init__(self, message: str, *, attempts: int, last_error: BaseException | None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


def resolve_retry_policy_config(config_path: Path | None = None) -> Path | None:
    if config_path is not None:
        return config_path
    env_path = Path(value).expanduser() if (value := os.environ.get("LV3_RETRY_POLICY_CONFIG", "").strip()) else None
    if env_path is not None:
        return env_path
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    return None


def load_retry_surface_policies(config_path: Path | None = None) -> RetrySurfacePolicies:
    resolved = resolve_retry_policy_config(config_path)
    policies = dict(DEFAULT_SURFACE_POLICIES.policies)
    if resolved is None or not resolved.exists():
        return RetrySurfacePolicies(policies=policies)

    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if payload.get("schema_version") != "1.0.0":
        raise ValueError(f"{resolved} must declare schema_version 1.0.0")
    items = payload.get("policies", [])
    if not isinstance(items, list):
        raise ValueError(f"{resolved} policies must be a list")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{resolved} policies entries must be mappings")
        surface = str(item.get("surface") or "").strip()
        if not surface:
            raise ValueError(f"{resolved} policies entries require a surface")
        policies[surface] = RetryPolicy(
            max_attempts=int(item.get("max_attempts", DEFAULT_POLICY.max_attempts)),
            base_delay_s=float(item.get("base_delay_s", DEFAULT_POLICY.base_delay_s)),
            max_delay_s=float(item.get("max_delay_s", DEFAULT_POLICY.max_delay_s)),
            multiplier=float(item.get("multiplier", DEFAULT_POLICY.multiplier)),
            jitter=bool(item.get("jitter", DEFAULT_POLICY.jitter)),
            transient_max=int(item.get("transient_max", DEFAULT_POLICY.transient_max)),
        )
    return RetrySurfacePolicies(policies=policies)


def policy_for_surface(surface: str, *, config_path: Path | None = None) -> RetryPolicy:
    return load_retry_surface_policies(config_path).get(surface)


def _delay_seconds(
    policy: RetryPolicy,
    classification: ClassifiedError,
    *,
    backoff_attempt: int,
    random_fn: Callable[[float, float], float],
) -> float:
    raw_delay = min(policy.base_delay_s * (policy.multiplier ** max(backoff_attempt - 1, 0)), policy.max_delay_s)
    delay = random_fn(0.0, raw_delay) if policy.jitter else raw_delay
    if classification.retry_after is not None:
        delay = max(delay, classification.retry_after)
    return delay


def with_retry(
    fn: Callable[[], Any],
    *,
    policy: RetryPolicy = DEFAULT_POLICY,
    error_context: str = "",
    sleep_fn: Callable[[float], None] = time.sleep,
    random_fn: Callable[[float, float], float] = random.uniform,
) -> Any:
    last_error: BaseException | None = None
    transient_failures = 0
    backoff_attempts = 0

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            classification = classify_error(exc)
            last_error = exc

            if classification.retry_class in {RetryClass.PERMANENT, RetryClass.FATAL}:
                raise
            if attempt >= policy.max_attempts:
                break
            if classification.retry_class == RetryClass.TRANSIENT and transient_failures < policy.transient_max:
                transient_failures += 1
                continue

            backoff_attempts += 1
            sleep_fn(
                _delay_seconds(
                    policy,
                    classification,
                    backoff_attempt=backoff_attempts,
                    random_fn=random_fn,
                )
            )

    raise MaxRetriesExceeded(
        f"exhausted {policy.max_attempts} attempts for {error_context or 'retry operation'}",
        attempts=policy.max_attempts,
        last_error=last_error,
    ) from last_error


async def async_with_retry(
    fn: Callable[[], Awaitable[Any]],
    *,
    policy: RetryPolicy = DEFAULT_POLICY,
    error_context: str = "",
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    random_fn: Callable[[float, float], float] = random.uniform,
) -> Any:
    last_error: BaseException | None = None
    transient_failures = 0
    backoff_attempts = 0

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            classification = classify_error(exc)
            last_error = exc

            if classification.retry_class in {RetryClass.PERMANENT, RetryClass.FATAL}:
                raise
            if attempt >= policy.max_attempts:
                break
            if classification.retry_class == RetryClass.TRANSIENT and transient_failures < policy.transient_max:
                transient_failures += 1
                continue

            backoff_attempts += 1
            await sleep_fn(
                _delay_seconds(
                    policy,
                    classification,
                    backoff_attempt=backoff_attempts,
                    random_fn=random_fn,
                )
            )

    raise MaxRetriesExceeded(
        f"exhausted {policy.max_attempts} attempts for {error_context or 'retry operation'}",
        attempts=policy.max_attempts,
        last_error=last_error,
    ) from last_error
