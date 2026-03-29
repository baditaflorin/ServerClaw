from __future__ import annotations

import contextvars
import json
import logging
import os
import socket
import sys
import uuid
from contextlib import contextmanager
from platform.datetime_compat import UTC, datetime
from typing import Any, Iterator


_LOG_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("platform_log_context", default={})
_STANDARD_LOG_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}
_REQUIRED_FIELDS = ("ts", "level", "service_id", "component", "trace_id", "msg", "vm")
_LEVEL_MAP = {
    "CRITICAL": "FATAL",
    "DEBUG": "DEBUG",
    "ERROR": "ERROR",
    "INFO": "INFO",
    "WARNING": "WARN",
}


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def current_context() -> dict[str, Any]:
    return dict(_LOG_CONTEXT.get({}))


def clear_context() -> None:
    _LOG_CONTEXT.set({})


def set_context(**fields: Any) -> contextvars.Token[dict[str, Any]]:
    merged = current_context()
    for key, value in fields.items():
        if value is None:
            merged.pop(key, None)
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                merged.pop(key, None)
                continue
        merged[key] = value
    return _LOG_CONTEXT.set(merged)


@contextmanager
def bind_context(**fields: Any) -> Iterator[None]:
    token = set_context(**fields)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _default_vm_name() -> str:
    return os.environ.get("VM_HOSTNAME") or os.environ.get("HOSTNAME") or socket.gethostname() or "unknown"


def _normalize_level(level_name: str) -> str:
    return _LEVEL_MAP.get(level_name.upper(), level_name.upper())


def _coerce_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _coerce_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce_json_value(item) for item in value]
    return str(value)


class PlatformJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = current_context()
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _STANDARD_LOG_ATTRS and not key.startswith("_")
            }
        )
        payload["ts"] = _utc_now_iso()
        payload["level"] = _normalize_level(record.levelname)
        payload["service_id"] = str(payload.get("service_id") or "unknown")
        payload["component"] = str(payload.get("component") or "unknown")
        payload["trace_id"] = str(payload.get("trace_id") or os.environ.get("PLATFORM_TRACE_ID") or "background")
        payload["msg"] = record.getMessage()
        payload["vm"] = str(payload.get("vm") or _default_vm_name())
        if record.exc_info:
            payload["error_detail"] = self.formatException(record.exc_info)

        normalized: dict[str, Any] = {}
        for field in _REQUIRED_FIELDS:
            normalized[field] = _coerce_json_value(payload[field])
        for key, value in payload.items():
            if key in normalized or value is None:
                continue
            normalized[key] = _coerce_json_value(value)
        return json.dumps(normalized, separators=(",", ":"), sort_keys=True)


class PlatformLoggerAdapter(logging.LoggerAdapter[logging.Logger]):
    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        extra = dict(self.extra)
        if "extra" in kwargs:
            extra.update(kwargs["extra"])
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(
    service_id: str,
    component: str,
    *,
    name: str | None = None,
    level: str | None = None,
    stream: Any | None = None,
) -> PlatformLoggerAdapter:
    logger_name = name or f"lv3.{service_id}.{component}"
    logger = logging.getLogger(logger_name)
    logger.setLevel((level or os.environ.get("LV3_LOG_LEVEL") or "INFO").upper())
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(stream or sys.stdout)
        handler.setFormatter(PlatformJsonFormatter())
        logger.addHandler(handler)

    return PlatformLoggerAdapter(
        logger,
        {
            "service_id": service_id,
            "component": component,
            "vm": _default_vm_name(),
        },
    )


__all__ = [
    "PlatformJsonFormatter",
    "PlatformLoggerAdapter",
    "bind_context",
    "clear_context",
    "current_context",
    "generate_trace_id",
    "get_logger",
    "set_context",
]
