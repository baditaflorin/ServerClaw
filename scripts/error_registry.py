"""Error code registry — load, validate, and look up platform error codes.

This module is the primary public interface for working with the error code
registry defined in ``config/error-codes.yaml``.  It re-exports the core
types from :mod:`canonical_errors` and adds:

- :func:`load_registry` — load and validate the canonical registry path.
- :func:`validate_registry` — validate a registry dict against the schema
  without constructing an :class:`ErrorRegistry` instance.
- :class:`ErrorRegistryError` — base exception for registry failures.
- :func:`lookup` — convenience function that looks up a code against the
  default (repo-canonical) registry.

Relationships
-------------
- ``config/error-codes.yaml`` is the authoritative source of truth (ADR 0166).
- :mod:`canonical_errors` owns the ``ErrorRegistry``, ``CanonicalError``, and
  ``ErrorCodeDefinition`` types; this module builds on top of them.
- ``scripts/validate_repository_data_models.py`` calls :func:`validate_registry`
  as part of the repository data-model gate (ADR 0031).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

# Re-export the core types so callers only need to import from one place.
from canonical_errors import (  # noqa: F401  (public re-exports)
    CanonicalError,
    ErrorCodeDefinition,
    ErrorRegistry,
    PlatformHTTPError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Allowed values for the ``severity`` field.
VALID_SEVERITIES: frozenset[str] = frozenset({"debug", "info", "warn", "error", "critical"})

#: Allowed values for the ``retry_advice`` field.
VALID_RETRY_ADVICE: frozenset[str] = frozenset({"none", "immediate", "backoff", "manual"})

#: Regex that error code names must match.  Codes are SCREAMING_SNAKE_CASE
#: with a single optional namespace prefix separated by an underscore.
_CODE_PATTERN: re.Pattern[str] = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z][A-Z0-9]+)+$")

#: Path to the canonical registry relative to the repository root.
_DEFAULT_REGISTRY_PATH: Path = (
    Path(__file__).resolve().parents[1] / "config" / "error-codes.yaml"
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ErrorRegistryError(ValueError):
    """Raised when the error code registry file is missing, malformed, or
    fails schema validation."""


class UnknownErrorCode(KeyError):
    """Raised when a code is looked up but does not exist in the registry."""

    def __init__(self, code: str) -> None:
        super().__init__(f"unknown error code: {code!r}")
        self.code = code


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ErrorRegistryError(message)


def _validate_code_name(code: str, path: str) -> None:
    _require(
        bool(_CODE_PATTERN.match(code)),
        f"{path}: code name must be SCREAMING_SNAKE_CASE with at least two components "
        f"(e.g. AUTH_TOKEN_MISSING), got {code!r}",
    )


def _validate_entry(code: str, entry: Any, path: str) -> None:
    _require(isinstance(entry, dict), f"{path}: must be a mapping, got {type(entry).__name__}")

    # ── required fields ────────────────────────────────────────────────────
    for required_field in ("severity", "category", "retry_advice", "description"):
        _require(
            required_field in entry,
            f"{path}.{required_field}: required field is missing",
        )
        _require(
            isinstance(entry[required_field], str) and entry[required_field].strip(),
            f"{path}.{required_field}: must be a non-empty string",
        )

    severity = entry["severity"]
    _require(
        severity in VALID_SEVERITIES,
        f"{path}.severity: must be one of {sorted(VALID_SEVERITIES)}, got {severity!r}",
    )

    retry_advice = entry["retry_advice"]
    _require(
        retry_advice in VALID_RETRY_ADVICE,
        f"{path}.retry_advice: must be one of {sorted(VALID_RETRY_ADVICE)}, got {retry_advice!r}",
    )

    # ── http_status — required unless code represents a non-error outcome ──
    # Codes in the 2xx range (e.g. EXEC_IDEMPOTENT_HIT) have http_status too,
    # so we just validate the type when the field is present.
    if "http_status" in entry:
        http_status = entry["http_status"]
        _require(
            isinstance(http_status, int) and 100 <= http_status <= 599,
            f"{path}.http_status: must be an integer HTTP status code (100–599), got {http_status!r}",
        )

    # ── retry_after_s ──────────────────────────────────────────────────────
    if "retry_after_s" in entry and entry["retry_after_s"] is not None:
        retry_after = entry["retry_after_s"]
        _require(
            isinstance(retry_after, int) and retry_after >= 0,
            f"{path}.retry_after_s: must be a non-negative integer or null, got {retry_after!r}",
        )

    # ── context_fields ─────────────────────────────────────────────────────
    if "context_fields" in entry and entry["context_fields"] is not None:
        fields = entry["context_fields"]
        _require(isinstance(fields, list), f"{path}.context_fields: must be a list")
        for i, field_name in enumerate(fields):
            _require(
                isinstance(field_name, str) and field_name.strip(),
                f"{path}.context_fields[{i}]: must be a non-empty string",
            )

    # ── docs_url ───────────────────────────────────────────────────────────
    if "docs_url" in entry and entry["docs_url"] is not None:
        docs_url = entry["docs_url"]
        _require(
            isinstance(docs_url, str) and docs_url.startswith(("http://", "https://")),
            f"{path}.docs_url: must be an HTTP(S) URL, got {docs_url!r}",
        )

    # ── deprecated_since ───────────────────────────────────────────────────
    if "deprecated_since" in entry and entry["deprecated_since"] is not None:
        deprecated = entry["deprecated_since"]
        _require(
            isinstance(deprecated, str) and deprecated.strip(),
            f"{path}.deprecated_since: must be a non-empty string (e.g. a version like '0.178.0')",
        )


def validate_registry(data: Any) -> dict[str, Any]:
    """Validate a parsed registry dict (the result of ``yaml.safe_load``).

    Returns the ``error_codes`` sub-mapping on success.
    Raises :class:`ErrorRegistryError` with a descriptive message on any
    schema violation.

    This function is intentionally free of side-effects — it does not build
    an :class:`ErrorRegistry` instance, so it can be used as a lightweight
    gate in the repository validation pipeline.

    Parameters
    ----------
    data:
        The parsed YAML document.  Must be a dict at the top level.

    Returns
    -------
    dict[str, Any]
        The validated ``error_codes`` mapping.
    """
    _require(isinstance(data, dict), "registry root must be a YAML mapping")
    _require("error_codes" in data, "registry must contain an 'error_codes' key")
    error_codes = data["error_codes"]
    _require(
        isinstance(error_codes, dict) and error_codes,
        "error_codes must be a non-empty mapping",
    )

    for code, entry in error_codes.items():
        _require(isinstance(code, str) and code.strip(), f"error_codes: key must be a non-empty string, got {code!r}")
        _validate_code_name(code, f"error_codes.{code}")
        _validate_entry(code, entry, f"error_codes.{code}")

    return error_codes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_registry(path: Path | None = None) -> ErrorRegistry:
    """Load and validate the error code registry from *path*.

    If *path* is ``None``, the canonical registry at
    ``config/error-codes.yaml`` (relative to the repository root) is used.

    Parameters
    ----------
    path:
        Explicit path to a ``error-codes.yaml`` file.  Defaults to the
        repo-canonical registry.

    Returns
    -------
    ErrorRegistry
        A validated, fully populated registry instance.

    Raises
    ------
    ErrorRegistryError
        If the file does not exist, is not valid YAML, or fails schema
        validation.
    FileNotFoundError
        If the registry file cannot be found at *path*.
    """
    registry_path = Path(path) if path is not None else _DEFAULT_REGISTRY_PATH

    if not registry_path.exists():
        raise FileNotFoundError(
            f"error code registry not found at {registry_path}. "
            "Expected config/error-codes.yaml in the repository root."
        )

    try:
        raw_text = registry_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ErrorRegistryError(f"cannot read registry file {registry_path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ErrorRegistryError(f"registry file {registry_path} is not valid YAML: {exc}") from exc

    try:
        validate_registry(data)
    except ErrorRegistryError as exc:
        raise ErrorRegistryError(f"registry file {registry_path} failed validation: {exc}") from exc

    try:
        return ErrorRegistry.load(registry_path)
    except (ValueError, KeyError) as exc:
        raise ErrorRegistryError(
            f"registry file {registry_path} could not be loaded: {exc}"
        ) from exc


def lookup(code: str, *, registry_path: Path | None = None) -> ErrorCodeDefinition:
    """Look up a single error code definition.

    Loads the registry (cached per process invocation) and returns the
    :class:`ErrorCodeDefinition` for *code*.

    Parameters
    ----------
    code:
        The error code to look up, e.g. ``"AUTH_TOKEN_MISSING"``.
    registry_path:
        Optional override for the registry file path.

    Returns
    -------
    ErrorCodeDefinition

    Raises
    ------
    UnknownErrorCode
        If *code* is not defined in the registry.
    ErrorRegistryError
        If the registry file cannot be loaded or is invalid.
    """
    registry = load_registry(registry_path)
    try:
        return registry.definition(code)
    except KeyError:
        raise UnknownErrorCode(code)


def list_codes(*, registry_path: Path | None = None) -> list[str]:
    """Return a sorted list of all error code names defined in the registry.

    Parameters
    ----------
    registry_path:
        Optional override for the registry file path.

    Returns
    -------
    list[str]
        Sorted list of code name strings.
    """
    registry = load_registry(registry_path)
    return sorted(registry.openapi_fragment().keys())


def codes_by_category(*, registry_path: Path | None = None) -> dict[str, list[str]]:
    """Return a mapping of category name → sorted list of code names.

    Parameters
    ----------
    registry_path:
        Optional override for the registry file path.

    Returns
    -------
    dict[str, list[str]]
        E.g. ``{"authentication": ["AUTH_TOKEN_EXPIRED", "AUTH_TOKEN_INVALID", ...], ...}``
    """
    registry = load_registry(registry_path)
    fragment = registry.openapi_fragment()
    result: dict[str, list[str]] = {}
    for code, meta in fragment.items():
        category = meta.get("category", "uncategorized")
        result.setdefault(category, []).append(code)
    for codes in result.values():
        codes.sort()
    return result


# ---------------------------------------------------------------------------
# CLI entry-point (python -m error_registry / python scripts/error_registry.py)
# ---------------------------------------------------------------------------


def _main() -> None:  # pragma: no cover
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Inspect the platform error code registry.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Path to error-codes.yaml (defaults to config/error-codes.yaml in repo root).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all error code names.")
    sub.add_parser("categories", help="List codes grouped by category.")

    lookup_cmd = sub.add_parser("lookup", help="Look up a single error code.")
    lookup_cmd.add_argument("code", help="Error code name (e.g. AUTH_TOKEN_MISSING).")

    sub.add_parser("validate", help="Validate the registry and exit 0 on success.")
    sub.add_parser("export", help="Export the full registry as JSON (OpenAPI fragment format).")

    args = parser.parse_args()

    registry = load_registry(args.registry)

    if args.command == "list":
        for code in sorted(registry.openapi_fragment()):
            print(code)

    elif args.command == "categories":
        grouped = codes_by_category(registry_path=args.registry)
        print(json.dumps(grouped, indent=2))

    elif args.command == "lookup":
        try:
            defn = registry.definition(args.code)
        except KeyError:
            import sys
            print(f"error: unknown code {args.code!r}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({
            "code": defn.code,
            "http_status": defn.http_status,
            "severity": defn.severity,
            "category": defn.category,
            "retry_advice": defn.retry_advice,
            "retry_after_s": defn.retry_after_s,
            "description": defn.description,
            "docs_url": defn.docs_url,
            "context_fields": list(defn.context_fields),
            "deprecated_since": defn.deprecated_since,
        }, indent=2))

    elif args.command == "validate":
        print(f"registry at {args.registry or _DEFAULT_REGISTRY_PATH} is valid.")

    elif args.command == "export":
        print(json.dumps(registry.openapi_fragment(), indent=2))


if __name__ == "__main__":  # pragma: no cover
    _main()
