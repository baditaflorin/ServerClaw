#!/usr/bin/env python3
"""
neko_tool.py — Manage Neko multi-instance browser sessions.

Reads generic ``neko_instances`` defaults from inventory and stores deployment
specific user assignments only in the selected private ``.local`` overlay.

Commands
--------
  list                     Show all configured instances in a table
  add <name>               Add a new instance (auto-assigns port and UDP range)
  remove <name>            Remove an instance
  check [name]             HTTP health-check instances (probe signalling port)
  validate                 Validate: unique ports, no UDP overlap, valid emails
  next-port                Print next available TCP port (machine-readable)
  next-udp-range           Print next available UDP range (machine-readable)
  sync-from-authentik      Sync neko_instances from live Authentik users

sync-from-authentik
------------------
Queries Authentik for all active users (or users in a specific group), then:
  - Adds entries for users not yet in neko_instances (auto-assigns port/UDP range)
  - Removes entries for users whose email no longer exists in Authentik

This is idempotent — re-running preserves existing port/UDP assignments.
Reads the Authentik API token from .local/authentik/bootstrap-token.txt
(the same local-only token source used by the neko.yml playbook).

Example:
  uvx --from pyyaml python scripts/neko_tool.py sync-from-authentik \\
      --authentik-url https://id.example.com \\
      --group platform-admins

Exit codes
----------
  0 = success
  1 = error / unhealthy / validation failure
  2 = usage error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.repo import local_overlay_root

try:
    import yaml
except ImportError:
    print(
        "ERROR: pyyaml is not installed. Install with: pip3 install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_TCP_PORT: int = 8080
UDP_BASE: int = 50000
UDP_BLOCK_SIZE: int = 1000  # ports per instance (1000 allows ~15 instances below 65535)

DEFAULT_HOST = "10.10.10.21"
HTTP_TIMEOUT = 5  # seconds
DEFAULT_INSTANCES_FILE = REPO_ROOT / "inventory" / "group_vars" / "all" / "neko.yml"

# ---------------------------------------------------------------------------
# Repo / file discovery
# ---------------------------------------------------------------------------


def selected_identity_path() -> Path | None:
    """Resolve the selected private identity overlay without mixing deployments."""
    local_root = local_overlay_root(REPO_ROOT)
    selected = os.environ.get("PLATFORM_IDENTITY_OVERLAY", "").strip()
    if selected:
        path = Path(selected).expanduser()
        if not path.is_absolute():
            path = local_root / path.as_posix().removeprefix(".local/")
        path = path.resolve()
        if not path.is_file():
            raise ValueError(f"PLATFORM_IDENTITY_OVERLAY is not a file: {path}")
        return path
    legacy = local_root / "identity.yml"
    return legacy if legacy.is_file() else None


def find_instances_file(override: str | None = None, *, for_write: bool = False) -> Path:
    """Find the selected deployment's Neko overlay, never a generated tracked file."""
    local_root = local_overlay_root(REPO_ROOT).resolve()
    env_selected = os.environ.get("PLATFORM_NEKO_OVERLAY", "").strip()
    selected = override or env_selected
    explicit = bool(selected)
    if selected:
        path = Path(selected).expanduser()
        if not path.is_absolute():
            if path.as_posix().startswith(".local/"):
                path = local_root / path.as_posix().removeprefix(".local/")
            elif override is not None:
                path = REPO_ROOT / path
            else:
                path = local_root / path
        path = path.resolve()
    else:
        identity = selected_identity_path()
        path = identity.parent / "neko.yml" if identity else DEFAULT_INSTANCES_FILE

    if for_write and not path.is_relative_to(local_root):
        raise ValueError(
            "Refusing to write Neko user assignments outside the private .local overlay; "
            "select PLATFORM_IDENTITY_OVERLAY or pass --instances-file under .local/."
        )
    if not path.exists() and explicit and not for_write:
        raise ValueError(f"explicit Neko instances file is not a file: {path}")
    if not path.exists() and not for_write:
        return DEFAULT_INSTANCES_FILE
    if path.exists() and not path.is_file():
        raise ValueError(f"Neko instances path is not a regular file: {path}")
    return path


# ---------------------------------------------------------------------------
# YAML read / write helpers
# ---------------------------------------------------------------------------


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Neko configuration must be a YAML mapping: {path}")
    return data


