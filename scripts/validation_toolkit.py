"""Shared validation helpers for all catalog and registry validation scripts.

Every function follows the same contract:
- Takes a value (of unknown type) and a path string (for error messages).
- Returns the value cast to the expected type if valid.
- Raises ValueError with a message of the form "{path} must be <description>".

Usage:
    from validation_toolkit import require_str, require_mapping, require_list
"""

from __future__ import annotations

from typing import Any


def require_str(value: Any, path: str, *, allow_empty: bool = False) -> str:
    """Validate that value is a string. By default rejects empty/whitespace-only strings."""
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a non-empty string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    """Validate that value is a dict/mapping."""
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str, *, min_length: int = 0) -> list[Any]:
    """Validate that value is a list, optionally with a minimum length."""
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    if len(value) < min_length:
        raise ValueError(f"{path} must have at least {min_length} item(s)")
    return value


def require_string_list(value: Any, path: str, *, min_length: int = 0) -> list[str]:
    """Validate that value is a list of non-empty strings."""
    items = require_list(value, path, min_length=min_length)
    for i, item in enumerate(items):
        require_str(item, f"{path}[{i}]")
    return items


def require_bool(value: Any, path: str) -> bool:
    """Validate that value is a boolean. Rejects truthy/falsy non-booleans."""
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def require_int(value: Any, path: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    """Validate that value is an integer (not a bool). Optionally enforce bounds."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{path} must be <= {maximum}")
    return value


def require_identifier(value: Any, path: str) -> str:
    """Validate that value is a lowercase alphanumeric identifier (hyphens and underscores allowed)."""
    s = require_str(value, path)
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", s):
        raise ValueError(
            f"{path} must be a lowercase identifier (letters, digits, hyphens, underscores; must start with a letter)"
        )
    return s


def require_http_url(value: Any, path: str) -> str:
    """Validate that value is a string starting with http:// or https://."""
    s = require_str(value, path)
    if not s.startswith(("http://", "https://")):
        raise ValueError(f"{path} must be an HTTP(S) URL")
    return s


def require_semver(value: Any, path: str) -> str:
    """Validate that value looks like a semantic version (e.g., 1.2.3, v1.2.3)."""
    s = require_str(value, path)
    import re
    if not re.fullmatch(r"v?\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?", s):
        raise ValueError(f"{path} must be a semantic version (e.g., 1.2.3 or v1.2.3)")
    return s


def require_enum(value: Any, path: str, allowed: set[str] | list[str]) -> str:
    """Validate that value is a string and is one of the allowed values."""
    s = require_str(value, path)
    allowed_set = set(allowed)
    if s not in allowed_set:
        raise ValueError(f"{path} must be one of: {', '.join(sorted(allowed_set))}")
    return s


def require_path(value: Any, path: str) -> str:
    """Validate that value is a non-empty string that looks like a filesystem or URL path (starts with /)."""
    s = require_str(value, path)
    if not s.startswith("/"):
        raise ValueError(f"{path} must be an absolute path starting with /")
    return s


def optional(value: Any, path: str, validator, **kwargs):
    """Apply a validator only if value is not None. Returns None if value is None."""
    if value is None:
        return None
    return validator(value, path, **kwargs)
