#!/usr/bin/env python3
"""
neko_tool.py — Manage Neko multi-instance browser sessions.

Manages the ``neko_instances`` block in ``inventory/group_vars/platform.yml``.

Commands
--------
  list                     Show all configured instances in a table
  add <name>               Add a new instance (auto-assigns port and UDP range)
  remove <name>            Remove an instance
  check [name]             HTTP health-check instances (probe signalling port)
  validate                 Validate: unique ports, no UDP overlap, valid emails
  next-port                Print next available TCP port (machine-readable)
  next-udp-range           Print next available UDP range (machine-readable)
  sync-from-keycloak       Sync neko_instances from live Keycloak users

sync-from-keycloak
------------------
Queries Keycloak for all users (or users in a specific group), then:
  - Adds entries for users not yet in neko_instances (auto-assigns port/UDP range)
  - Removes entries for users whose email no longer exists in Keycloak

This is idempotent — re-running preserves existing port/UDP assignments.
Reads the admin client secret from .local/keycloak/admin-client-secret.txt
(same secret file used by the neko.yml Ansible playbook).

Example:
  python3 scripts/neko_tool.py sync-from-keycloak \\
      --keycloak-url http://10.10.10.20:8091 \\
      --group /lv3-platform-admins

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
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

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

NEKO_MARKER = "\n# ---------------------------------------------------------------------------\n# Neko multi-instance browser sessions"

DEFAULT_HOST = "10.10.10.21"
HTTP_TIMEOUT = 5  # seconds

# ---------------------------------------------------------------------------
# Repo / file discovery
# ---------------------------------------------------------------------------


def find_platform_yml(override: str | None = None) -> Path:
    """Return the absolute path to inventory/group_vars/platform.yml.

    Walks up from the script's own directory to find the repo root (identified
    by the presence of ``inventory/group_vars/platform.yml``).  An explicit
    ``--platform-yml`` override skips discovery entirely.
    """
    if override:
        p = Path(override).expanduser().resolve()
        if not p.exists():
            print(f"ERROR: --platform-yml path does not exist: {p}", file=sys.stderr)
            sys.exit(1)
        return p

    start = Path(__file__).resolve().parent
    candidate = start
    for _ in range(10):  # don't walk past filesystem root forever
        target = candidate / "inventory" / "group_vars" / "platform.yml"
        if target.exists():
            return target
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent

    print(
        "ERROR: Could not find inventory/group_vars/platform.yml. "
        "Use --platform-yml to specify the path.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# YAML read / write helpers
# ---------------------------------------------------------------------------


def load_instances(platform_yml: Path) -> dict[str, dict[str, Any]]:
    """Load and return the neko_instances mapping from platform.yml.

    Returns an empty dict if the key is absent or null.
    """
    with platform_yml.open() as fh:
        data = yaml.safe_load(fh)
    instances = data.get("neko_instances") or {}
    return instances


def _build_neko_block(instances: dict[str, dict[str, Any]]) -> str:
    """Render the neko_instances YAML block (comment header + data)."""
    lines = [
        "",
        "# ---------------------------------------------------------------------------",
        "# Neko multi-instance browser sessions",
        "# ---------------------------------------------------------------------------",
        "# Each entry provisions an isolated browser container on runtime-comms-lv3",
        "# and a Keycloak user in the lv3 realm. Removing an entry destroys the",
        "# container and the Keycloak user on the next converge.",
        "#",
        "# Key         = instance name (container name: neko-<key>, data dir: /opt/neko/instances/<key>)",
        "# email       = Keycloak user email and routing key for NGINX → container mapping",
        "# port        = TCP port the Neko signalling server binds on (must be unique per instance)",
        "# udp_range   = Ephemeral UDP port range for WebRTC media (must be unique per instance)",
        "#",
        "# Example:",
        "#   neko_instances:",
        "#     florin:",
        "#       email: florin@lv3.org",
        "#       port: 8080",
        '#       udp_range: "50000-50999"',
        "#     alice:",
        "#       email: alice@lv3.org",
        "#       port: 8081",
        '#       udp_range: "51000-51999"',
    ]

    if not instances:
        lines.append("neko_instances: {}")
    else:
        lines.append("neko_instances:")
        for name, cfg in sorted(instances.items()):
            lines.append(f"  {name}:")
            lines.append(f"    email: {cfg['email']}")
            lines.append(f"    port: {cfg['port']}")
            lines.append(f'    udp_range: "{cfg["udp_range"]}"')

    lines.append("")  # trailing newline
    return "\n".join(lines)


def save_instances(platform_yml: Path, instances: dict[str, dict[str, Any]]) -> None:
    """Write neko_instances back to platform.yml.

    Strategy:
      1. Read the entire file as text.
      2. Find the last occurrence of the Neko marker comment.
      3. Keep everything before that marker.
      4. Append the freshly rendered neko_instances block.
    """
    raw = platform_yml.read_text()

    idx = raw.rfind(NEKO_MARKER)
    if idx == -1:
        # Marker not found: append to end of file
        prefix = raw.rstrip("\n")
    else:
        prefix = raw[:idx]

    new_block = _build_neko_block(instances)
    new_content = prefix + new_block

    platform_yml.write_text(new_content)


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


def next_available_udp_range(
    instances: dict[str, dict[str, Any]], override: str | None = None
) -> str:
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


def cmd_add(args: argparse.Namespace, instances: dict[str, dict[str, Any]], platform_yml: Path) -> int:
    name = args.name

    if not validate_name(name):
        print(
            f"ERROR: Instance name {name!r} is invalid. "
            "Use only letters, digits, hyphens, and underscores.",
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
                f"ERROR: UDP range {udp_range} overlaps with instance {iname!r} "
                f"({icfg['udp_range']}).",
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
    save_instances(platform_yml, instances)

    if not args.json:
        print(f"Instance {name!r} added successfully.")
    else:
        print(json.dumps({"status": "added", "instance": name, "config": new_cfg}))

    return 0


def cmd_remove(
    args: argparse.Namespace, instances: dict[str, dict[str, Any]], platform_yml: Path
) -> int:
    name = args.name

    if name not in instances:
        print(f"ERROR: Instance {name!r} not found.", file=sys.stderr)
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
    save_instances(platform_yml, instances)

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
        if not validate_email(cfg.get("email", "")):
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
                    f"UDP range overlap between {a_name!r} ({a_start}-{a_end}) "
                    f"and {b_name!r} ({b_start}-{b_end})"
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
# Keycloak API helpers
# ---------------------------------------------------------------------------


def _kc_request(url: str, token: str | None = None, data: bytes | None = None) -> Any:
    """Make a GET (or POST if data is given) request; return parsed JSON."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def _kc_get_token(kc_url: str, realm: str, client_id: str, client_secret: str) -> str:
    """Obtain an admin access token using client_credentials grant."""
    url = f"{kc_url}/realms/{realm}/protocol/openid-connect/token"
    payload = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    return _kc_request(url, data=payload)["access_token"]