def _operator_email_from_identity() -> str | None:
    identity_path = selected_identity_path()
    if identity_path is None:
        return None
    configured_email = _read_yaml_mapping(identity_path).get("platform_operator_email")
    return configured_email.strip() if isinstance(configured_email, str) and configured_email.strip() else None


def _resolve_operator_email(instances: dict[str, dict[str, Any]]) -> None:
    configured_email = _operator_email_from_identity()
    if configured_email is None:
        return
    for config in instances.values():
        value = config.get("email")
        if isinstance(value, str) and re.fullmatch(r"\{\{\s*platform_operator_email\s*\}\}", value):
            config["email"] = configured_email


def _overlay_allows_empty(instances_file: Path) -> bool:
    """Read the selected overlay's explicit full-teardown opt-in."""
    configured = _read_yaml_mapping(instances_file).get("neko_allow_empty_instances", False)
    if not isinstance(configured, bool):
        raise ValueError("neko_allow_empty_instances must be a YAML boolean")
    return configured


def _default_authentik_admin_group() -> str:
    prefix = os.environ.get("PLATFORM_CONFIG_PREFIX", "").strip()
    if not prefix:
        identity_path = selected_identity_path()
        if identity_path is not None:
            identity = _read_yaml_mapping(identity_path)
            configured = identity.get("platform_config_prefix")
            if isinstance(configured, str) and configured.strip() and "{{" not in configured:
                prefix = configured.strip()
            if not prefix:
                domain = identity.get("platform_domain")
                if isinstance(domain, str) and domain.strip():
                    prefix = domain.strip().split(".", 1)[0]
    return f"{prefix}-platform-admins" if prefix else "platform-admins"


def _default_authentik_url() -> str:
    """Resolve Authentik's issuer host from the explicitly selected deployment."""
    configured = os.environ.get("LV3_AUTHENTIK_URL", "").strip()
    if configured:
        return configured.rstrip("/")

    identity_path = selected_identity_path()
    if identity_path is not None:
        domain = _read_yaml_mapping(identity_path).get("platform_domain")
        if isinstance(domain, str) and domain.strip() and "{{" not in domain:
            return f"https://id.{domain.strip().strip('/')}"

    return "https://id.example.com"


def load_instances(instances_file: Path) -> dict[str, dict[str, Any]]:
    """Load a selected full-map override, otherwise use generic tracked defaults."""
    base = _read_yaml_mapping(DEFAULT_INSTANCES_FILE).get("neko_instances", {})
    overlay_data = _read_yaml_mapping(instances_file)
    unexpected = set(overlay_data) - {"neko_instances", "neko_allow_empty_instances"}
    if unexpected:
        raise ValueError("Neko overlay contains unsupported top-level keys: " + ", ".join(sorted(unexpected)))
    allow_empty = overlay_data.get("neko_allow_empty_instances", False)
    if not isinstance(allow_empty, bool):
        raise ValueError("neko_allow_empty_instances must be a YAML boolean")
    instances = overlay_data.get("neko_instances", base)
    if not isinstance(instances, dict):
        raise ValueError("neko_instances must be a mapping")
    _resolve_operator_email(instances)
    return instances


def save_instances(instances_file: Path, instances: dict[str, dict[str, Any]], *, allow_empty: bool = False) -> None:
    """Atomically write user assignments to a private deployment overlay."""
    if not instances and not allow_empty:
        raise ValueError("Refusing to write an empty Neko mapping without explicit --allow-empty")
    instances_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stored_instances = {name: dict(config) for name, config in instances.items()}
    base_operator = (_read_yaml_mapping(DEFAULT_INSTANCES_FILE).get("neko_instances") or {}).get("operator", {})
    operator_template = base_operator.get("email") if isinstance(base_operator, dict) else None
    operator_email = _operator_email_from_identity()
    if (
        operator_template == "{{ platform_operator_email }}"
        and operator_email
        and isinstance(stored_instances.get("operator"), dict)
        and stored_instances["operator"].get("email") == operator_email
    ):
        stored_instances["operator"]["email"] = operator_template

    payload = {
        "neko_instances": stored_instances,
        "neko_allow_empty_instances": bool(not instances and allow_empty),
    }
    rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=instances_file.parent, prefix=".neko-", delete=False
        ) as fh:
            temp_path = Path(fh.name)
            fh.write(rendered)
            fh.flush()
            os.fsync(fh.fileno())
        temp_path.chmod(0o600)
        os.replace(temp_path, instances_file)
        instances_file.chmod(0o600)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


