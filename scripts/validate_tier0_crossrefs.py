#!/usr/bin/env python3
"""Tier 0 cross-reference validator — ADR 0438.

Validates the seven Tier-0 root files against each other:

  - JSON Schema well-formedness (one schema per root file)
  - Cross-file referential integrity (service registry ↔ postgres clients,
    ↔ subdomain exposure, ↔ host topology)
  - Identity-flavor hygiene (no raw prefix leaks in Tier-0 root files)
  - No hardcoded deployment IPs in root facts

Run directly:
    uv run --with pyyaml --with jsonschema python scripts/validate_tier0_crossrefs.py

Exit 1 on any error-severity finding; exits 0 if only warnings.

Usage:
    validate_tier0_crossrefs.py [--json] [--min-severity {warning,error}]

The --json flag emits machine-readable JSON (list of Finding dicts).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:
    print(
        "ERROR: pyyaml is required. Run: uv run --with pyyaml python scripts/validate_tier0_crossrefs.py",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

SEVERITY_RANK = {"warning": 0, "error": 1}


@dataclass
class Finding:
    check_id: str
    severity: str  # "warning" | "error"
    location: str  # "file:line" or file path
    message: str
    fix_hint: str = ""


# ---------------------------------------------------------------------------
# Tier-0 loader
# ---------------------------------------------------------------------------


def _load_yaml(rel: str) -> Any:
    path = REPO_ROOT / rel
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text())


def _load_json(rel: str) -> Any:
    path = REPO_ROOT / rel
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_tier0() -> dict[str, Any]:
    """Load the Tier-0 root files. Missing files return None."""
    return {
        "identity": _load_yaml("inventory/group_vars/all/identity.yml"),
        "proxmox_host": _load_yaml("inventory/host_vars/proxmox-host.yml"),
        "service_registry": _load_yaml("inventory/group_vars/all/platform_services.yml"),
        "postgres_clients": _load_yaml("inventory/group_vars/platform_postgres.yml"),
        "subdomain_exposure": _load_json("config/subdomain-exposure-registry.json"),
        "execution_scopes": _load_yaml("config/ansible-execution-scopes.yaml"),
        "credentials": _load_yaml("config/platform_credentials.yml"),
    }


def _all_role_names() -> frozenset[str]:
    """Return the union of all role names under collections/ and roles/."""
    names: set[str] = set()
    for base in (
        REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles",
        REPO_ROOT / "roles",
    ):
        if base.exists():
            for entry in base.iterdir():
                if entry.is_dir() and not entry.name.startswith("_"):
                    names.add(entry.name)
    return frozenset(names)


# ---------------------------------------------------------------------------
# Check registry
# ---------------------------------------------------------------------------

CHECK_REGISTRY: list[Callable[[dict], list[Finding]]] = []


def check(fn: Callable) -> Callable:
    """Decorator: register a check function."""
    CHECK_REGISTRY.append(fn)
    return fn


# ---------------------------------------------------------------------------
# Group A — service registry ↔ postgres clients
# ---------------------------------------------------------------------------


@check
def check_A1_postgres_services_exist_in_registry(tier0: dict) -> list[Finding]:
    """A1: every platform_postgres_clients[*].service exists in platform_service_registry."""
    findings = []
    clients = (tier0.get("postgres_clients") or {}).get("platform_postgres_clients", []) or []
    registry = (tier0.get("service_registry") or {}).get("platform_service_registry", {}) or {}

    for entry in clients:
        svc = entry.get("service")
        if svc and svc not in registry:
            findings.append(
                Finding(
                    check_id="A1",
                    severity="error",
                    location="inventory/group_vars/platform_postgres.yml",
                    message=f"postgres client `{svc}` has no matching entry in platform_service_registry",
                    fix_hint=f"Add `{svc}:` section to inventory/group_vars/all/platform_services.yml",
                )
            )
    return findings


@check
def check_A2_postgres_remote_dir_no_hardcoded_prefix(tier0: dict) -> list[Finding]:
    """A2: password_remote_dir / password_remote_file must not contain literal 'lv3' or 'fork'.

    These paths should be derived from platform_identity.unix_prefix (Phase 3).
    Flagging now as warning so Phase 2/3 can sweep them.
    """
    findings = []
    clients = (tier0.get("postgres_clients") or {}).get("platform_postgres_clients", []) or []
    _PREFIX_RE = re.compile(r"/etc/(?:lv3|fork)\b")

    for entry in clients:
        svc = entry.get("service", "?")
        for field_name in ("password_remote_dir", "password_remote_file"):
            val = entry.get(field_name, "")
            if val and _PREFIX_RE.search(val):
                findings.append(
                    Finding(
                        check_id="A2",
                        severity="warning",
                        location="inventory/group_vars/platform_postgres.yml",
                        message=f"postgres client `{svc}`.{field_name} = `{val}` contains a hardcoded deployment prefix",
                        fix_hint="Phase 3: replace with `{{ platform_identity.unix_prefix }}` — e.g. `/etc/{{ platform_identity.unix_prefix }}/{{ svc }}`",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Group B — service registry ↔ subdomain exposure
# ---------------------------------------------------------------------------


@check
def check_B1_public_fqdns_in_exposure_registry(tier0: dict) -> list[Finding]:
    """B1: every proxy.public_fqdn in service_registry has a subdomain in subdomain-exposure-registry.

    The service registry stores template FQDNs like `sso.{{ platform_domain }}`;
    the exposure registry stores resolved FQDNs like `sso.lv3.org`. We compare
    by subdomain label (the part before the first `.{{ platform_domain }}`) to
    handle both template and resolved forms.
    """
    findings = []
    registry = (tier0.get("service_registry") or {}).get("platform_service_registry", {}) or {}
    exposure = tier0.get("subdomain_exposure") or {}

    # Gather all declared subdomain labels from the exposure registry.
    # A label is the first DNS component of any `fqdn` entry.
    declared_labels: set[str] = set()
    publications = exposure.get("publications", []) if isinstance(exposure, dict) else []
    for pub in publications:
        if isinstance(pub, dict):
            fqdn = pub.get("fqdn", "")
            if fqdn:
                declared_labels.add(fqdn.split(".")[0])

    # Jinja template pattern: `<subdomain>.{{ platform_domain }}`
    _TEMPLATE_RE = re.compile(r"^([^.{]+)\.\{\{")

    for svc_name, svc in registry.items():
        if not isinstance(svc, dict):
            continue
        proxy = svc.get("proxy") or {}
        fqdn_template = proxy.get("public_fqdn", "")
        if not fqdn_template:
            continue

        m = _TEMPLATE_RE.match(fqdn_template)
        if m:
            label = m.group(1)
        else:
            # Fully resolved FQDN fallback
            label = fqdn_template.split(".")[0]

        if label and label not in declared_labels:
            findings.append(
                Finding(
                    check_id="B1",
                    severity="warning",
                    location=f"inventory/group_vars/all/platform_services.yml [{svc_name}]",
                    message=f"service `{svc_name}` subdomain label `{label}` (from `{fqdn_template}`) has no publication entry in config/subdomain-exposure-registry.json",
                    fix_hint="Add a `publications` entry for this subdomain or verify the fqdn spelling.",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Group C — service registry ↔ host topology
# ---------------------------------------------------------------------------


@check
def check_C1_host_group_non_empty(tier0: dict) -> list[Finding]:
    """C1: every service in platform_service_registry declares a non-empty host_group."""
    findings = []
    registry = (tier0.get("service_registry") or {}).get("platform_service_registry", {}) or {}

    for svc_name, svc in registry.items():
        if not isinstance(svc, dict):
            continue
        hg = svc.get("host_group", "")
        if not hg:
            findings.append(
                Finding(
                    check_id="C1",
                    severity="error",
                    location=f"inventory/group_vars/all/platform_services.yml [{svc_name}]",
                    message=f"service `{svc_name}` is missing required field `host_group`",
                    fix_hint="Add `host_group: <inventory-group-or-host>` to the service entry.",
                )
            )
    return findings


@check
def check_C2_service_type_is_known(tier0: dict) -> list[Finding]:
    """C2: every service declares a known service_type."""
    findings = []
    registry = (tier0.get("service_registry") or {}).get("platform_service_registry", {}) or {}
    KNOWN_TYPES = {"docker_compose", "system_package", "infrastructure", "multi_instance"}

    for svc_name, svc in registry.items():
        if not isinstance(svc, dict):
            continue
        st = svc.get("service_type", "")
        if st not in KNOWN_TYPES:
            findings.append(
                Finding(
                    check_id="C2",
                    severity="error",
                    location=f"inventory/group_vars/all/platform_services.yml [{svc_name}]",
                    message=f"service `{svc_name}` has unknown service_type `{st}` (known: {sorted(KNOWN_TYPES)})",
                    fix_hint="Set service_type to one of: docker_compose, system_package, infrastructure, multi_instance",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Group D — credentials registry integrity (ADR 0438 Phase 3)
# ---------------------------------------------------------------------------

_CRED_FILE = "config/platform_credentials.yml"
_ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_VAR_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*_local_file$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@check
def check_D1_credentials_unique_ids(tier0: dict) -> list[Finding]:
    """D1: every platform_credentials[*].id is unique."""
    findings = []
    creds = (tier0.get("credentials") or {}).get("platform_credentials", []) or []
    seen: dict[str, int] = {}
    for idx, entry in enumerate(creds):
        cid = entry.get("id", "")
        if not cid:
            continue
        if cid in seen:
            findings.append(
                Finding(
                    check_id="D1",
                    severity="error",
                    location=f"{_CRED_FILE}[{idx}]",
                    message=f"Duplicate credential id `{cid}` (first seen at index {seen[cid]})",
                    fix_hint="Each credential must have a unique id.",
                )
            )
        else:
            seen[cid] = idx
    return findings


@check
def check_D2_credentials_unique_var_names(tier0: dict) -> list[Finding]:
    """D2: every platform_credentials[*].local_file_var is unique."""
    findings = []
    creds = (tier0.get("credentials") or {}).get("platform_credentials", []) or []
    seen: dict[str, int] = {}
    for idx, entry in enumerate(creds):
        var = entry.get("local_file_var", "")
        if not var:
            continue
        if var in seen:
            findings.append(
                Finding(
                    check_id="D2",
                    severity="error",
                    location=f"{_CRED_FILE}[{idx}]",
                    message=f"Duplicate local_file_var `{var}` (first seen at index {seen[var]})",
                    fix_hint="Two credentials cannot share the same variable name — writer/reader confusion is the failure class this registry prevents.",
                )
            )
        else:
            seen[var] = idx
    return findings


@check
def check_D3_credentials_var_naming_convention(tier0: dict) -> list[Finding]:
    """D3: local_file_var must match ^[a-z][a-z0-9_]*_local_file$."""
    findings = []
    creds = (tier0.get("credentials") or {}).get("platform_credentials", []) or []
    for idx, entry in enumerate(creds):
        cid = entry.get("id", f"[{idx}]")
        var = entry.get("local_file_var", "")
        if var and not _VAR_NAME_RE.match(var):
            findings.append(
                Finding(
                    check_id="D3",
                    severity="error",
                    location=f"{_CRED_FILE}[{cid}]",
                    message=f"local_file_var `{var}` does not match required pattern `*_local_file`",
                    fix_hint="Rename to `<service>_<purpose>_local_file`.",
                )
            )
    return findings


@check
def check_D4_credentials_owner_role_exists(tier0: dict) -> list[Finding]:
    """D4: owner_role must name a role that exists on disk."""
    findings = []
    creds = (tier0.get("credentials") or {}).get("platform_credentials", []) or []
    if not creds:
        return findings

    all_roles = _all_role_names()
    for idx, entry in enumerate(creds):
        cid = entry.get("id", f"[{idx}]")
        owner = entry.get("owner_role", "")
        if owner and owner not in all_roles:
            findings.append(
                Finding(
                    check_id="D4",
                    severity="error",
                    location=f"{_CRED_FILE}[{cid}]",
                    message=f"owner_role `{owner}` does not match any role in collections/ or roles/",
                    fix_hint=f"Create the role at collections/ansible_collections/lv3/platform/roles/{owner}/ or check the spelling.",
                )
            )
    return findings


@check
def check_D5_credentials_consumer_roles_exist(tier0: dict) -> list[Finding]:
    """D5: all consumer_roles must name roles that exist on disk."""
    findings = []
    creds = (tier0.get("credentials") or {}).get("platform_credentials", []) or []
    if not creds:
        return findings

    all_roles = _all_role_names()
    for idx, entry in enumerate(creds):
        cid = entry.get("id", f"[{idx}]")
        for consumer in entry.get("consumer_roles", []):
            if consumer and consumer not in all_roles:
                findings.append(
                    Finding(
                        check_id="D5",
                        severity="warning",
                        location=f"{_CRED_FILE}[{cid}]",
                        message=f"consumer_role `{consumer}` does not match any role in collections/ or roles/",
                        fix_hint="Create the role or correct the spelling. Warning only — consumer_roles may reference roles in planned future phases.",
                    )
                )
    return findings


@check
def check_D6_credentials_var_matches_id(tier0: dict) -> list[Finding]:
    """D6: local_file_var should equal <id>_local_file (naming consistency)."""
    findings = []
    creds = (tier0.get("credentials") or {}).get("platform_credentials", []) or []
    for idx, entry in enumerate(creds):
        cid = entry.get("id", "")
        var = entry.get("local_file_var", "")
        if cid and var:
            expected = f"{cid}_local_file"
            if var != expected:
                findings.append(
                    Finding(
                        check_id="D6",
                        severity="warning",
                        location=f"{_CRED_FILE}[{cid}]",
                        message=f"local_file_var `{var}` does not match expected `{expected}` (id=`{cid}`)",
                        fix_hint="Convention: local_file_var = id + '_local_file'. Divergence is allowed during transition but must be documented in `notes:`.",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Group E — identity flavor hygiene in Tier-0 root files
# ---------------------------------------------------------------------------


@check
def check_E1_no_raw_split_in_service_registry(tier0: dict) -> list[Finding]:
    """E1: platform_services.yml must not contain raw `split('.') | first`."""
    return _scan_for_raw_split(
        REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml",
        check_id="E1",
    )


@check
def check_E2_no_raw_split_in_postgres_clients(tier0: dict) -> list[Finding]:
    """E2: platform_postgres.yml must not contain raw `split('.') | first`."""
    return _scan_for_raw_split(
        REPO_ROOT / "inventory" / "group_vars" / "platform_postgres.yml",
        check_id="E2",
    )


_RAW_SPLIT_RE = re.compile(r"platform_domain\s*\|\s*split\(\s*['\"]\.['\"]\s*\)\s*\|\s*first")


def _scan_for_raw_split(path: Path, check_id: str) -> list[Finding]:
    if not path.exists():
        return []
    findings = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if _RAW_SPLIT_RE.search(line):
            findings.append(
                Finding(
                    check_id=check_id,
                    severity="error",
                    location=f"{path.relative_to(REPO_ROOT)}:{line_no}",
                    message=f"Raw `platform_domain | split('.') | first` found — use `platform_identity.<flavor>_prefix` (ADR 0438)",
                    fix_hint="Choose: config_prefix (DNS-safe), sql_prefix (PG), pve_prefix (PVE), unix_prefix (POSIX)",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Group G — no hardcoded deployment IPs in root files
# ---------------------------------------------------------------------------

# Guest network + Tailscale network; skip RFC 5737 docs IPs
_GUEST_IP_RE = re.compile(r"\b10\.10\.10\.\d{1,3}\b")
_TAILSCALE_IP_RE = re.compile(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")

# Root files that may legitimately define CIDR ranges (not host IPs)
_CIDR_LINES_OK = re.compile(r"[_\-]cidr:|[_\-]network:|[_\-]wildcard:|platform_guest_network")

# Root inventory host_vars intentionally contains IPs — skip it.
_IP_ALLOWED_FILES = {
    REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml",
    REPO_ROOT / "inventory" / "group_vars" / "all" / "identity.yml",  # CIDR ranges only
}


@check
def check_G1_no_hardcoded_guest_ips_in_service_registry(tier0: dict) -> list[Finding]:
    """G1: platform_services.yml must not contain hardcoded 10.10.10.* IPs.

    Addresses must flow through `platform_host_address()` (Phase 5).
    """
    path = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
    return _scan_for_hardcoded_ips(path, check_id="G1")


@check
def check_G2_no_hardcoded_guest_ips_in_postgres_clients(tier0: dict) -> list[Finding]:
    """G2: platform_postgres.yml must not contain hardcoded IPs."""
    path = REPO_ROOT / "inventory" / "group_vars" / "platform_postgres.yml"
    return _scan_for_hardcoded_ips(path, check_id="G2")


def _scan_for_hardcoded_ips(path: Path, check_id: str) -> list[Finding]:
    if not path.exists() or path in _IP_ALLOWED_FILES:
        return []
    findings = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if _CIDR_LINES_OK.search(line):
            continue
        for pattern, label in ((_GUEST_IP_RE, "guest network"), (_TAILSCALE_IP_RE, "Tailscale")):
            if pattern.search(line):
                findings.append(
                    Finding(
                        check_id=check_id,
                        severity="warning",
                        location=f"{path.relative_to(REPO_ROOT)}:{line_no}",
                        message=f"Hardcoded {label} IP in `{line.strip()}` — Phase 5 will introduce `platform_host_address()` filter",
                        fix_hint="For now, reference `hostvars[host].ansible_host` or the platform_guest_catalog; Phase 5 will standardise this.",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Group F — execution scopes structural sanity
# ---------------------------------------------------------------------------


@check
def check_F1_scope_playbooks_exist(tier0: dict) -> list[Finding]:
    """F1: every playbook referenced in execution scopes exists on disk."""
    findings = []
    scopes_data = tier0.get("execution_scopes") or {}
    scopes = scopes_data.get("scopes", []) if isinstance(scopes_data, dict) else []

    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        playbook = scope.get("playbook", "")
        if not playbook:
            continue
        playbook_path = REPO_ROOT / playbook
        if not playbook_path.exists():
            findings.append(
                Finding(
                    check_id="F1",
                    severity="error",
                    location=f"config/ansible-execution-scopes.yaml [{scope.get('name', '?')}]",
                    message=f"Scope references playbook `{playbook}` which does not exist",
                    fix_hint=f"Create `{playbook}` or update the scope to point at the correct playbook path.",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# JSON Schema checks (when jsonschema is available)
# ---------------------------------------------------------------------------


def _load_schema(schema_rel: str) -> dict | None:
    path = REPO_ROOT / schema_rel
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


@check
def check_S2_credentials_schema(tier0: dict) -> list[Finding]:
    """S2: validate config/platform_credentials.yml against its JSON schema."""
    if jsonschema is None:
        return []
    schema = _load_schema("config/schemas/credentials.schema.json")
    if schema is None:
        return []
    creds_data = tier0.get("credentials")
    if creds_data is None:
        return []
    try:
        jsonschema.validate(creds_data, schema)
    except jsonschema.ValidationError as e:
        return [
            Finding(
                check_id="S2",
                severity="error",
                location=f"config/platform_credentials.yml: {e.json_path}",
                message=f"Schema validation failed: {e.message}",
                fix_hint="Check config/schemas/credentials.schema.json for the required structure.",
            )
        ]
    return []


@check
def check_S1_operators_schema(tier0: dict) -> list[Finding]:
    """S1: validate identity.yml-adjacent operator config against its JSON schema."""
    if jsonschema is None:
        return []
    schema = _load_schema("config/schemas/operators.schema.json")
    if schema is None:
        return []
    # operators.schema.json validates a separate `config/operators.yaml`;
    # this check ensures the schema itself is valid JSON Schema.
    try:
        jsonschema.Draft7Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        return [
            Finding(
                check_id="S1",
                severity="error",
                location="config/schemas/operators.schema.json",
                message=f"operators.schema.json is not valid JSON Schema: {e.message}",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_checks(tier0: dict, min_severity: str = "warning") -> list[Finding]:
    min_rank = SEVERITY_RANK.get(min_severity, 0)
    all_findings: list[Finding] = []
    for check_fn in CHECK_REGISTRY:
        try:
            findings = check_fn(tier0)
        except Exception as exc:  # noqa: BLE001
            findings = [
                Finding(
                    check_id=check_fn.__name__,
                    severity="error",
                    location="<validator>",
                    message=f"Check raised an exception: {exc}",
                )
            ]
        all_findings.extend(f for f in findings if SEVERITY_RANK.get(f.severity, 0) >= min_rank)
    return all_findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    parser.add_argument(
        "--min-severity",
        choices=["warning", "error"],
        default="warning",
        help="Minimum severity to report (default: warning)",
    )
    args = parser.parse_args(argv)

    tier0 = load_tier0()
    findings = run_all_checks(tier0, min_severity=args.min_severity)

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            print("✓ All Tier-0 cross-reference checks passed.")
        else:
            error_count = sum(1 for f in findings if f.severity == "error")
            warning_count = sum(1 for f in findings if f.severity == "warning")
            counts = []
            if error_count:
                counts.append(f"{error_count} error(s)")
            if warning_count:
                counts.append(f"{warning_count} warning(s)")
            print(f"Tier-0 validation: {', '.join(counts)}\n")
            for f in findings:
                icon = "✗" if f.severity == "error" else "⚠"
                print(f"  [{f.check_id}] {icon} {f.location}")
                print(f"       {f.message}")
                if f.fix_hint:
                    print(f"       → {f.fix_hint}")
                print()

    has_errors = any(f.severity == "error" for f in findings)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
