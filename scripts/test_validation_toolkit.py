"""Simple test suite for validation_toolkit — run with: python scripts/test_validation_toolkit.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import (
    require_str,
    require_mapping,
    require_list,
    require_string_list,
    require_bool,
    require_int,
    require_identifier,
    require_http_url,
    require_semver,
    require_enum,
    require_path,
    optional,
)


def test_require_str():
    assert require_str("hello", "x") == "hello"
    try:
        require_str(123, "x")
        assert False
    except ValueError:
        pass
    try:
        require_str("", "x")
        assert False
    except ValueError:
        pass
    try:
        require_str("  ", "x")
        assert False
    except ValueError:
        pass
    assert require_str("", "x", allow_empty=True) == ""


def test_require_mapping():
    assert require_mapping({"a": 1}, "x") == {"a": 1}
    try:
        require_mapping([], "x")
        assert False
    except ValueError:
        pass
    try:
        require_mapping("str", "x")
        assert False
    except ValueError:
        pass


def test_require_list():
    assert require_list([1, 2], "x") == [1, 2]
    try:
        require_list({}, "x")
        assert False
    except ValueError:
        pass
    try:
        require_list([1], "x", min_length=2)
        assert False
    except ValueError:
        pass


def test_require_string_list():
    assert require_string_list(["a", "b"], "x") == ["a", "b"]
    try:
        require_string_list([1, 2], "x")
        assert False
    except ValueError:
        pass


def test_require_bool():
    assert require_bool(True, "x") is True
    assert require_bool(False, "x") is False
    try:
        require_bool(1, "x")
        assert False
    except ValueError:
        pass
    try:
        require_bool("true", "x")
        assert False
    except ValueError:
        pass


def test_require_int():
    assert require_int(42, "x") == 42
    try:
        require_int(True, "x")
        assert False
    except ValueError:
        pass
    try:
        require_int("1", "x")
        assert False
    except ValueError:
        pass
    try:
        require_int(5, "x", minimum=10)
        assert False
    except ValueError:
        pass
    try:
        require_int(15, "x", maximum=10)
        assert False
    except ValueError:
        pass


def test_require_identifier():
    assert require_identifier("hello", "x") == "hello"
    assert require_identifier("hello-world_123", "x") == "hello-world_123"
    try:
        require_identifier("Hello", "x")
        assert False
    except ValueError:
        pass
    try:
        require_identifier("1abc", "x")
        assert False
    except ValueError:
        pass


def test_require_http_url():
    assert require_http_url("http://example.com", "x") == "http://example.com"
    assert require_http_url("https://example.com/path", "x") == "https://example.com/path"
    try:
        require_http_url("ftp://example.com", "x")
        assert False
    except ValueError:
        pass


def test_require_semver():
    assert require_semver("1.2.3", "x") == "1.2.3"
    assert require_semver("v1.2.3", "x") == "v1.2.3"
    try:
        require_semver("1.2", "x")
        assert False
    except ValueError:
        pass


def test_require_enum():
    assert require_enum("a", "x", ["a", "b", "c"]) == "a"
    try:
        require_enum("d", "x", ["a", "b", "c"])
        assert False
    except ValueError:
        pass


def test_require_path():
    assert require_path("/etc/foo", "x") == "/etc/foo"
    try:
        require_path("relative/path", "x")
        assert False
    except ValueError:
        pass


def test_optional():
    assert optional(None, "x", require_str) is None
    assert optional("hello", "x", require_str) == "hello"


if __name__ == "__main__":
    test_require_str()
    test_require_mapping()
    test_require_list()
    test_require_string_list()
    test_require_bool()
    test_require_int()
    test_require_identifier()
    test_require_http_url()
    test_require_semver()
    test_require_enum()
    test_require_path()
    test_optional()
    print("All tests passed.")