# ---------------------------------------------------------------------------
# Port allocation
# ---------------------------------------------------------------------------


def _used_tcp_ports(instances: dict[str, dict[str, Any]]) -> set[int]:
    return {int(cfg["port"]) for cfg in instances.values()}


def _used_udp_ranges(instances: dict[str, dict[str, Any]]) -> list[tuple[int, int]]:
    """Return sorted list of (start, end) UDP ranges in use."""
    ranges = []
    for cfg in instances.values():
        start, end = _parse_udp_range(cfg["udp_range"])
        ranges.append((start, end))
    return sorted(ranges)


def _parse_udp_range(udp_range: str) -> tuple[int, int]:
    """Parse 'start-end' string into (start, end) integers."""
    parts = udp_range.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid UDP range: {udp_range!r}")
    return int(parts[0]), int(parts[1])


def next_available_port(instances: dict[str, dict[str, Any]], override: int | None = None) -> int:
    """Return the next available TCP port, optionally honouring an override."""
    if override is not None:
        return override
    used = _used_tcp_ports(instances)
    port = BASE_TCP_PORT
    while port in used:
        port += 1
    return port


def next_available_udp_range(instances: dict[str, dict[str, Any]], override: str | None = None) -> str:
    """Return the next available UDP range string, optionally honouring an override."""
    if override is not None:
        # Validate format
        _parse_udp_range(override)
        return override

    used = _used_udp_ranges(instances)
    # Try each block starting from UDP_BASE
    block = 0
    while True:
        start = UDP_BASE + block * UDP_BLOCK_SIZE
        end = start + UDP_BLOCK_SIZE - 1
        if end > 65535:
            raise RuntimeError(
                f"No available UDP range: would exceed max port 65535 "
                f"(tried start={start}). Reduce UDP_BLOCK_SIZE or free up ranges."
            )
        # Check for overlap with any used range
        overlap = False
        for u_start, u_end in used:
            if start <= u_end and end >= u_start:
                overlap = True
                break
        if not overlap:
            return f"{start}-{end}"
        block += 1


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def validate_name(name: str) -> bool:
    return bool(_NAME_RE.match(name))


def _ranges_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and a_end >= b_start


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _sep_line(col_widths: list[int]) -> str:
    return "  ".join("\u2500" * w for w in col_widths)


def print_table(instances: dict[str, dict[str, Any]]) -> None:
    """Print instances as a formatted ASCII table."""
    headers = ["NAME", "EMAIL", "PORT", "UDP RANGE"]
    rows = []
    for name in sorted(instances):
        cfg = instances[name]
        rows.append([name, cfg["email"], str(cfg["port"]), cfg["udp_range"]])

    # Column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print(_sep_line(col_widths))
    for row in rows:
        print(fmt.format(*row))


# ---------------------------------------------------------------------------
# HTTP health check
# ---------------------------------------------------------------------------


def http_check(host: str, port: int) -> tuple[int | str, bool]:
    """Probe http://<host>:<port>/ with a 5-second timeout.

    Returns (status, healthy) where status is the HTTP status code (int),
    or one of the strings "timeout" / "error".
    """
    url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            status = resp.status
            healthy = 200 <= status < 400
            return status, healthy
    except urllib.error.HTTPError as exc:
        return exc.code, False
    except TimeoutError:
        return "timeout", False
    except Exception:
        return "error", False


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace, instances: dict[str, dict[str, Any]]) -> int:
    if args.json:
        print(json.dumps(instances, indent=2))
        return 0

    if not instances:
        print("No Neko instances configured.")
        return 0

    print_table(instances)
    return 0


