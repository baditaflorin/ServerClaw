from __future__ import annotations

import asyncio
import json
import math
import os
import socket
import threading
import urllib.error
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "circuit-policies.yaml"
CIRCUIT_BUCKET = "platform-circuits"
CIRCUIT_STATE_FILE_ENV = "LV3_CIRCUIT_STATE_FILE"
CIRCUIT_STATE_NATS_URL_ENV = "LV3_CIRCUIT_NATS_URL"
RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value: Any) -> datetime | None:
    if value in {None, "", "not yet"}:
        return None
    if not isinstance(value, str):
        raise ValueError(f"expected ISO-8601 datetime string, got {value!r}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_retryable_http_status(status_code: int) -> bool:
    return status_code in RETRYABLE_HTTP_STATUSES


def should_count_socket_exception(exc: BaseException) -> bool:
    return isinstance(exc, (ConnectionError, OSError, TimeoutError, socket.timeout))


def should_count_urllib_exception(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return is_retryable_http_status(exc.code)
    if isinstance(exc, urllib.error.URLError):
        return True
    return should_count_socket_exception(exc)


def should_count_httpx_exception(exc: BaseException) -> bool:
    try:
        import httpx
    except ModuleNotFoundError:
        return should_count_socket_exception(exc)

    if isinstance(exc, httpx.HTTPStatusError):
        return is_retryable_http_status(exc.response.status_code)
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError, httpx.ReadTimeout, httpx.WriteError, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True
    return should_count_socket_exception(exc)


def run_coro_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("sync circuit breaker API cannot be used inside a running event loop")


@dataclass(frozen=True)
class CircuitPolicy:
    name: str
    service: str
    failure_threshold: int
    recovery_window_s: int
    success_threshold: int
    timeout_s: float | None = None


@dataclass
class CircuitState:
    name: str
    state: str = "closed"
    failure_count: int = 0
    last_failure_at: datetime | None = None
    opened_at: datetime | None = None
    recovery_window_s: int = 30
    failure_threshold: int = 5
    success_threshold: int = 1
    consecutive_successes: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_at": format_datetime(self.last_failure_at),
            "opened_at": format_datetime(self.opened_at),
            "recovery_window_s": self.recovery_window_s,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "consecutive_successes": self.consecutive_successes,
        }
        payload.update(self.meta)
        return payload

    @classmethod
    def for_policy(cls, policy: CircuitPolicy) -> "CircuitState":
        return cls(
            name=policy.name,
            recovery_window_s=policy.recovery_window_s,
            failure_threshold=policy.failure_threshold,
            success_threshold=policy.success_threshold,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any], policy: CircuitPolicy) -> "CircuitState":
        state = cls.for_policy(policy)
        state.state = str(payload.get("state", "closed")).strip() or "closed"
        state.failure_count = int(payload.get("failure_count", 0) or 0)
        state.last_failure_at = parse_datetime(payload.get("last_failure_at"))
        state.opened_at = parse_datetime(payload.get("opened_at"))
        state.consecutive_successes = int(payload.get("consecutive_successes", 0) or 0)
        state.meta = {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "name",
                "state",
                "failure_count",
                "last_failure_at",
                "opened_at",
                "recovery_window_s",
                "failure_threshold",
                "success_threshold",
                "consecutive_successes",
            }
        }
        return state


class CircuitOpenError(RuntimeError):
    def __init__(self, circuit: str, *, retry_after: int, opened_at: datetime | None) -> None:
        self.circuit = circuit
        self.retry_after = max(1, int(retry_after))
        self.opened_at = opened_at
        super().__init__(f"circuit '{circuit}' is open for {self.retry_after}s")


class CircuitStateBackend:
    async def load(self, name: str, policy: CircuitPolicy) -> CircuitState:
        raise NotImplementedError

    async def save(self, state: CircuitState) -> CircuitState:
        raise NotImplementedError

    async def reset(self, name: str, policy: CircuitPolicy) -> CircuitState:
        state = CircuitState.for_policy(policy)
        return await self.save(state)

    def load_sync(self, name: str, policy: CircuitPolicy) -> CircuitState:
        return run_coro_sync(self.load(name, policy))

    def save_sync(self, state: CircuitState) -> CircuitState:
        return run_coro_sync(self.save(state))

    def reset_sync(self, name: str, policy: CircuitPolicy) -> CircuitState:
        return run_coro_sync(self.reset(name, policy))


