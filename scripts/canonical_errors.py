from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ErrorCodeDefinition:
    code: str
    http_status: int
    severity: str
    category: str
    retry_advice: str
    description: str
    docs_url: str | None = None
    retry_after_s: int | None = None
    context_fields: tuple[str, ...] = ()
    deprecated_since: str | None = None


@dataclass
class CanonicalError(Exception):
    code: str
    message: str
    trace_id: str
    http_status: int
    retry_advice: str
    retry_after_s: int | None = None
    docs_url: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_response(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "trace_id": self.trace_id,
            "retry_advice": self.retry_advice,
            "retry_after": self.retry_after_s,
            "docs_url": self.docs_url,
            "occurred_at": self.occurred_at,
        }
        if self.context:
            payload["context"] = self.context
        return {"error": payload}


class PlatformHTTPError(Exception):
    def __init__(self, error: CanonicalError) -> None:
        super().__init__(error.message)
        self.error = error


class ErrorRegistry:
    def __init__(self, definitions: dict[str, ErrorCodeDefinition]) -> None:
        if not definitions:
            raise ValueError("error registry must define at least one error code")
        self._definitions = definitions

    @classmethod
    def load(cls, path: Path) -> "ErrorRegistry":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path} must contain a YAML mapping")
        error_codes = payload.get("error_codes")
        if not isinstance(error_codes, dict) or not error_codes:
            raise ValueError(f"{path}.error_codes must be a non-empty mapping")

        definitions: dict[str, ErrorCodeDefinition] = {}
        for code, raw_definition in error_codes.items():
            if not isinstance(code, str) or not code.strip():
                raise ValueError(f"{path}.error_codes contains an invalid code key")
            if not isinstance(raw_definition, dict):
                raise ValueError(f"{path}.error_codes.{code} must be a mapping")
            context_fields = raw_definition.get("context_fields", [])
            if context_fields is None:
                context_fields = []
            if not isinstance(context_fields, list):
                raise ValueError(f"{path}.error_codes.{code}.context_fields must be a list")
            definitions[code] = ErrorCodeDefinition(
                code=code,
                http_status=int(raw_definition["http_status"]),
                severity=str(raw_definition["severity"]),
                category=str(raw_definition["category"]),
                retry_advice=str(raw_definition["retry_advice"]),
                description=str(raw_definition["description"]),
                docs_url=raw_definition.get("docs_url"),
                retry_after_s=raw_definition.get("retry_after_s"),
                context_fields=tuple(str(field_name) for field_name in context_fields),
                deprecated_since=raw_definition.get("deprecated_since"),
            )
        return cls(definitions)

    def definition(self, code: str) -> ErrorCodeDefinition:
        try:
            return self._definitions[code]
        except KeyError as exc:
            raise KeyError(f"unknown error code '{code}'") from exc

    def create(
        self,
        code: str,
        *,
        trace_id: str,
        message: str | None = None,
        context: dict[str, Any] | None = None,
        retry_after_s: int | None = None,
        docs_url: str | None = None,
    ) -> CanonicalError:
        definition = self.definition(code)
        filtered_context: dict[str, Any] = {}
        if context:
            allowed_fields = set(definition.context_fields)
            for key, value in context.items():
                if key in allowed_fields:
                    filtered_context[key] = value
        return CanonicalError(
            code=definition.code,
            message=message or definition.description,
            trace_id=trace_id,
            http_status=definition.http_status,
            retry_advice=definition.retry_advice,
            retry_after_s=retry_after_s if retry_after_s is not None else definition.retry_after_s,
            docs_url=docs_url if docs_url is not None else definition.docs_url,
            context=filtered_context,
        )

    def openapi_fragment(self) -> dict[str, Any]:
        return {
            definition.code: {
                "http_status": definition.http_status,
                "severity": definition.severity,
                "category": definition.category,
                "retry_advice": definition.retry_advice,
                "retry_after_s": definition.retry_after_s,
                "description": definition.description,
                "docs_url": definition.docs_url,
                "context_fields": list(definition.context_fields),
                "deprecated_since": definition.deprecated_since,
            }
            for definition in sorted(self._definitions.values(), key=lambda item: item.code)
        }
