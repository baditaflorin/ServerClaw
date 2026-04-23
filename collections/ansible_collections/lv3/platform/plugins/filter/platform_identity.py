"""Platform-identity filter plugin — ADR 0438 Phase 1.

Exposes the canonical identity derivations used across the platform. A single
anchor (`platform_domain`) + flavor-aware derivers produce prefix strings that
are safe for each downstream consumer context:

  - config_prefix: DNS-label shape, unrestricted (e.g. `0fork`)
  - sql_prefix:    PostgreSQL identifier-safe (leading [a-z_]; strips leading
                   non-[a-z_] characters — e.g. `fork` from `0fork`)
  - pve_prefix:    Proxmox VE user-name-safe (leading [A-Za-z]; strips leading
                   digits only, preserves everything else — e.g. `fork` from
                   `0fork`)
  - unix_prefix:   POSIX user-name-safe ([a-z_][a-z0-9_-]*; lowercases,
                   strips non-POSIX characters, ensures leading [a-z_])
  - dns_label:     RFC 1123 label-safe (current semantic: == config_prefix,
                   but kept distinct so a future policy change doesn't have
                   to rename every callsite)

The ADR 0438 lint table binds each callsite to its required flavor. Misuse
(e.g. `platform_sql_prefix` for a Proxmox user name) is a lint error.

Root entry point for plays / templates:

  {{ platform_domain | platform_identity }}

…returns a dict with the five flavors plus domain echo. Individual flavor
filters are exposed for convenience:

  {{ platform_domain | platform_identity_config_prefix }}
  {{ platform_domain | platform_identity_sql_prefix }}
  {{ platform_domain | platform_identity_pve_prefix }}
  {{ platform_domain | platform_identity_unix_prefix }}
  {{ platform_domain | platform_identity_dns_label }}

All derivations are pure functions of `platform_domain`. The plugin does no
I/O, no inventory lookups, no state — so it is cheap to call from any
context (including inventory render-time for shard generation, ADR 0438
Phase 4).
"""
from __future__ import annotations

import re

from ansible.errors import AnsibleFilterError


__all__ = [
    "platform_identity",
    "platform_identity_config_prefix",
    "platform_identity_sql_prefix",
    "platform_identity_pve_prefix",
    "platform_identity_unix_prefix",
    "platform_identity_dns_label",
    "FilterModule",
]


# ---------------------------------------------------------------------------
# Core derivers (plain Python — testable without Ansible)
# ---------------------------------------------------------------------------


def _require_domain(domain) -> str:
    if not isinstance(domain, str):
        raise AnsibleFilterError(
            f"platform_identity: platform_domain must be a string, got {type(domain).__name__}"
        )
    stripped = domain.strip()
    if not stripped:
        raise AnsibleFilterError("platform_identity: platform_domain must not be empty")
    return stripped


def _first_label(domain: str) -> str:
    return _require_domain(domain).split(".", 1)[0]


def _config_prefix(domain: str) -> str:
    """First DNS label. No character restrictions applied."""
    label = _first_label(domain)
    if not label:
        raise AnsibleFilterError(
            f"platform_identity: first DNS label of {domain!r} is empty"
        )
    return label


def _sql_prefix(domain: str) -> str:
    """PostgreSQL identifier-safe prefix.

    Strips leading characters that aren't [a-z_]. Also lowercases to match
    PostgreSQL's case-folding behavior for unquoted identifiers.

    Example: `0fork` -> `fork`, `LV3` -> `lv3`, `123-test` -> `test`.
    """
    label = _config_prefix(domain).lower()
    result = re.sub(r"^[^a-z_]+", "", label)
    if not result:
        raise AnsibleFilterError(
            f"platform_identity: cannot derive sql_prefix from {domain!r} — "
            f"first DNS label {label!r} contains no [a-z_] characters"
        )
    return result


def _pve_prefix(domain: str) -> str:
    """Proxmox VE user-name-safe prefix.

    PVE regex: `^[A-Za-z][A-Za-z0-9\\.\\-_]*`. Strips leading digits only
    (preserves case, preserves mid-string digits, preserves dashes/dots).

    Example: `0fork` -> `fork`, `Lv3` -> `Lv3`, `123test` -> `test`.
    """
    label = _config_prefix(domain)
    result = re.sub(r"^[0-9]+", "", label)
    if not result:
        raise AnsibleFilterError(
            f"platform_identity: cannot derive pve_prefix from {domain!r} — "
            f"first DNS label {label!r} is all digits"
        )
    # PVE also forbids a leading character that isn't [A-Za-z]; after digit
    # stripping, if the next char still isn't a letter we've hit an edge case.
    if not re.match(r"^[A-Za-z]", result):
        raise AnsibleFilterError(
            f"platform_identity: pve_prefix {result!r} derived from {domain!r} "
            f"does not start with a letter"
        )
    return result


def _unix_prefix(domain: str) -> str:
    """POSIX user-name-safe prefix.

    Regex: `[a-z_][a-z0-9_-]*`. Lowercases, strips non-POSIX chars, ensures
    leading [a-z_].

    Example: `0fork` -> `fork`, `LV3` -> `lv3`, `my.domain` -> `mydomain`.
    """
    label = _config_prefix(domain).lower()
    # Keep [a-z0-9_-]
    filtered = re.sub(r"[^a-z0-9_-]", "", label)
    # Strip leading [^a-z_]
    result = re.sub(r"^[^a-z_]+", "", filtered)
    if not result:
        raise AnsibleFilterError(
            f"platform_identity: cannot derive unix_prefix from {domain!r} — "
            f"first DNS label {label!r} produces empty POSIX username"
        )
    return result


def _dns_label(domain: str) -> str:
    """RFC 1123 DNS label.

    Today equals config_prefix. Kept distinct so a future policy change
    (e.g. enforcing lowercase-only) doesn't require renaming every callsite.
    """
    return _config_prefix(domain)


# ---------------------------------------------------------------------------
# Ansible filter entry points
# ---------------------------------------------------------------------------


def platform_identity(domain):
    """Return the full identity dict for a domain.

    Callable as:

        {{ platform_domain | platform_identity }}

    Returns a dict with keys: domain, config_prefix, sql_prefix, pve_prefix,
    unix_prefix, dns_label.
    """
    domain_str = _require_domain(domain)
    return {
        "domain": domain_str,
        "config_prefix": _config_prefix(domain_str),
        "sql_prefix": _sql_prefix(domain_str),
        "pve_prefix": _pve_prefix(domain_str),
        "unix_prefix": _unix_prefix(domain_str),
        "dns_label": _dns_label(domain_str),
    }


def platform_identity_config_prefix(domain):
    return _config_prefix(domain)


def platform_identity_sql_prefix(domain):
    return _sql_prefix(domain)


def platform_identity_pve_prefix(domain):
    return _pve_prefix(domain)


def platform_identity_unix_prefix(domain):
    return _unix_prefix(domain)


def platform_identity_dns_label(domain):
    return _dns_label(domain)


class FilterModule(object):
    def filters(self):
        return {
            "platform_identity": platform_identity,
            "platform_identity_config_prefix": platform_identity_config_prefix,
            "platform_identity_sql_prefix": platform_identity_sql_prefix,
            "platform_identity_pve_prefix": platform_identity_pve_prefix,
            "platform_identity_unix_prefix": platform_identity_unix_prefix,
            "platform_identity_dns_label": platform_identity_dns_label,
        }