class MemoryCircuitStateBackend(CircuitStateBackend):
    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    async def load(self, name: str, policy: CircuitPolicy) -> CircuitState:
        with self._lock:
            payload = dict(self._states.get(name, {}))
        if not payload:
            return CircuitState.for_policy(policy)
        return CircuitState.from_dict(payload, policy)

    async def save(self, state: CircuitState) -> CircuitState:
        with self._lock:
            self._states[state.name] = state.to_dict()
        return state

    async def reset(self, name: str, policy: CircuitPolicy) -> CircuitState:
        state = CircuitState.for_policy(policy)
        with self._lock:
            self._states[name] = state.to_dict()
        return state


class JsonFileCircuitStateBackend(CircuitStateBackend):
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path).expanduser()
        self._lock = threading.Lock()

    def _read_all(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {
            str(name): value
            for name, value in payload.items()
            if isinstance(name, str) and isinstance(value, dict)
        }

    def _write_all(self, payload: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    async def load(self, name: str, policy: CircuitPolicy) -> CircuitState:
        with self._lock:
            payload = self._read_all().get(name, {})
        if not payload:
            return CircuitState.for_policy(policy)
        return CircuitState.from_dict(payload, policy)

    async def save(self, state: CircuitState) -> CircuitState:
        with self._lock:
            payload = self._read_all()
            payload[state.name] = state.to_dict()
            self._write_all(payload)
        return state

    async def reset(self, name: str, policy: CircuitPolicy) -> CircuitState:
        state = CircuitState.for_policy(policy)
        await self.save(state)
        return state


class NatsKvCircuitStateBackend(CircuitStateBackend):
    def __init__(
        self,
        nats_url: str,
        *,
        bucket: str = CIRCUIT_BUCKET,
        credentials: dict[str, str] | None = None,
        fallback: CircuitStateBackend | None = None,
    ) -> None:
        self._nats_url = nats_url
        self._bucket = bucket
        self._credentials = credentials or {}
        self._fallback = fallback or MemoryCircuitStateBackend()

    async def _connect(self) -> tuple[Any, Any]:
        from nats.aio.client import Client as NATS

        async def error_cb(error: Exception) -> None:
            recorded_errors.append(error)

        recorded_errors: list[Exception] = []
        nc = NATS()
        setattr(nc, "_lv3_recorded_errors", recorded_errors)
        connect_kwargs: dict[str, Any] = {
            "servers": [self._nats_url],
            "error_cb": error_cb,
            "connect_timeout": 5,
            "allow_reconnect": False,
            "max_reconnect_attempts": 0,
            "reconnect_time_wait": 0,
        }
        if self._credentials:
            connect_kwargs.update(self._credentials)
        await nc.connect(**connect_kwargs)
        return nc, nc.jetstream()

    async def _bucket_for(self, js: Any) -> Any:
        import nats.js.errors

        try:
            return await js.key_value(self._bucket)
        except nats.js.errors.BucketNotFoundError:
            return await js.create_key_value(
                bucket=self._bucket,
                description="Distributed circuit breaker state",
                history=1,
                direct=True,
            )

    async def load(self, name: str, policy: CircuitPolicy) -> CircuitState:
        try:
            import nats.js.errors  # noqa: F401
        except ModuleNotFoundError:
            return await self._fallback.load(name, policy)

        try:
            nc, js = await self._connect()
        except Exception:
            return await self._fallback.load(name, policy)

        try:
            kv = await self._bucket_for(js)
            try:
                entry = await kv.get(name)
            except Exception:
                return await self._fallback.load(name, policy)
            payload = json.loads(entry.value.decode("utf-8"))
            if not isinstance(payload, dict):
                return await self._fallback.load(name, policy)
            state = CircuitState.from_dict(payload, policy)
            state.meta["revision"] = getattr(entry, "revision", None)
            return state
        except Exception:
            return await self._fallback.load(name, policy)
        finally:
            await nc.drain()

    async def save(self, state: CircuitState) -> CircuitState:
        try:
            import nats.js.errors
        except ModuleNotFoundError:
            return await self._fallback.save(state)

        payload = state.to_dict()
        try:
            nc, js = await self._connect()
        except Exception:
            return await self._fallback.save(state)

        try:
            kv = await self._bucket_for(js)
            revision = state.meta.get("revision")
            encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            if isinstance(revision, int):
                try:
                    await kv.update(state.name, encoded, last=revision)
                    return state
                except Exception:
                    pass
            try:
                await kv.create(state.name, encoded)
            except Exception:
                await kv.put(state.name, encoded)
            return state
        except Exception:
            return await self._fallback.save(state)
        finally:
            await nc.drain()

    async def reset(self, name: str, policy: CircuitPolicy) -> CircuitState:
        state = CircuitState.for_policy(policy)
        return await self.save(state)


def load_circuit_policies(path: Path | str = DEFAULT_POLICY_PATH) -> dict[str, CircuitPolicy]:
    resolved_path = Path(path)
    if not resolved_path.exists():
        return {}
    payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
    circuits = payload.get("circuits", [])
    if not isinstance(circuits, list):
        raise ValueError("config/circuit-policies.yaml must define a circuits list")
    result: dict[str, CircuitPolicy] = {}
    for index, item in enumerate(circuits):
        if not isinstance(item, dict):
            raise ValueError(f"circuits[{index}] must be an object")
        name = str(item.get("name", "")).strip()
        service = str(item.get("service", "")).strip() or name
        failure_threshold = int(item.get("failure_threshold", 0) or 0)
        recovery_window_s = int(item.get("recovery_window_s", 0) or 0)
        success_threshold = int(item.get("success_threshold", 0) or 0)
        if not name:
            raise ValueError(f"circuits[{index}].name must be a non-empty string")
        if failure_threshold < 1:
            raise ValueError(f"circuits[{index}].failure_threshold must be >= 1")
        if recovery_window_s < 1:
            raise ValueError(f"circuits[{index}].recovery_window_s must be >= 1")
        if success_threshold < 1:
            raise ValueError(f"circuits[{index}].success_threshold must be >= 1")
        timeout_s = item.get("timeout_s")
        result[name] = CircuitPolicy(
            name=name,
            service=service,
            failure_threshold=failure_threshold,
            recovery_window_s=recovery_window_s,
            success_threshold=success_threshold,
            timeout_s=float(timeout_s) if timeout_s is not None else None,
        )
    return result


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        policy: CircuitPolicy,
        *,
        backend: CircuitStateBackend,
        exception_classifier: Callable[[BaseException], bool] | None = None,
    ) -> None:
        self.name = name
        self.policy = policy
        self.backend = backend
        self.exception_classifier = exception_classifier or (lambda _exc: True)

    def state(self) -> CircuitState:
        return self.backend.load_sync(self.name, self.policy)

    def reset(self) -> CircuitState:
        return self.backend.reset_sync(self.name, self.policy)

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        state = self.backend.load_sync(self.name, self.policy)
        state = self._prepare_for_execution(state)
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            if self.exception_classifier(exc):
                state = self._record_failure(state)
                self.backend.save_sync(state)
            raise
        state = self._record_success(state)
        self.backend.save_sync(state)
        return result

    def _prepare_for_execution(self, state: CircuitState) -> CircuitState:
        if state.state != "open":
            return state
        now = utc_now()
        opened_at = state.opened_at or now
        elapsed = (now - opened_at).total_seconds()
        remaining = self.policy.recovery_window_s - elapsed
        if remaining > 0:
            raise CircuitOpenError(self.name, retry_after=math.ceil(remaining), opened_at=state.opened_at)
        state.state = "half_open"
        state.consecutive_successes = 0
        self.backend.save_sync(state)
        return state

    def _record_failure(self, state: CircuitState) -> CircuitState:
        now = utc_now()
        state.last_failure_at = now
        state.consecutive_successes = 0
        if state.state == "half_open":
            state.failure_count = self.policy.failure_threshold
            state.state = "open"
            state.opened_at = now
            return state
        state.failure_count += 1
        if state.failure_count >= self.policy.failure_threshold:
            state.state = "open"
            state.opened_at = now
        return state

    def _record_success(self, state: CircuitState) -> CircuitState:
        if state.state == "half_open":
            state.consecutive_successes += 1
            if state.consecutive_successes >= self.policy.success_threshold:
                state.state = "closed"
                state.failure_count = 0
                state.consecutive_successes = 0
                state.opened_at = None
            return state
        if state.state == "closed" and state.failure_count > 0:
            state.failure_count = max(0, state.failure_count - 1)
        return state


class AsyncCircuitBreaker:
    def __init__(
        self,
        name: str,
        policy: CircuitPolicy,
        *,
        backend: CircuitStateBackend,
        exception_classifier: Callable[[BaseException], bool] | None = None,
    ) -> None:
        self.name = name
        self.policy = policy
        self.backend = backend
        self.exception_classifier = exception_classifier or (lambda _exc: True)

    async def state(self) -> CircuitState:
        return await self.backend.load(self.name, self.policy)

    async def reset(self) -> CircuitState:
        return await self.backend.reset(self.name, self.policy)

    async def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        state = await self.backend.load(self.name, self.policy)
        state = await self._prepare_for_execution(state)
        try:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:  # noqa: BLE001
            if self.exception_classifier(exc):
                state = self._record_failure(state)
                await self.backend.save(state)
            raise
        state = self._record_success(state)
        await self.backend.save(state)
        return result

    async def _prepare_for_execution(self, state: CircuitState) -> CircuitState:
        if state.state != "open":
            return state
        now = utc_now()
        opened_at = state.opened_at or now
        elapsed = (now - opened_at).total_seconds()
        remaining = self.policy.recovery_window_s - elapsed
        if remaining > 0:
            raise CircuitOpenError(self.name, retry_after=math.ceil(remaining), opened_at=state.opened_at)
        state.state = "half_open"
        state.consecutive_successes = 0
        await self.backend.save(state)
        return state

    def _record_failure(self, state: CircuitState) -> CircuitState:
        now = utc_now()
        state.last_failure_at = now
        state.consecutive_successes = 0
        if state.state == "half_open":
            state.failure_count = self.policy.failure_threshold
            state.state = "open"
            state.opened_at = now
            return state
        state.failure_count += 1
        if state.failure_count >= self.policy.failure_threshold:
            state.state = "open"
            state.opened_at = now
        return state

    def _record_success(self, state: CircuitState) -> CircuitState:
        if state.state == "half_open":
            state.consecutive_successes += 1
            if state.consecutive_successes >= self.policy.success_threshold:
                state.state = "closed"
                state.failure_count = 0
                state.consecutive_successes = 0
                state.opened_at = None
            return state
        if state.state == "closed" and state.failure_count > 0:
            state.failure_count = max(0, state.failure_count - 1)
        return state


class CircuitRegistry:
    def __init__(
        self,
        repo_root: Path | str = REPO_ROOT,
        *,
        policies_path: Path | str | None = None,
        backend: CircuitStateBackend | None = None,
        nats_url: str | None = None,
        nats_credentials: dict[str, str] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.policies_path = Path(policies_path) if policies_path is not None else (self.repo_root / "config" / "circuit-policies.yaml")
        self.policies = load_circuit_policies(self.policies_path)
        self.backend = backend or self._build_backend(nats_url=nats_url, nats_credentials=nats_credentials)

    def _build_backend(
        self,
        *,
        nats_url: str | None,
        nats_credentials: dict[str, str] | None,
    ) -> CircuitStateBackend:
        state_file = os.environ.get(CIRCUIT_STATE_FILE_ENV, "").strip()
        if state_file:
            return JsonFileCircuitStateBackend(state_file)

        resolved_nats_url = (
            nats_url
            or os.environ.get(CIRCUIT_STATE_NATS_URL_ENV, "").strip()
            or os.environ.get("LV3_NATS_URL", "").strip()
            or os.environ.get("NATS_URL", "").strip()
        )
        if resolved_nats_url:
            credentials = dict(nats_credentials or {})
            user = os.environ.get("LV3_NATS_USERNAME", "").strip()
            password = os.environ.get("LV3_NATS_PASSWORD", "").strip()
            if user and password:
                credentials.setdefault("user", user)
                credentials.setdefault("password", password)
            return NatsKvCircuitStateBackend(
                resolved_nats_url,
                credentials=credentials or None,
                fallback=MemoryCircuitStateBackend(),
            )
        return MemoryCircuitStateBackend()

    def has_policy(self, name: str) -> bool:
        return name in self.policies

    def policy(self, name: str) -> CircuitPolicy:
        if name not in self.policies:
            raise KeyError(f"unknown circuit policy: {name}")
        return self.policies[name]

    def sync_breaker(
        self,
        name: str,
        *,
        exception_classifier: Callable[[BaseException], bool] | None = None,
    ) -> CircuitBreaker:
        return CircuitBreaker(
            name,
            self.policy(name),
            backend=self.backend,
            exception_classifier=exception_classifier,
        )

    def async_breaker(
        self,
        name: str,
        *,
        exception_classifier: Callable[[BaseException], bool] | None = None,
    ) -> AsyncCircuitBreaker:
        return AsyncCircuitBreaker(
            name,
            self.policy(name),
            backend=self.backend,
            exception_classifier=exception_classifier,
        )
