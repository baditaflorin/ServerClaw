from __future__ import annotations

import errno
import socket
import ssl
import urllib.error
from dataclasses import dataclass
from platform.datetime_compat import UTC, datetime
from email.utils import parsedate_to_datetime
from platform.enum_compat import StrEnum

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - some utility scripts do not install httpx
    httpx = None  # type: ignore[assignment]


class RetryClass(StrEnum):
    TRANSIENT = "TRANSIENT"
    BACKOFF = "BACKOFF"
    PERMANENT = "PERMANENT"
    FATAL = "FATAL"


@dataclass(frozen=True)
class ClassifiedError:
    retry_class: RetryClass
    code: str
    retry_after: float | None = None


class PlatformRetryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retry_class: RetryClass | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_class = retry_class
        self.retry_after = retry_after


ERROR_TAXONOMY: dict[str, RetryClass] = {
    "http:400": RetryClass.PERMANENT,
    "http:401": RetryClass.PERMANENT,
    "http:403": RetryClass.PERMANENT,
    "http:404": RetryClass.PERMANENT,
    "http:408": RetryClass.TRANSIENT,
    "http:409": RetryClass.PERMANENT,
    "http:422": RetryClass.PERMANENT,
    "http:429": RetryClass.BACKOFF,
    "http:500": RetryClass.BACKOFF,
    "http:502": RetryClass.BACKOFF,
    "http:503": RetryClass.BACKOFF,
    "http:504": RetryClass.BACKOFF,
    "net:connection_refused": RetryClass.BACKOFF,
    "net:connection_timeout": RetryClass.TRANSIENT,
    "net:read_timeout": RetryClass.BACKOFF,
    "net:ssl_error": RetryClass.PERMANENT,
    "net:dns_resolution_failed": RetryClass.BACKOFF,
    "platform:lock_contention": RetryClass.BACKOFF,
    "platform:budget_exceeded": RetryClass.PERMANENT,
    "platform:health_gate_fail": RetryClass.BACKOFF,
    "platform:concurrency_limit": RetryClass.BACKOFF,
    "platform:intent_conflict": RetryClass.PERMANENT,
    "platform:circuit_open": RetryClass.BACKOFF,
    "ansible:unreachable": RetryClass.BACKOFF,
    "ansible:syntax_error": RetryClass.PERMANENT,
    "ansible:task_failed": RetryClass.PERMANENT,
    "ansible:timeout": RetryClass.BACKOFF,
}


def classify_code(code: str, *, retry_after: float | None = None) -> ClassifiedError:
    normalized = code.strip().lower()
    retry_class = ERROR_TAXONOMY.get(normalized, RetryClass.PERMANENT)
    return ClassifiedError(retry_class=retry_class, code=normalized, retry_after=retry_after)


def parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max((retry_at - datetime.now(UTC)).total_seconds(), 0.0)
    return max(seconds, 0.0)


def _classify_os_error(exc: BaseException) -> str:
    if isinstance(exc, ssl.SSLError):
        return "net:ssl_error"
    if isinstance(exc, socket.gaierror):
        return "net:dns_resolution_failed"
    if isinstance(exc, ConnectionRefusedError):
        return "net:connection_refused"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "net:connection_timeout"
    if isinstance(exc, OSError):
        if exc.errno == errno.ECONNREFUSED:
            return "net:connection_refused"
        if exc.errno in {errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ENETUNREACH}:
            return "net:connection_timeout"
    return f"python:{exc.__class__.__name__.lower()}"


def _classify_httpx_error(exc: object) -> ClassifiedError:
    assert httpx is not None
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        return classify_code(
            f"http:{response.status_code}",
            retry_after=parse_retry_after(response.headers.get("Retry-After")),
        )
    if isinstance(exc, httpx.ConnectTimeout):
        return classify_code("net:connection_timeout")
    if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return classify_code("net:read_timeout")
    if isinstance(exc, httpx.ConnectError):
        cause = exc.__cause__ or (exc.args[0] if exc.args else None)
        if isinstance(cause, BaseException):
            return classify_code(_classify_os_error(cause))
        message = str(exc).lower()
        if "name or service not known" in message or "temporary failure in name resolution" in message:
            return classify_code("net:dns_resolution_failed")
        if "connection refused" in message:
            return classify_code("net:connection_refused")
        return classify_code("net:connection_timeout")
    return classify_code(f"python:{exc.__class__.__name__.lower()}")


def classify_error(exc: BaseException) -> ClassifiedError:
    if isinstance(exc, PlatformRetryError):
        if exc.retry_class is not None:
            return ClassifiedError(
                retry_class=exc.retry_class,
                code=(exc.code or f"platform:{exc.retry_class.lower()}").strip().lower(),
                retry_after=exc.retry_after,
            )
        if exc.code is not None:
            return classify_code(exc.code, retry_after=exc.retry_after)

    if isinstance(exc, urllib.error.HTTPError):
        return classify_code(
            f"http:{exc.code}",
            retry_after=parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None),
        )
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return classify_code(_classify_os_error(reason))
        return classify_code("net:connection_timeout")
    if httpx is not None and isinstance(exc, httpx.HTTPError):
        return _classify_httpx_error(exc)
    if isinstance(exc, BaseException):
        return classify_code(_classify_os_error(exc))
    return classify_code("python:unknown")
