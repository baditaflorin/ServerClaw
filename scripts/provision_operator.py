#!/usr/bin/env python3
"""
provision_operator.py — Canonical operator onboarding script for the platform.

Implements ADR 0318: repeatable, code-first operator provisioning with audit-trail CC.
Uses the Authentik admin API and adds Headscale VPN +
step-ca bootstrap details so the operator receives everything in a single email.

Usage:
    python3 scripts/provision_operator.py \
        --id matei-busui-tmp-001 \
        --name "Matei Busui" \
        --email operator@example.com \
        --username matei.busui-tmp \
        --role admin \
        --expires 2026-04-08T00:00:00Z \
        --requester operator@example.com \
        [--dry-run] [--skip-email]

What it does:
    1. Resolve controller-local inputs from the shared checkout even under `.worktrees/`
    2. Reuse or generate `.local/authentik/<username>-password.txt`
    3. Create or verify the Authentik user and group membership
    4. Optionally create or verify the Headscale user and pre-auth key
    5. Optionally send one onboarding email to the operator with CC to the requester

`--skip-email` keeps the Authentik provisioning and verification path live without
re-sending onboarding email or generating a fresh Headscale auth key. Use it when
re-verifying an already onboarded operator from exact `main`.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from operator_manager import ROLE_DEFINITIONS as OPERATOR_MANAGER_ROLE_DEFINITIONS


def detect_common_repo_root(repo_root: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return repo_root
    common_dir = Path(result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = (repo_root / common_dir).resolve()
    if common_dir.name == ".git":
        return common_dir.parent
    return repo_root


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]
COMMON_REPO_ROOT = detect_common_repo_root(REPO_ROOT)


def discover_local_root(repo_root: Path, common_repo_root: Path | None = None) -> Path:
    shared_repo_root = common_repo_root or detect_common_repo_root(repo_root)
    direct_root = repo_root / ".local"
    shared_root = shared_repo_root / ".local"
    # In a linked worktree, `.local/` is controller-shared state. Prefer the
    # common checkout copy even if a partial shadow directory exists locally.
    if shared_repo_root != repo_root and shared_root.exists():
        return shared_root
    if direct_root.exists():
        return direct_root
    if shared_root.exists():
        return shared_root
    if repo_root.parent.name == ".worktrees":
        sibling_root = repo_root.parent.parent / ".local"
        if sibling_root.exists():
            return sibling_root
    return direct_root


LOCAL_ROOT = discover_local_root(REPO_ROOT, COMMON_REPO_ROOT)


def repo_path(*parts: str) -> Path:
    if not parts:
        return REPO_ROOT
    candidate = Path(*parts)
    if candidate.is_absolute():
        return candidate
    worktree_path = REPO_ROOT / candidate
    if candidate.parts and candidate.parts[0] == ".local":
        return LOCAL_ROOT.joinpath(*candidate.parts[1:])
    if worktree_path.exists():
        return worktree_path
    common_path = COMMON_REPO_ROOT / candidate
    if common_path.exists():
        return common_path
    return worktree_path


def read_required_text(path: Path, label: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path.read_text(encoding="utf-8").strip()


def read_authentik_bootstrap_token() -> str:
    override = os.environ.get("LV3_AUTHENTIK_BOOTSTRAP_TOKEN", "").strip()
    if override:
        return override
    return read_required_text(AUTHENTIK_TOKEN_FILE, "Authentik bootstrap API token")


def read_mail_gateway_api_key() -> str:
    override = os.environ.get("LV3_MAIL_GATEWAY_API_KEY", "").strip()
    if override:
        return override
    return read_required_text(MAIL_GATEWAY_KEY_FILE, "platform transactional mail-gateway API key")


# ---------------------------------------------------------------------------
# Identity resolution (ADR 0385 / ADR 0407)
# Derive the config prefix and endpoints from inventory + the .local
# identity overlay rather than hardcoding one deployment. This keeps the
# committed script generic (no deployment-specific literals); real values come
# from .local/identity.yml at runtime. Env vars override for ad-hoc runs.
# ---------------------------------------------------------------------------
def _resolve_identity() -> tuple[str, str]:
    """Return (platform_domain, config_prefix).

    An explicit PLATFORM_DOMAIN env override takes full precedence. Authentik
    does not scope operator accounts inside a separate realm.
    """
    domain = os.environ.get("PLATFORM_DOMAIN", "").strip()
    prefix = ""
    if not domain:
        try:
            from identity_yaml import load_identity_vars

            identity_vars = load_identity_vars()
            domain = identity_vars.get("platform_domain", "").strip()
            prefix = identity_vars.get("platform_config_prefix", "").strip()
        except Exception:
            pass
    domain = domain or "example.com"
    prefix = prefix or domain.split(".")[0]
    return domain, prefix


PLATFORM_DOMAIN, CONFIG_PREFIX = _resolve_identity()

# Authentik
DEFAULT_AUTHENTIK_URL = f"https://id.{PLATFORM_DOMAIN}"
AUTHENTIK_TOKEN_FILE = repo_path(".local", "authentik", "bootstrap-token.txt")
PASSWORD_DIR = repo_path(".local", "authentik")

# Mail delivery — the platform mail-gateway HTTP API. It listens on the internal
# network only, so we reach it through the SSH proxy. The transactional profile
# fixes the sender identity, so no From/SMTP credentials are configured here.
MAIL_GATEWAY_KEY_FILE = repo_path(".local", "mail-platform", "profiles", "platform-transactional-gateway-api-key.txt")
SSH_KEY_FILE = repo_path(".local", "ssh", "bootstrap.id_ed25519")
SSH_PROXY = os.environ.get("LV3_SSH_PROXY", "").strip() or "ops@100.64.0.1"

# Headscale (self-hosted Tailscale control server)
DEFAULT_HEADSCALE_URL = f"https://headscale.{PLATFORM_DOMAIN}"
HEADSCALE_API_KEY_FILE = repo_path(".local", "headscale", "api-key.txt")
HEADSCALE_AUTHKEY_DIR = repo_path(".local", "headscale")

# step-ca
STEP_CA_URL = os.environ.get("LV3_STEP_CA_URL", "").strip() or f"https://ca.{PLATFORM_DOMAIN}"
STEP_CA_ROOT_CERT = repo_path(".local", "step-ca", "certs", "root_ca.crt")

# Role → (Authentik groups, OpenBao policies)
ROLE_DEFINITIONS: dict[str, dict[str, list[str]]] = {
    role_name: {
        "groups": list(definition.authentik_groups),
        "openbao_policies": list(definition.openbao_policies),
    }
    for role_name, definition in OPERATOR_MANAGER_ROLE_DEFINITIONS.items()
}


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def configured_url(env_var: str, default: str) -> str:
    override = os.environ.get(env_var, "").strip()
    if override:
        return override.rstrip("/")
    return default


def authentik_api(method: str, path: str, token: str, body: Any = None) -> tuple[int, Any]:
    """Make an Authentik admin REST API call. Returns (status_code, parsed_body)."""
    authentik_url = configured_url("LV3_AUTHENTIK_URL", DEFAULT_AUTHENTIK_URL)
    url = f"{authentik_url}/api/v3{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx()) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else None


def hs(method: str, path: str, api_key: str, body: Any = None) -> tuple[int, Any]:
    """Make a Headscale API call. Returns (status_code, parsed_body)."""
    headscale_url = configured_url("LV3_HEADSCALE_URL", DEFAULT_HEADSCALE_URL)
    url = f"{headscale_url}/api/v1{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx()) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else None


def headscale_provision(username: str, expiry: str, api_key: str, dry_run: bool = False) -> str:
    """
    Create a Headscale user (idempotent) and generate a one-time pre-auth key.
    Returns the auth key string and saves it to `.local/headscale/<username>-authkey.txt`.
    """
    authkey_file = HEADSCALE_AUTHKEY_DIR / f"{username}-authkey.txt"
    if authkey_file.exists():
        existing = authkey_file.read_text(encoding="utf-8").strip()
        print(f"[hs] Reusing existing authkey from {authkey_file}")
        return existing

    if dry_run:
        print(f"[hs] DRY-RUN: would create Headscale user '{username}' and generate pre-auth key")
        return "hskey-auth-DRY-RUN"

    HEADSCALE_AUTHKEY_DIR.mkdir(parents=True, exist_ok=True)

    status, users_body = hs("GET", "/user", api_key)
    if status != 200:
        raise RuntimeError(f"Headscale user listing failed: HTTP {status}: {users_body}")
    users = (users_body or {}).get("users", [])
    existing_user = next((user for user in users if user["name"] == username), None)

    if existing_user:
        user_id = existing_user["id"]
        print(f"[hs] User '{username}' already exists (id={user_id})")
    else:
        status, body = hs("POST", "/user", api_key, {"name": username})
        if status not in (200, 201):
            raise RuntimeError(f"Headscale user creation failed: HTTP {status}: {body}")
        user_id = body["user"]["id"]
        print(f"[hs] Created user '{username}' (id={user_id})")

    status, body = hs(
        "POST",
        "/preauthkey",
        api_key,
        {
            "user": user_id,
            "reusable": False,
            "ephemeral": False,
            "expiration": expiry,
        },
    )
    if status not in (200, 201) or not body.get("preAuthKey", {}).get("key"):
        raise RuntimeError(f"Headscale pre-auth key generation failed: HTTP {status}: {body}")

    authkey = body["preAuthKey"]["key"]
    authkey_file.write_text(authkey + "\n", encoding="utf-8")
    print(f"[hs] Pre-auth key generated -> {authkey_file}")
    return authkey


def get_ca_fingerprint() -> str:
    """
    Compute the SHA-256 fingerprint of the step-ca root CA cert in the format
    expected by `step ca bootstrap --fingerprint`.
    """
    result = subprocess.run(
        ["openssl", "x509", "-noout", "-fingerprint", "-sha256", "-in", str(STEP_CA_ROOT_CERT)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not read CA fingerprint: {result.stderr}")
    raw = result.stdout.strip().split("=", 1)[-1]
    return raw.lower().replace(":", "")


SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")

# Categories surfaced to a new operator, in display order. Catalog entries in
# other categories (raw infrastructure surfaces) are omitted from the welcome
# mail, as are the explicitly-skipped infra ids below.
_SERVICE_CATEGORY_ORDER = [
    ("access", "Access & identity"),
    ("automation", "Automation & apps"),
    ("data", "Data & storage"),
    ("observability", "Monitoring & logs"),
    ("communication", "Communication"),
    ("security", "Security"),
]
_SERVICE_SKIP_IDS = {"docker_runtime", "docker_build", "nginx_edge", "proxmox_ui"}


def render_service_lines(domain: str) -> str:
    """Build the welcome-email service list from the capability catalog.

    Public services only, with the generic ``example.com`` substituted for the
    live domain and grouped by catalog category. Falls back to a single SSO line
    if the catalog is unavailable, so a missing catalog never blocks a send.
    """
    try:
        payload = json.loads(SERVICE_CATALOG_PATH.read_text(encoding="utf-8"))
        services = [s for s in payload.get("services", []) if isinstance(s, dict)]
    except (OSError, json.JSONDecodeError):
        return f"  SSO portal                 https://id.{domain}"
    by_category: dict[str, list[tuple[str, str]]] = {}
    for service in services:
        url = service.get("public_url")
        if not url or service.get("id") in _SERVICE_SKIP_IDS:
            continue
        url = url.replace("example.com", domain)
        name = service.get("name") or service.get("id", "")
        by_category.setdefault(service.get("category", "other"), []).append((name, url))
    lines: list[str] = []
    for category_key, category_label in _SERVICE_CATEGORY_ORDER:
        entries = sorted(by_category.get(category_key, []))
        if not entries:
            continue
        lines.append(f"  {category_label}:")
        lines.extend(f"    {name:<26} {url}" for name, url in entries)
    return "\n".join(lines) if lines else f"  SSO portal                 https://id.{domain}"


PLAIN_TEMPLATE = """\
Hi {first_name},

