#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import (
    optional,
    require_bool,
    require_enum,
    require_http_url,
    require_identifier,
    require_int,
    require_list,
    require_mapping,
    require_path,
    require_semver,
    require_str,
    require_string_list,
)


def assert_value_error(fn, message: str) -> None:
    try:
        fn()
    except ValueError as exc:
        assert str(exc) == message
    else:
        raise AssertionError(f"expected ValueError: {message}")


def main() -> None:
    assert require_str("hello", "field") == "hello"
    assert require_str("  ", "field", allow_empty=True) == "  "
    assert_value_error(lambda: require_str(1, "field"), "field must be a non-empty string")
    assert_value_error(lambda: require_str("  ", "field"), "field must be a non-empty string")

    mapping = {"key": "value"}
    assert require_mapping(mapping, "obj") is mapping
    assert_value_error(lambda: require_mapping([], "obj"), "obj must be an object")

    values = [1, 2]
    assert require_list(values, "items", min_length=2) is values
    assert_value_error(lambda: require_list({}, "items"), "items must be a list")
    assert_value_error(lambda: require_list([], "items", min_length=1), "items must have at least 1 item(s)")

    strings = ["a", "b"]
    assert require_string_list(strings, "items", min_length=2) is strings
    assert_value_error(lambda: require_string_list(["a", ""], "items"), "items[1] must be a non-empty string")

    assert require_bool(True, "flag") is True
    assert_value_error(lambda: require_bool(1, "flag"), "flag must be a boolean")

    assert require_int(3, "count", minimum=1, maximum=5) == 3
    assert_value_error(lambda: require_int(True, "count"), "count must be an integer")
    assert_value_error(lambda: require_int(0, "count", minimum=1), "count must be >= 1")
    assert_value_error(lambda: require_int(6, "count", maximum=5), "count must be <= 5")

    assert require_identifier("alpha_1", "id") == "alpha_1"
    assert_value_error(
        lambda: require_identifier("1alpha", "id"),
        "id must be a lowercase identifier (letters, digits, hyphens, underscores; must start with a letter)",
    )

    assert require_http_url("https://example.com", "url") == "https://example.com"
    assert_value_error(lambda: require_http_url("ftp://example.com", "url"), "url must be an HTTP(S) URL")

    assert require_semver("v1.2.3", "version") == "v1.2.3"
    assert_value_error(
        lambda: require_semver("1.2", "version"),
        "version must be a semantic version (e.g., 1.2.3 or v1.2.3)",
    )

    assert require_enum("green", "color", {"green", "blue"}) == "green"
    assert_value_error(lambda: require_enum("red", "color", {"green", "blue"}), "color must be one of: blue, green")

    assert require_path("/tmp/file", "path") == "/tmp/file"
    assert_value_error(lambda: require_path("tmp/file", "path"), "path must be an absolute path starting with /")

    assert optional(None, "field", require_str) is None
    assert optional("value", "field", require_str) == "value"
    assert_value_error(lambda: optional("", "field", require_str), "field must be a non-empty string")


if __name__ == "__main__":
    main()