def _kc_list_users_in_realm(kc_url: str, realm: str, token: str) -> list[dict[str, Any]]:
    """Return all enabled users in the realm (max 1000)."""
    url = f"{kc_url}/admin/realms/{realm}/users?max=1000&enabled=true"
    return _kc_request(url, token=token)


def _kc_list_users_in_group(kc_url: str, realm: str, token: str, group_path: str) -> list[dict[str, Any]]:
    """Return all enabled users in a Keycloak group (looked up by path)."""
    # First resolve path → group ID
    # Strip leading slash for the search term — Keycloak search matches by name,
    # not full path, so "%2F..." returns 0 results; we do exact path match below.
    search_term = group_path.lstrip("/")
    search_url = f"{kc_url}/admin/realms/{realm}/groups?search={urllib.parse.quote(search_term)}&max=100"
    groups = _kc_request(search_url, token=token)

    # Find exact path match (search is fuzzy)
    group_id = None
    for g in _flatten_groups(groups):
        if g.get("path") == group_path:
            group_id = g["id"]
            break

    if group_id is None:
        raise RuntimeError(
            f"Keycloak group {group_path!r} not found. "
            f"Groups returned: {[g.get('path') for g in _flatten_groups(groups)]}"
        )

    members_url = f"{kc_url}/admin/realms/{realm}/groups/{group_id}/members?max=1000"
    return _kc_request(members_url, token=token)