def cmd_add(args: argparse.Namespace, instances: dict[str, dict[str, Any]], instances_file: Path) -> int:
    name = args.name

    if not validate_name(name):
        print(
            f"ERROR: Instance name {name!r} is invalid. Use only letters, digits, hyphens, and underscores.",
            file=sys.stderr,
        )
        return 2

    email = args.email
    if not email:
        print("ERROR: --email is required for the add command.", file=sys.stderr)
        return 2

    if not validate_email(email):
        print(f"ERROR: Email {email!r} does not appear valid.", file=sys.stderr)
        return 2

    # Idempotency: if name exists with same email, report and exit cleanly
    if name in instances:
        existing = instances[name]
        if existing["email"] == email:
            print(f"Instance {name!r} already exists with the same email. Nothing to do.")
            if args.json:
                print(json.dumps({"status": "already_exists", "instance": name, "config": existing}))
            return 0
        else:
            print(
                f"ERROR: Instance {name!r} already exists with a different email "
                f"({existing['email']!r}). Remove it first.",
                file=sys.stderr,
            )
            return 1

    port = next_available_port(instances, override=args.port)
    udp_range = next_available_udp_range(instances, override=args.udp_range)

    # Check for port conflicts with existing instances
    used_ports = _used_tcp_ports(instances)
    if port in used_ports:
        print(f"ERROR: Port {port} is already in use by another instance.", file=sys.stderr)
        return 1

    # Check for UDP range conflicts
    new_udp_start, new_udp_end = _parse_udp_range(udp_range)
    for iname, icfg in instances.items():
        ex_start, ex_end = _parse_udp_range(icfg["udp_range"])
        if _ranges_overlap(new_udp_start, new_udp_end, ex_start, ex_end):
            print(
                f"ERROR: UDP range {udp_range} overlaps with instance {iname!r} ({icfg['udp_range']}).",
                file=sys.stderr,
            )
            return 1

    new_cfg: dict[str, Any] = {"email": email, "port": port, "udp_range": udp_range}

    if args.json:
        print(json.dumps({"status": "adding", "instance": name, "config": new_cfg}))

    if not args.json:
        print(f"Adding instance {name!r}:")
        print(f"  email:     {email}")
        print(f"  port:      {port}")
        print(f"  udp_range: {udp_range}")

    instances[name] = new_cfg
    save_instances(instances_file, instances)

    if not args.json:
        print(f"Instance {name!r} added successfully.")
    else:
        print(json.dumps({"status": "added", "instance": name, "config": new_cfg}))

    return 0


def cmd_remove(args: argparse.Namespace, instances: dict[str, dict[str, Any]], instances_file: Path) -> int:
    name = args.name

    if name not in instances:
        print(f"ERROR: Instance {name!r} not found.", file=sys.stderr)
        return 1

    if len(instances) == 1 and not args.allow_empty:
        print(
            "ERROR: Removing the last Neko instance is destructive. Repeat with --allow-empty "
            "only when intentionally tearing down all Neko sessions.",
            file=sys.stderr,
        )
        return 1

    cfg = instances[name]

    if not args.yes:
        print(f"Would remove instance {name!r}:")
        print(f"  email:     {cfg['email']}")
        print(f"  port:      {cfg['port']}")
        print(f"  udp_range: {cfg['udp_range']}")
        try:
            answer = input("Remove? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 1
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1

    del instances[name]
    save_instances(instances_file, instances, allow_empty=args.allow_empty)

    if args.json:
        print(json.dumps({"status": "removed", "instance": name}))
    else:
        print(f"Instance {name!r} removed.")

    return 0


def cmd_check(args: argparse.Namespace, instances: dict[str, dict[str, Any]]) -> int:
    """HTTP health-check one or all instances."""
    host = args.host

    if args.name:
        names_to_check = [args.name]
        for n in names_to_check:
            if n not in instances:
                print(f"ERROR: Instance {n!r} not found.", file=sys.stderr)
                return 1
    else:
        names_to_check = sorted(instances.keys())

    if not names_to_check:
        print("No instances to check.")
        return 0

    results = []
    for name in names_to_check:
        cfg = instances[name]
        port = cfg["port"]
        status, healthy = http_check(host, port)
        results.append(
            {
                "name": name,
                "email": cfg["email"],
                "port": port,
                "http_status": status,
                "healthy": healthy,
            }
        )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        headers = ["NAME", "EMAIL", "PORT", "STATUS", "HEALTHY"]
        rows = [
            [
                r["name"],
                r["email"],
                str(r["port"]),
                str(r["http_status"]),
                "yes" if r["healthy"] else "no",
            ]
            for r in results
        ]
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(cell))
        fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
        print(fmt.format(*headers))
        print(_sep_line(col_widths))
        for row in rows:
            print(fmt.format(*row))

    any_unhealthy = any(not r["healthy"] for r in results)
    return 1 if any_unhealthy else 0


