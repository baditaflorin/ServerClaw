"""Smoke test for fork-shape fixture inventories — ADR 0444 item 12.

Each fixture under `tests/fixtures/inventories/*-shape.yml` is a publishable
identity overlay. This test asserts that every fixture:

1. Parses as YAML.
2. Defines the three required scalars (`platform_domain`,
   `platform_operator_email`, `platform_operator_name`).
3. Renders the full `platform_identity` filter (all five flavors) without
   raising.
4. Produces unique `sql_prefix` and `unix_prefix` values across the matrix —
   collisions defeat the purpose of running the matrix because a role
   passing on lv3 by accident also passes on the fork.
5. Matches the expected per-fixture identity derivations encoded below.
   Updating a fixture without updating EXPECTED_FIXTURES is a test failure
   by design.

The test imports the platform_identity filter directly without a full
Ansible install, mirroring tests/test_platform_identity_filters.py.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "inventories"
PLATFORM_IDENTITY_MODULE = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "plugins"
    / "filter"
    / "platform_identity.py"
)

REQUIRED_SCALARS = (
    "platform_domain",
    "platform_operator_email",
    "platform_operator_name",
)

EXPECTED_FIXTURES = {
    "lv3-shape.yml": {
        "platform_domain": "lv3.example.invalid",
        "identity": {
            "config_prefix": "lv3",
            "sql_prefix": "lv3",
            "pve_prefix": "lv3",
            "unix_prefix": "lv3",
            "dns_label": "lv3",
        },
    },
    "0fork-shape.yml": {
        "platform_domain": "0fork.example.invalid",
        "identity": {
            "config_prefix": "0fork",
            "sql_prefix": "fork",
            "pve_prefix": "fork",
            "unix_prefix": "fork",
            "dns_label": "0fork",
        },
    },
    "synthetic-shape.yml": {
        "platform_domain": "testfork.invalid",
        "identity": {
            "config_prefix": "testfork",
            "sql_prefix": "testfork",
            "pve_prefix": "testfork",
            "unix_prefix": "testfork",
            "dns_label": "testfork",
        },
    },
}


def _load_platform_identity():
    """Load the platform_identity filter module with a stubbed ansible.errors."""
    ansible_module = types.ModuleType("ansible")
    ansible_errors = types.ModuleType("ansible.errors")

    class AnsibleFilterError(Exception):
        pass

    ansible_errors.AnsibleFilterError = AnsibleFilterError
    ansible_module.errors = ansible_errors
    sys.modules.setdefault("ansible", ansible_module)
    sys.modules["ansible.errors"] = ansible_errors
    spec = importlib.util.spec_from_file_location("platform_identity_for_fixtures", PLATFORM_IDENTITY_MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def platform_identity():
    return _load_platform_identity()


@pytest.fixture(scope="module")
def fixture_files():
    files = sorted(FIXTURE_DIR.glob("*-shape.yml"))
    assert files, f"no *-shape.yml fixtures found under {FIXTURE_DIR}"
    return files


def test_every_fixture_is_indexed(fixture_files):
    """Every committed fixture must appear in EXPECTED_FIXTURES."""
    on_disk = {f.name for f in fixture_files}
    indexed = set(EXPECTED_FIXTURES)
    missing = on_disk - indexed
    extra = indexed - on_disk
    assert not missing, (
        f"fixture files exist on disk but are not indexed in EXPECTED_FIXTURES: "
        f"{sorted(missing)}. Update tests/test_fixture_inventories.py."
    )
    assert not extra, f"EXPECTED_FIXTURES references fixtures that don't exist on disk: {sorted(extra)}."


@pytest.mark.parametrize("fixture_name", sorted(EXPECTED_FIXTURES))
def test_fixture_parses_and_has_required_scalars(fixture_name):
    path = FIXTURE_DIR / fixture_name
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), f"{fixture_name}: top-level must be a mapping"
    for key in REQUIRED_SCALARS:
        assert key in data, f"{fixture_name}: missing required scalar {key!r}"
        assert isinstance(data[key], str) and data[key].strip(), f"{fixture_name}: {key!r} must be a non-empty string"


@pytest.mark.parametrize("fixture_name", sorted(EXPECTED_FIXTURES))
def test_fixture_domain_matches_expected(fixture_name):
    path = FIXTURE_DIR / fixture_name
    data = yaml.safe_load(path.read_text())
    expected_domain = EXPECTED_FIXTURES[fixture_name]["platform_domain"]
    assert data["platform_domain"] == expected_domain, (
        f"{fixture_name}: platform_domain drifted from EXPECTED_FIXTURES — "
        f"got {data['platform_domain']!r}, expected {expected_domain!r}. "
        f"Update both together."
    )


@pytest.mark.parametrize("fixture_name", sorted(EXPECTED_FIXTURES))
def test_fixture_renders_platform_identity(fixture_name, platform_identity):
    path = FIXTURE_DIR / fixture_name
    data = yaml.safe_load(path.read_text())
    identity = platform_identity.platform_identity(data["platform_domain"])
    expected = EXPECTED_FIXTURES[fixture_name]["identity"]
    for flavor, expected_value in expected.items():
        assert identity[flavor] == expected_value, (
            f"{fixture_name}: platform_identity.{flavor} = {identity[flavor]!r}, expected {expected_value!r}"
        )
        assert identity[flavor], f"{fixture_name}: platform_identity.{flavor} is empty"


def test_sql_and_unix_prefixes_are_unique_across_matrix(platform_identity):
    """Two fixtures must not collide on sql_prefix or unix_prefix.

    A collision means a role bug that derives from sql_prefix or unix_prefix
    can pass against one fixture by coincidence and fail against another —
    exactly the regression the matrix is built to catch.
    """
    sql_prefixes: dict[str, str] = {}
    unix_prefixes: dict[str, str] = {}
    for fixture_name, expected in EXPECTED_FIXTURES.items():
        identity = platform_identity.platform_identity(expected["platform_domain"])
        sql = identity["sql_prefix"]
        unix = identity["unix_prefix"]
        assert sql not in sql_prefixes, (
            f"sql_prefix collision: {fixture_name} and {sql_prefixes[sql]} both resolve to {sql!r}"
        )
        assert unix not in unix_prefixes, (
            f"unix_prefix collision: {fixture_name} and {unix_prefixes[unix]} both resolve to {unix!r}"
        )
        sql_prefixes[sql] = fixture_name
        unix_prefixes[unix] = fixture_name


def test_matrix_covers_distinct_shape_paths(platform_identity):
    """Confirm the matrix exercises both the equal-flavor and divergent-flavor
    code paths.

    - Equal-flavor: at least one fixture where every flavor produces the
      same string (lv3-shape, synthetic-shape).
    - Divergent-flavor: at least one fixture where sql/unix/pve diverge from
      config_prefix (0fork-shape — leading digit stripped).

    Without both, a regression in the digit-stripping path could land
    undetected.
    """
    saw_equal = False
    saw_divergent = False
    for expected in EXPECTED_FIXTURES.values():
        identity = platform_identity.platform_identity(expected["platform_domain"])
        if (
            identity["config_prefix"]
            == identity["sql_prefix"]
            == identity["pve_prefix"]
            == identity["unix_prefix"]
            == identity["dns_label"]
        ):
            saw_equal = True
        if identity["config_prefix"] != identity["sql_prefix"]:
            saw_divergent = True
    assert saw_equal, "matrix lacks an equal-flavor fixture"
    assert saw_divergent, (
        "matrix lacks a divergent-flavor fixture (one where sql_prefix "
        "differs from config_prefix). The digit-stripping path is uncovered."
    )
