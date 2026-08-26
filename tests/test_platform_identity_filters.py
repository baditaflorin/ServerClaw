"""Unit tests for the platform_identity filter plugin — ADR 0438 Phase 1.

Covers the five flavors (config, sql, pve, unix, dns_label) across a matrix
of identity inputs that exercise the real edge cases we have seen or expect:

  - `lv3`         — production deployment, all flavors equal
  - `0fork`       — leading digit (triggers sql/pve/unix divergence)
  - `UPPERCASE`   — case folding divergence
  - `with-dashes` — dash handling
  - `_under_`     — leading underscore (sql-safe, not POSIX-safe-leading)
  - `123`         — all-digits edge case (pve/sql must fail loudly)

The test harness mirrors test_service_topology_filters.py: dynamically
loads the plugin without a full Ansible install, stubs AnsibleFilterError.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "plugins"
    / "filter"
    / "platform_identity.py"
)


def _load_module():
    """Import the filter module with a stubbed ansible.errors package."""
    ansible_module = types.ModuleType("ansible")
    ansible_errors = types.ModuleType("ansible.errors")

    class AnsibleFilterError(Exception):
        pass

    ansible_errors.AnsibleFilterError = AnsibleFilterError
    ansible_module.errors = ansible_errors
    sys.modules.setdefault("ansible", ansible_module)
    sys.modules["ansible.errors"] = ansible_errors
    spec = importlib.util.spec_from_file_location("platform_identity_filters", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plugin():
    return _load_module()


# ---------------------------------------------------------------------------
# Happy-path matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "domain,expected",
    [
        (
            "example.com",
            {
                "config_prefix": "lv3",
                "sql_prefix": "lv3",
                "pve_prefix": "lv3",
                "unix_prefix": "lv3",
                "dns_label": "lv3",
            },
        ),
        (
            "example.org",
            {
                "config_prefix": "0fork",
                "sql_prefix": "fork",  # leading digit stripped
                "pve_prefix": "fork",  # leading digit stripped
                "unix_prefix": "fork",  # leading digit stripped
                "dns_label": "0fork",
            },
        ),
        (
            "LV3.org",
            {
                "config_prefix": "LV3",  # preserved
                "sql_prefix": "lv3",  # lowercased
                "pve_prefix": "LV3",  # preserved (PVE is case-sensitive-ok)
                "unix_prefix": "lv3",  # lowercased
                "dns_label": "LV3",  # preserved
            },
        ),
        (
            "my-org.net",
            {
                "config_prefix": "my-org",
                "sql_prefix": "my-org",  # unquoted PG ident with dash is user's call
                "pve_prefix": "my-org",
                "unix_prefix": "my-org",
                "dns_label": "my-org",
            },
        ),
    ],
)
def test_flavors_full_dict(plugin, domain, expected):
    """Happy path: every flavor produces the expected value.

    Cases where a specific flavor should FAIL for a given input are covered
    below in per-flavor error tests (e.g. `_internal.local` vs pve_prefix).
    """
    identity = plugin.platform_identity(domain)
    assert identity["domain"] == domain
    for flavor, value in expected.items():
        assert identity.get(flavor) == value, f"{flavor}({domain!r}) -> {identity.get(flavor)!r}, expected {value!r}"


def test_leading_underscore_sql_unix_accept_pve_rejects(plugin):
    """`_internal.local` — sql/unix/config/dns accept; pve must reject."""
    from ansible.errors import AnsibleFilterError

    assert plugin.platform_identity_config_prefix("_internal.local") == "_internal"
    assert plugin.platform_identity_sql_prefix("_internal.local") == "_internal"
    assert plugin.platform_identity_unix_prefix("_internal.local") == "_internal"
    assert plugin.platform_identity_dns_label("_internal.local") == "_internal"
    with pytest.raises(AnsibleFilterError, match="pve_prefix"):
        plugin.platform_identity_pve_prefix("_internal.local")
    # Also, the full-dict form propagates the pve failure.
    with pytest.raises(AnsibleFilterError, match="pve_prefix"):
        plugin.platform_identity("_internal.local")


def test_dict_shape(plugin):
    identity = plugin.platform_identity("example.org")
    assert set(identity.keys()) == {
        "domain",
        "config_prefix",
        "sql_prefix",
        "pve_prefix",
        "unix_prefix",
        "dns_label",
    }


def test_individual_flavor_filters(plugin):
    assert plugin.platform_identity_config_prefix("example.org") == "0fork"
    assert plugin.platform_identity_sql_prefix("example.org") == "fork"
    assert plugin.platform_identity_pve_prefix("example.org") == "fork"
    assert plugin.platform_identity_unix_prefix("example.org") == "fork"
    assert plugin.platform_identity_dns_label("example.org") == "0fork"


def test_filter_module_exposes_all_filters(plugin):
    filters = plugin.FilterModule().filters()
    assert set(filters.keys()) == {
        "platform_identity",
        "platform_identity_config_prefix",
        "platform_identity_sql_prefix",
        "platform_identity_pve_prefix",
        "platform_identity_unix_prefix",
        "platform_identity_dns_label",
    }
    # Sanity: every advertised callable actually executes.
    for name, fn in filters.items():
        result = fn("example.org")
        assert result is not None, f"filter {name!r} returned None"


# ---------------------------------------------------------------------------
# Error paths — must fail loudly, never silently return empty strings.
# ---------------------------------------------------------------------------


def test_empty_domain_raises(plugin):
    from ansible.errors import AnsibleFilterError

    with pytest.raises(AnsibleFilterError, match="must not be empty"):
        plugin.platform_identity("")


def test_non_string_domain_raises(plugin):
    from ansible.errors import AnsibleFilterError

    with pytest.raises(AnsibleFilterError, match="must be a string"):
        plugin.platform_identity(None)
    with pytest.raises(AnsibleFilterError, match="must be a string"):
        plugin.platform_identity(42)


def test_all_digit_label_fails_sql(plugin):
    from ansible.errors import AnsibleFilterError

    # Config prefix of `123.test` is `123`; sql_prefix strips all leading
    # non-[a-z_] and runs out of characters.
    with pytest.raises(AnsibleFilterError, match="sql_prefix"):
        plugin.platform_identity_sql_prefix("123.test")


def test_all_digit_label_fails_pve(plugin):
    from ansible.errors import AnsibleFilterError

    with pytest.raises(AnsibleFilterError, match="pve_prefix"):
        plugin.platform_identity_pve_prefix("123.test")


def test_underscore_leading_fails_pve(plugin):
    from ansible.errors import AnsibleFilterError

    # PVE regex requires [A-Za-z] leading — underscore is forbidden.
    with pytest.raises(AnsibleFilterError, match="pve_prefix"):
        plugin.platform_identity_pve_prefix("_internal.local")


def test_underscore_leading_fails_unix_after_strip(plugin):
    """A pure leading-underscore label is allowed for unix (POSIX [a-z_] lead)."""
    # This SHOULD succeed — underscore is a valid POSIX leading char.
    assert plugin.platform_identity_unix_prefix("_internal.local") == "_internal"


def test_pve_preserves_case(plugin):
    """PVE user names are case-sensitive; we should not lowercase."""
    assert plugin.platform_identity_pve_prefix("LV3.org") == "LV3"
    assert plugin.platform_identity_pve_prefix("MyOrg.com") == "MyOrg"


def test_sql_lowercases(plugin):
    """PostgreSQL folds unquoted identifiers to lowercase; pre-empt surprise."""
    assert plugin.platform_identity_sql_prefix("LV3.org") == "lv3"


def test_production_invariant_lv3(plugin):
    """On the author's production deployment, all five flavors must equal 'lv3'."""
    identity = plugin.platform_identity("example.com")
    assert identity["config_prefix"] == "lv3"
    assert identity["sql_prefix"] == "lv3"
    assert identity["pve_prefix"] == "lv3"
    assert identity["unix_prefix"] == "lv3"
    assert identity["dns_label"] == "lv3"


def test_fork_flavor_divergence(plugin):
    """On the 0fork clone, config/dns keep '0fork' while sql/pve/unix strip digit."""
    identity = plugin.platform_identity("example.org")
    assert identity["config_prefix"] == "0fork"
    assert identity["dns_label"] == "0fork"
    assert identity["sql_prefix"] == "fork"
    assert identity["pve_prefix"] == "fork"
    assert identity["unix_prefix"] == "fork"
    # The 0fork-automation@pve vs fork-automation@pve bug surfaced this session:
    # sql and pve coincide for 0fork but they're semantically distinct and would
    # diverge on, e.g., 'lv3_fork' (sql: lv3_fork, pve: lv3_fork — both valid).