def cmd_validate(args: argparse.Namespace, instances: dict[str, dict[str, Any]]) -> int:
    """Validate all instances for uniqueness and correctness."""
    errors: list[str] = []

    # 1. Name format
    for name in instances:
        if not validate_name(name):
            errors.append(f"Instance name {name!r} contains invalid characters.")

    # 2. Email format
    for name, cfg in instances.items():
        email = cfg.get("email", "")
        is_operator_template = isinstance(email, str) and re.fullmatch(r"\{\{\s*platform_operator_email\s*\}\}", email)
        if not is_operator_template and not validate_email(email):
            errors.append(f"Instance {name!r} has invalid email: {cfg.get('email')!r}")

    # 3. Unique TCP ports
    port_map: dict[int, list[str]] = {}
    for name, cfg in instances.items():
        p = int(cfg["port"])
        port_map.setdefault(p, []).append(name)
    for port, names in port_map.items():
        if len(names) > 1:
            errors.append(f"TCP port {port} is shared by instances: {', '.join(names)}")

    # 4. No overlapping UDP ranges
    range_list: list[tuple[int, int, str]] = []
    for name, cfg in instances.items():
        try:
            start, end = _parse_udp_range(cfg.get("udp_range", ""))
            range_list.append((start, end, name))
        except (ValueError, AttributeError):
            errors.append(f"Instance {name!r} has an unparseable udp_range: {cfg.get('udp_range')!r}")

    for i in range(len(range_list)):
        for j in range(i + 1, len(range_list)):
            a_start, a_end, a_name = range_list[i]
            b_start, b_end, b_name = range_list[j]
            if _ranges_overlap(a_start, a_end, b_start, b_end):
                errors.append(
                    f"UDP range overlap between {a_name!r} ({a_start}-{a_end}) and {b_name!r} ({b_start}-{b_end})"
                )

    if args.json:
        print(json.dumps({"valid": len(errors) == 0, "errors": errors}, indent=2))
    else:
        if not errors:
            print(f"All {len(instances)} instance(s) are valid.")
        else:
            for err in errors:
                print(f"  FAIL  {err}")

    return 0 if not errors else 1


def cmd_next_port(args: argparse.Namespace, instances: dict[str, dict[str, Any]]) -> int:
    port = next_available_port(instances)
    if args.json:
        print(json.dumps({"next_port": port}))
    else:
        print(port)
    return 0


def cmd_next_udp_range(args: argparse.Namespace, instances: dict[str, dict[str, Any]]) -> int:
    udp_range = next_available_udp_range(instances)
    if args.json:
        print(json.dumps({"next_udp_range": udp_range}))
    else:
        print(udp_range)
    return 0


# ---------------------------------------------------------------------------
# Authentik API helpers
# ---------------------------------------------------------------------------