Welcome to the {domain} platform! {requester_name} has provisioned you
a {role} account valid until {expiry}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 YOUR SSO CREDENTIALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Login portal : {authentik_url}
  Username     : {username}
  Password     : {password}
  Expires      : {expiry}

Change your password: {account_url}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PLATFORM SERVICES  (all use SSO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{services_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 VPN ACCESS (Tailscale / Headscale)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The platform uses a self-hosted Tailscale control server (Headscale).

  # 1. Install Tailscale
  brew install tailscale          # macOS
  curl -fsSL https://tailscale.com/install.sh | sh   # Linux

  # 2. Connect (pre-auth key valid until {expiry})
  sudo tailscale up \\
    --login-server {headscale_url} \\
    --authkey {headscale_authkey} \\
    --hostname {username}-laptop

  tailscale status    # verify — you'll get a 100.x.x.x address

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SSH ACCESS (step-ca certificates, 24h TTL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 1. Install Smallstep CLI
  brew install step               # macOS
  # or https://smallstep.com/docs/step-cli/installation

  # 2. Bootstrap the CA (one-time)
  step ca bootstrap \\
    --ca-url {ca_url} \\
    --fingerprint {ca_fingerprint}

  # 3. Follow the operator onboarding runbook for your first SSH cert
  #    docs/runbooks/operator-onboarding.md

  # 4. SSH in (requires Tailscale above)
  ssh {username}@100.64.0.1

Platform hosts once on VPN:
  100.64.0.1   ops host (SSH gateway, Docker)
  100.64.0.2   Proxmox hypervisor
  10.10.10.x   Internal Docker services

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CODEBASE TOUR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Repo: {git_url}

  config/                   operators.yaml, schemas, service catalog
  docs/adr/                 Architecture Decision Records — READ FIRST
  collections/...roles/     Ansible roles for all platform services
  scripts/                  Operator tooling (this script lives here)
  workstreams.yaml          Active in-progress changes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 QUICK CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [ ] Log in at {authentik_url} and change your password
  [ ] sudo tailscale up --login-server {headscale_url} --authkey <above>
  [ ] step ca bootstrap --ca-url {ca_url} --fingerprint {ca_fingerprint}
  [ ] Review docs/runbooks/operator-onboarding.md for SSH setup
  [ ] ssh {username}@100.64.0.1

Account expires {expiry}.

Welcome aboard,
{domain} platform (provisioned per ADR 0318)
---
CC: {cc_email} — audit record per ADR 0318.
"""


def build_email_payload(
    to_email: str,
    cc_email: str,
    first_name: str,
    username: str,
    password: str,
    role: str,
    expiry: str,
    requester_email: str,
    headscale_authkey: str,
    ca_fingerprint: str,
) -> dict[str, Any]:
    requester_name = requester_email.split("@", 1)[0].replace(".", " ").title()
    authentik_url = configured_url("LV3_AUTHENTIK_URL", DEFAULT_AUTHENTIK_URL)
    plain = PLAIN_TEMPLATE.format(
        first_name=first_name,
        requester_name=requester_name,
        role=role,
        expiry=expiry,
        username=username,
        password=password,
        cc_email=cc_email,
        headscale_authkey=headscale_authkey,
        ca_fingerprint=ca_fingerprint,
        domain=PLATFORM_DOMAIN,
        authentik_url=authentik_url,
        account_url=f"{authentik_url}/if/user/",
        headscale_url=configured_url("LV3_HEADSCALE_URL", DEFAULT_HEADSCALE_URL),
        ca_url=STEP_CA_URL,
        git_url=f"https://git.{PLATFORM_DOMAIN}",
        services_block=render_service_lines(PLATFORM_DOMAIN),
    )
    expiry_short = expiry[:10]
    payload: dict[str, Any] = {
        "to": [to_email],
        "subject": f"[{PLATFORM_DOMAIN}] Platform access — {first_name} — expires {expiry_short}",
        "text": plain,
    }
    if cc_email and cc_email != to_email:
        payload["cc"] = [cc_email]
    return payload


def mail_gateway_send_endpoint() -> str:
    """Resolve the mail-gateway /send URL from the service catalog.

    Honors the LV3_MAIL_PLATFORM_URL override (handled inside service_url).
    """
    from operator_manager import service_url

    return service_url("mail_platform").rstrip("/") + "/send"


def send_email_via_gateway(payload: dict[str, Any], api_key: str, ssh_key: Path) -> None:
    """POST the message to the mail-gateway /send API via the SSH proxy.

    The gateway listens on the internal network only, so curl runs on the proxy
    host. The transactional profile (selected by the API key) fixes the sender.
    """
    endpoint = mail_gateway_send_endpoint()
    remote_cmd = (
        "curl -sS -X POST "
        f"-H {shlex.quote('X-API-Key: ' + api_key)} "
        "-H 'Content-Type: application/json' --data-binary @- "
        f"{shlex.quote(endpoint)}"
    )
    result = subprocess.run(
        ["ssh", "-i", str(ssh_key), "-o", "StrictHostKeyChecking=accept-new", SSH_PROXY, remote_cmd],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Mail gateway send failed: {result.stderr.decode('utf-8', errors='replace')}")
    recipients = list(payload.get("to", [])) + list(payload.get("cc", []))
    print(f"Email sent via mail gateway to {', '.join(recipients)}")


def _list_authentik(path: str, token: str) -> list[dict[str, Any]]:
    """Read every page from a small Authentik collection without leaking tokens."""
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        separator = "&" if "?" in path else "?"
        status, body = authentik_api("GET", f"{path}{separator}page={page}&page_size=100", token)
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(f"Authentik list failed for {path}: HTTP {status}")
        batch = body.get("results")
        if not isinstance(batch, list):
            raise RuntimeError(f"Authentik list for {path} did not return results.")
        results.extend(item for item in batch if isinstance(item, dict))
        pagination = body.get("pagination")
        next_page = pagination.get("next") if isinstance(pagination, dict) else None
        if next_page is None:
            return results
        if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page <= page:
            raise RuntimeError(f"Authentik list for {path} returned an invalid pagination cursor.")
        page = next_page


def _fetch_authentik_user(username: str, token: str) -> tuple[str | None, bool, dict[str, Any] | None]:
    users = _list_authentik(f"/core/users/?username={urllib.parse.quote(username, safe='')}&include_groups=true", token)
    matches = [user for user in users if user.get("username") == username]
    if len(matches) > 1:
        raise RuntimeError(f"Authentik returned multiple users for {username!r}.")
    if not matches:
        return None, False, None
    user_id = matches[0].get("pk")
    if user_id is None or isinstance(user_id, bool) or not str(user_id).strip():
        raise RuntimeError(f"Authentik user '{username}' has no primary key.")
    return str(user_id), True, matches[0]


def _authentik_group_map(token: str) -> dict[str, str]:
    groups = _list_authentik("/core/groups/", token)
    group_map: dict[str, str] = {}
    for group in groups:
        name, group_id = group.get("name"), group.get("pk")
        if isinstance(name, str) and name and group_id is not None and not isinstance(group_id, bool):
            group_map[name] = str(group_id)
    return group_map


def _verify_assignments(user_id: str, role_def: dict[str, list[str]], token: str) -> None:
    status, user = authentik_api("GET", f"/core/users/{urllib.parse.quote(user_id, safe='')}/", token)
    if status != 200 or not isinstance(user, dict):
        raise RuntimeError(f"Authentik user verification failed: HTTP {status}")
    group_map = _authentik_group_map(token)
    expected_groups = set(role_def["groups"])
    missing_groups = sorted(expected_groups - set(group_map))
    if missing_groups:
        raise RuntimeError(f"Authentik groups are missing: {missing_groups}")
    group_names_by_id = {group_id: name for name, group_id in group_map.items()}
    user_groups = user.get("groups")
    if not isinstance(user_groups, list):
        raise RuntimeError("Authentik user verification response did not include a groups list.")
    observed_groups = {
        group_names_by_id[str(group_id)] for group_id in user_groups if str(group_id) in group_names_by_id
    }
    missing_assignments = sorted(expected_groups - observed_groups)
    if missing_assignments:
        raise RuntimeError(f"Authentik group assignment verification failed: missing groups={missing_assignments}")
    print(f"[5] Groups: {sorted(observed_groups)}")


def provision(args: argparse.Namespace, dry_run: bool = False) -> None:
    role_def = ROLE_DEFINITIONS[args.role]

    PASSWORD_DIR.mkdir(parents=True, exist_ok=True)
    pw_file = PASSWORD_DIR / f"{args.username}-password.txt"
    existing_password = pw_file.read_text(encoding="utf-8").strip() if pw_file.exists() else None
    password = existing_password or secrets.token_urlsafe(24)

    if existing_password:
        print(f"[0] Reusing existing password from {pw_file}")
    elif dry_run:
        print(f"[0] DRY-RUN: would write password to {pw_file}")
    else:
        print(f"[0] Will write a new password to {pw_file} after Authentik user creation")

    if dry_run:
        print(f"[dry-run] Would provision {args.username} ({args.email}) role={args.role}")
        if args.skip_email:
            print("[dry-run] Would stop after Authentik provisioning and group verification")
        else:
            print(f"[dry-run] Would create or reuse Headscale authkey under {HEADSCALE_AUTHKEY_DIR}")
            print(f"[dry-run] Resolved domain={PLATFORM_DOMAIN} authentik={DEFAULT_AUTHENTIK_URL}")
            print(f"[dry-run] Would send onboarding email via mail gateway using proxy {SSH_PROXY}")
            print("[dry-run] Rendered welcome email below:\n")
            print(
                build_email_payload(
                    to_email=args.email,
                    cc_email=args.requester,
                    first_name=args.name.split()[0],
                    username=args.username,
                    password=password,
                    role=args.role,
                    expiry=args.expires,
                    requester_email=args.requester,
                    headscale_authkey="<generated-at-send-time>",
                    ca_fingerprint="<computed-from-step-ca-root>",
                )["text"]
            )
        return

    token = read_authentik_bootstrap_token()
    user_id, user_exists, _existing_user = _fetch_authentik_user(args.username, token)
    group_map = _authentik_group_map(token)
    missing_group_defs = [name for name in role_def["groups"] if name not in group_map]
    if missing_group_defs:
        raise RuntimeError(f"Authentik groups missing from the directory: {missing_group_defs}")
    user_payload = {
        "username": args.username,
        "name": args.name,
        "email": args.email,
        "is_active": True,
        "type": "internal",
        "groups": [group_map[name] for name in role_def["groups"]],
    }
    if user_exists:
        assert user_id is not None
        status, _ = authentik_api("PATCH", f"/core/users/{urllib.parse.quote(user_id, safe='')}/", token, user_payload)
        if status != 200:
            raise RuntimeError(f"Authentik user update failed: HTTP {status}")
        print(f"[1] Authentik user already exists and was reconciled: {user_id}")
        if not existing_password and not args.skip_email:
            raise RuntimeError(
                f"Authentik user already exists but the local password file is missing: {pw_file}. "
                "Use --skip-email or reset the user through the Authentik recovery flow."
            )
    else:
        status, user = authentik_api("POST", "/core/users/", token, user_payload)
        if status != 201 or not isinstance(user, dict):
            raise RuntimeError(f"Authentik user creation failed: HTTP {status}")
        user_id_raw = user.get("pk")
        if user_id_raw is None or isinstance(user_id_raw, bool) or not str(user_id_raw).strip():
            raise RuntimeError("Authentik user creation response has no primary key.")
        user_id = str(user_id_raw)
        status, _ = authentik_api(
            "POST", f"/core/users/{urllib.parse.quote(user_id, safe='')}/set_password/", token, {"password": password}
        )
        if status != 204:
            raise RuntimeError(f"Authentik password setup failed: HTTP {status}")
        pw_file.write_text(password + "\n", encoding="utf-8")
        print("[2] Authentik user created")
        print(f"[2] Generated password -> {pw_file}")
        print(f"[2] User ID: {user_id}")

    assert user_id is not None
    _verify_assignments(user_id, role_def, token)

    if args.skip_email:
        print("\n✓ Authentik provisioning and group verification succeeded.")
        print(f"  Authentik username : {args.username}")
        print(f"  Authentik user ID  : {user_id}")
        print(f"  Password file      : {pw_file}")
        print("  Email / Headscale  : skipped by request (--skip-email)")
        return

    hs_api_key = read_required_text(HEADSCALE_API_KEY_FILE, "Headscale API key")
    gateway_api_key = read_mail_gateway_api_key()
    ca_fingerprint = get_ca_fingerprint()
    print(f"[6] CA fingerprint: {ca_fingerprint}")

    hs_username = args.username.replace(".", "-")
    headscale_authkey = headscale_provision(hs_username, args.expires, hs_api_key, dry_run=False)

    first_name = args.name.split()[0]
    payload = build_email_payload(
        to_email=args.email,
        cc_email=args.requester,
        first_name=first_name,
        username=args.username,
        password=password,
        role=args.role,
        expiry=args.expires,
        requester_email=args.requester,
        headscale_authkey=headscale_authkey,
        ca_fingerprint=ca_fingerprint,
    )
    send_email_via_gateway(payload, gateway_api_key, SSH_KEY_FILE)

    print(f"\n✓ Operator '{args.name}' fully provisioned.")
    print(f"  Authentik username : {args.username}")
    print(f"  Authentik user ID  : {user_id}")
    print(f"  Password file      : {pw_file}")
    print(f"  Headscale user     : {hs_username}")
    print(f"  Headscale authkey  : {HEADSCALE_AUTHKEY_DIR / (hs_username + '-authkey.txt')}")
    print(f"  CA fingerprint     : {ca_fingerprint}")
    print(f"  Email sent to      : {args.email} (CC: {args.requester})")
    print(f"  Expires            : {args.expires}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a new operator account on the platform (ADR 0318).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--id", required=True, help="Operator ID (e.g. matei-busui-tmp-001)")
    parser.add_argument("--name", required=True, help='Full name (e.g. "Matei Busui")')
    parser.add_argument("--email", required=True, help="Operator email address")
    parser.add_argument("--username", required=True, help="Authentik username (e.g. matei.busui-tmp)")
    parser.add_argument(
        "--role",
        required=True,
        choices=sorted(ROLE_DEFINITIONS),
        help="Access tier: admin | operator | viewer",
    )
    parser.add_argument(
        "--expires",
        required=True,
        help="Expiry datetime ISO8601 (e.g. 2026-04-08T00:00:00Z)",
    )
    parser.add_argument(
        "--requester",
        required=True,
        help="Requester email — receives CC of welcome email as audit record",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without making any changes",
    )
    parser.add_argument(
        "--skip-email",
        action="store_true",
        help="Verify the Authentik provisioning path without generating Headscale state or sending email",
    )
    args = parser.parse_args()
    provision(args, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