def _flatten_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recursively flatten group tree into a flat list."""
    result = []
    for g in groups:
        result.append(g)
        result.extend(_flatten_groups(g.get("subGroups", [])))
    return result


def _email_to_instance_name(email: str) -> str:
    """Derive a valid instance name from an email address."""
    local = email.split("@")[0]
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", local).lower()
    # Ensure it starts with a letter or digit
    name = re.sub(r"^[^a-zA-Z0-9]+", "", name)
    return name or "user"


def cmd_sync_from_keycloak(
    args: argparse.Namespace,
    instances: dict[str, dict[str, Any]],
    platform_yml: Path,
) -> int:
    """Sync neko_instances from live Keycloak users."""
    # --- Load admin client secret ---
    if args.secret_file:
        secret_path = Path(args.secret_file).expanduser().resolve()
    else:
        # Default: .local/keycloak/admin-client-secret.txt relative to repo root
        repo_root = platform_yml.parent.parent.parent
        secret_path = repo_root / ".local" / "keycloak" / "admin-client-secret.txt"

    if not secret_path.exists():
        print(
            f"ERROR: Admin client secret not found at {secret_path}\n"
            "Use --secret-file to specify an alternate path.",
            file=sys.stderr,
        )
        return 1

    client_secret = secret_path.read_text().strip()
    if not client_secret:
        print(f"ERROR: Secret file is empty: {secret_path}", file=sys.stderr)
        return 1

    kc_url = args.keycloak_url.rstrip("/")
    realm = args.realm
    client_id = args.client_id

    # --- Authenticate ---
    if not args.json:
        print(f"Authenticating with Keycloak at {kc_url} (realm=master, client={client_id})...")
    try:
        token = _kc_get_token(kc_url, "master", client_id, client_secret)
    except Exception as exc:
        print(f"ERROR: Could not obtain Keycloak admin token: {exc}", file=sys.stderr)
        return 1

    # --- Fetch users ---
    try:
        if args.group:
            if not args.json:
                print(f"Fetching users in group {args.group!r} from realm {realm!r}...")
            kc_users = _kc_list_users_in_group(kc_url, realm, token, args.group)
        else:
            if not args.json:
                print(f"Fetching all users from realm {realm!r}...")
            kc_users = _kc_list_users_in_realm(kc_url, realm, token)
    except Exception as exc:
        print(f"ERROR: Could not fetch users from Keycloak: {exc}", file=sys.stderr)
        return 1

    # Build email → Keycloak user mapping (only enabled users with a valid email)
    kc_by_email: dict[str, dict[str, Any]] = {}
    for u in kc_users:
        if not u.get("enabled", True):
            continue
        email = (u.get("email") or "").strip().lower()
        if email and validate_email(email):
            kc_by_email[email] = u

    if not args.json:
        print(f"Found {len(kc_by_email)} Keycloak user(s) with valid emails.")

    # Build current email → instance name mapping
    current_by_email: dict[str, str] = {
        cfg["email"].lower(): name for name, cfg in instances.items()
    }

    # --- Determine changes ---
    to_add: list[str] = []  # emails to add
    to_remove: list[str] = []  # instance names to remove

    for email in kc_by_email:
        if email not in current_by_email:
            to_add.append(email)

    for inst_email, inst_name in current_by_email.items():
        if inst_email not in kc_by_email:
            to_remove.append(inst_name)

    if not to_add and not to_remove:
        if args.json:
            print(json.dumps({"status": "no_changes", "instances": instances}))
        else:
            print("neko_instances is already in sync with Keycloak. Nothing to do.")
        return 0

    if not args.json:
        if to_add:
            print(f"  + Adding {len(to_add)} user(s): {', '.join(to_add)}")
        if to_remove:
            print(f"  - Removing {len(to_remove)} instance(s): {', '.join(to_remove)}")

    if args.dry_run:
        if args.json:
            print(json.dumps({"status": "dry_run", "add": to_add, "remove": to_remove}))
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
            print(f"  Added {name!r} ({email}) → port={port}, udp={udp_range}")

    # --- Apply removals ---
    for inst_name in to_remove:
        del instances[inst_name]
        if not args.json:
            print(f"  Removed {inst_name!r} (no longer in Keycloak)")

    save_instances(platform_yml, instances)

    if args.json:
        print(
            json.dumps(
                {
                    "status": "synced",
                    "added": to_add,
                    "removed": to_remove,
                    "instances": instances,
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
        description="Manage Neko multi-instance browser sessions in platform.yml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--platform-yml",
        metavar="PATH",
        default=None,
        help="Override path to inventory/group_vars/platform.yml",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit machine-readable JSON output",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompts (for automation)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # list
    sub.add_parser("list", help="Show all configured instances")

    # add
    p_add = sub.add_parser("add", help="Add a new instance")
    p_add.add_argument("name", help="Instance name (alphanumeric, hyphens, underscores)")
    p_add.add_argument("--email", required=True, help="Keycloak user email")
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

    # sync-from-keycloak
    p_sync = sub.add_parser(
        "sync-from-keycloak",
        help="Sync neko_instances from live Keycloak users (add new, remove deleted)",
    )
    p_sync.add_argument(
        "--keycloak-url",
        default="http://10.10.10.20:8091",
        help="Keycloak base URL (default: http://10.10.10.20:8091)",
    )
    p_sync.add_argument(
        "--realm",
        default="lv3",
        help="Keycloak realm to query (default: lv3)",
    )
    p_sync.add_argument(
        "--client-id",
        default="lv3-admin-runtime",
        help="Admin client ID for client_credentials grant (default: lv3-admin-runtime)",
    )
    p_sync.add_argument(
        "--secret-file",
        default=None,
        metavar="PATH",
        help="Path to admin client secret file "
        "(default: .local/keycloak/admin-client-secret.txt)",
    )
    p_sync.add_argument(
        "--group",
        default="/lv3-platform-admins",
        metavar="GROUP_PATH",
        help="Only sync users in this Keycloak group path "
        "(default: /lv3-platform-admins; use '' for all users)",
    )
    p_sync.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would change without writing to platform.yml",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    platform_yml = find_platform_yml(args.platform_yml)
    instances = load_instances(platform_yml)

    if args.command == "list":
        return cmd_list(args, instances)
    elif args.command == "add":
        return cmd_add(args, instances, platform_yml)
    elif args.command == "remove":
        return cmd_remove(args, instances, platform_yml)
    elif args.command == "check":
        return cmd_check(args, instances)
    elif args.command == "validate":
        return cmd_validate(args, instances)
    elif args.command == "next-port":
        return cmd_next_port(args, instances)
    elif args.command == "next-udp-range":
        return cmd_next_udp_range(args, instances)
    elif args.command == "sync-from-keycloak":
        return cmd_sync_from_keycloak(args, instances, platform_yml)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