def _authentik_request(url: str, token: str) -> Any:
    """Make an authenticated Authentik API GET request and return parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc


def _authentik_list_results(url: str, token: str) -> list[dict[str, Any]]:
    """Return every result from an Authentik list endpoint without logging data."""
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        separator = "&" if "?" in url else "?"
        payload = _authentik_request(f"{url}{separator}page={page}&page_size=100", token)
        current = payload.get("results", [])
        if not isinstance(current, list):
            raise RuntimeError(f"Unexpected list response from {url}")
        results.extend(current)
        if len(current) < 100:
            return results
        page += 1
        if page > 100:
            raise RuntimeError(f"Refusing to paginate more than 100 pages from {url}")


def _authentik_list_users(authentik_url: str, token: str) -> list[dict[str, Any]]:
    """Return all Authentik users visible to the supplied API token."""
    return _authentik_list_results(f"{authentik_url}/api/v3/core/users/", token)


def _authentik_list_users_in_group(
    authentik_url: str,
    token: str,
    group_name: str,
) -> list[dict[str, Any]]:
    """Return Authentik users that belong to the named group."""
    groups = _authentik_list_results(f"{authentik_url}/api/v3/core/groups/", token)
    group = next((item for item in groups if item.get("name") == group_name), None)
    if group is None:
        raise RuntimeError(f"Authentik group {group_name!r} not found")

    member_pks = {int(pk) for pk in group.get("users", [])}
    users = _authentik_list_users(authentik_url, token)
    return [user for user in users if user.get("pk") in member_pks]


def _email_to_instance_name(email: str) -> str:
    """Derive a valid instance name from an email address."""
    local = email.split("@")[0]
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", local).lower()
    # Ensure it starts with a letter or digit
    name = re.sub(r"^[^a-zA-Z0-9]+", "", name)
    return name or "user"


def cmd_sync_from_authentik(
    args: argparse.Namespace,
    instances: dict[str, dict[str, Any]],
    instances_file: Path,
) -> int:
    """Sync neko_instances from live Authentik users."""
    if _operator_email_from_identity() is None:
        print(
            "ERROR: Select a deployment identity with PLATFORM_IDENTITY_OVERLAY before syncing Authentik users.",
            file=sys.stderr,
        )
        return 1

    # --- Load controller-local Authentik API token ---
    if args.token_file:
        token_path = Path(args.token_file).expanduser().resolve()
    else:
        token_path = local_overlay_root(REPO_ROOT) / "authentik" / "bootstrap-token.txt"

    if not token_path.exists():
        print(
            f"ERROR: Authentik API token not found at {token_path}\nUse --token-file to specify an alternate path.",
            file=sys.stderr,
        )
        return 1

    token = token_path.read_text().strip()
    if not token:
        print(f"ERROR: Token file is empty: {token_path}", file=sys.stderr)
        return 1

    authentik_url = args.authentik_url.rstrip("/")

    # --- Fetch users ---
    if not args.json:
        print(f"Querying Authentik at {authentik_url}...")
    try:
        if args.group:
            if not args.json:
                print(f"Fetching users in Authentik group {args.group!r}...")
            authentik_users = _authentik_list_users_in_group(authentik_url, token, args.group)
        else:
            if not args.json:
                print("Fetching all Authentik users...")
            authentik_users = _authentik_list_users(authentik_url, token)
    except Exception as exc:
        print(f"ERROR: Could not fetch users from Authentik: {exc}", file=sys.stderr)
        return 1

    # Build email → Authentik user mapping (only active users with a valid email)
    authentik_by_email: dict[str, dict[str, Any]] = {}
    for user in authentik_users:
        if not user.get("is_active", True):
            continue
        email = (user.get("email") or "").strip().lower()
        if email and validate_email(email):
            authentik_by_email[email] = user

    if not args.json:
        print(f"Found {len(authentik_by_email)} active Authentik user(s) with valid emails.")

    # Build current email → instance name mapping
    current_by_email: dict[str, str] = {cfg["email"].lower(): name for name, cfg in instances.items()}
    allow_empty = args.allow_empty or _overlay_allows_empty(instances_file)

    # --- Determine changes ---
    to_add: list[str] = []  # emails to add
    to_remove: list[str] = []  # instance names to remove

    for email in authentik_by_email:
        if email not in current_by_email:
            to_add.append(email)

    for inst_email, inst_name in current_by_email.items():
        if inst_email not in authentik_by_email:
            to_remove.append(inst_name)

    final_count = len(instances) + len(to_add) - len(to_remove)
    if final_count == 0 and not allow_empty:
        print(
            "ERROR: Authentik sync would remove every Neko instance. Repeat with --allow-empty "
            "only when intentionally tearing down all Neko sessions.",
            file=sys.stderr,
        )
        return 1

    if not to_add and not to_remove:
        if args.json:
            print(json.dumps({"status": "no_changes", "instance_count": len(instances)}))
        else:
            print("neko_instances is already in sync with Authentik. Nothing to do.")
        return 0

    if not args.json:
        if to_add:
            print(f"  + Adding {len(to_add)} Authentik group member(s)")
        if to_remove:
            print(f"  - Removing {len(to_remove)} stale instance(s)")

    if args.dry_run:
        if args.json:
            print(json.dumps({"status": "dry_run", "add_count": len(to_add), "remove_count": len(to_remove)}))
        else:
            print("Dry run — no changes written.")
        return 0

    # --- Apply additions ---
    for email in sorted(to_add):
        name = _email_to_instance_name(email)
        # Avoid name collisions
        base_name = name
        counter = 2
        while name in instances:
            name = f"{base_name}{counter}"
            counter += 1

        port = next_available_port(instances)
        udp_range = next_available_udp_range(instances)
        instances[name] = {"email": email, "port": port, "udp_range": udp_range}
        if not args.json:
            print(f"  Added instance {name!r} → port={port}, udp={udp_range}")

    # --- Apply removals ---
    for inst_name in to_remove:
        del instances[inst_name]
        if not args.json:
            print(f"  Removed stale instance {inst_name!r}")

    save_instances(instances_file, instances, allow_empty=allow_empty)

    if args.json:
        print(
            json.dumps(
                {
                    "status": "synced",
                    "added_count": len(to_add),
                    "removed_count": len(to_remove),
                    "instance_count": len(instances),
                }
            )
        )
    else:
        print(f"Sync complete. {len(instances)} instance(s) now configured.")

    return 0


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neko_tool.py",
        description="Manage Neko multi-instance browser sessions in deployment-local config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--instances-file",
        "--platform-yml",
        dest="instances_file",
        metavar="PATH",
        default=None,
        help="Override the Neko YAML path (writes are restricted to the private .local overlay)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit machine-readable JSON output",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompts (for automation)",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Explicitly permit removing every Neko instance (container/data teardown)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # list
    sub.add_parser("list", help="Show all configured instances")

    # add
    p_add = sub.add_parser("add", help="Add a new instance")
    p_add.add_argument("name", help="Instance name (alphanumeric, hyphens, underscores)")
    p_add.add_argument("--email", required=True, help="Authentik user email")
    p_add.add_argument("--port", type=int, default=None, help="Override TCP port (default: auto)")
    p_add.add_argument(
        "--udp-range",
        metavar="START-END",
        default=None,
        dest="udp_range",
        help="Override UDP range, e.g. 50000-52999 (default: auto)",
    )

    # remove
    p_remove = sub.add_parser("remove", help="Remove an instance")
    p_remove.add_argument("name", help="Instance name to remove")

    # check
    p_check = sub.add_parser("check", help="HTTP health-check instances")
    p_check.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Instance name to check (default: all)",
    )
    p_check.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host to probe (default: {DEFAULT_HOST})",
    )

    # validate
    sub.add_parser("validate", help="Validate all instances for correctness")

    # next-port
    sub.add_parser("next-port", help="Print next available TCP port")

    # next-udp-range
    sub.add_parser("next-udp-range", help="Print next available UDP range")

    # sync-from-authentik
    p_sync = sub.add_parser(
        "sync-from-authentik",
        help="Sync neko_instances from live Authentik users (add new, remove deleted)",
    )
    p_sync.add_argument(
        "--authentik-url",
        default=_default_authentik_url(),
        help=(
            "Authentik base URL (default: LV3_AUTHENTIK_URL, then the selected identity's "
            "platform_domain, then https://id.example.com)"
        ),
    )
    p_sync.add_argument(
        "--token-file",
        default=None,
        metavar="PATH",
        help="Path to Authentik API token file (default: .local/authentik/bootstrap-token.txt)",
    )
    p_sync.add_argument(
        "--group",
        default=_default_authentik_admin_group(),
        metavar="GROUP_NAME",
        help="Only sync users in this deployment's <prefix>-platform-admins Authentik group (use '' for all users)",
    )
    p_sync.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would change without writing to the local deployment overlay",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    is_write = args.command in {"add", "remove", "sync-from-authentik"}
    if args.command == "sync-from-authentik" and args.dry_run:
        is_write = False

    try:
        instances_file = find_instances_file(
            args.instances_file,
            for_write=is_write,
        )
        instances = load_instances(instances_file)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.command == "list":
        return cmd_list(args, instances)
    elif args.command == "add":
        return cmd_add(args, instances, instances_file)
    elif args.command == "remove":
        return cmd_remove(args, instances, instances_file)
    elif args.command == "check":
        return cmd_check(args, instances)
    elif args.command == "validate":
        return cmd_validate(args, instances)
    elif args.command == "next-port":
        return cmd_next_port(args, instances)
    elif args.command == "next-udp-range":
        return cmd_next_udp_range(args, instances)
    elif args.command == "sync-from-authentik":
        return cmd_sync_from_authentik(args, instances, instances_file)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
