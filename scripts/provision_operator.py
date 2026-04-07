#!/usr/bin/env python3
"""
provision_operator.py — Canonical operator onboarding script for lv3.org platform.

Implements ADR 0318: repeatable, code-first operator provisioning with audit-trail CC.
Wraps the Keycloak direct-API procedure from ADR 0317 and adds Headscale VPN +
step-ca bootstrap details so the operator receives everything in a single email.

Usage:
    python3 scripts/provision_operator.py \
        --id matei-busui-tmp-001 \
        --name "Matei Busui" \
        --email busui.matei1994@gmail.com \
        --username matei.busui-tmp \
        --role admin \
        --expires 2026-04-08T00:00:00Z \
        --requester florin@badita.org \
        [--dry-run] [--skip-email]

What it does:
    1. Resolve controller-local inputs from the shared checkout even under `.worktrees/`
    2. Reuse or generate `.local/keycloak/<username>-password.txt`
    3. Create or verify the Keycloak user, roles, and groups
    4. Optionally create or verify the Headscale user and pre-auth key
    5. Optionally send one onboarding email to the operator with CC to the requester

`--skip-email` keeps the Keycloak provisioning and verification path live without
re-sending onboarding email or generating a fresh Headscale auth key. Use it when
re-verifying an already onboarded operator from exact `main`.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


def read_keycloak_bootstrap_password() -> str:
    override = os.environ.get("LV3_KEYCLOAK_BOOTSTRAP_PASSWORD", "").strip()
    if override:
        return override
    return read_required_text(BOOTSTRAP_PASS_FILE, "Keycloak bootstrap password")


def read_platform_smtp_password() -> str:
    override = os.environ.get("LV3_PLATFORM_SMTP_PASSWORD", "").strip()
    if override:
        return override
    return read_required_text(SMTP_PASS_FILE, "platform transactional mailbox password")


# Keycloak
DEFAULT_KEYCLOAK_URL = "https://sso.lv3.org"
REALM = "lv3"
ADMIN_USER = "lv3-bootstrap-admin"
BOOTSTRAP_PASS_FILE = repo_path(".local", "keycloak", "bootstrap-admin-password.txt")
PASSWORD_DIR = repo_path(".local", "keycloak")

# SMTP (internal — relay via SSH proxy)
SMTP_HOST = "10.10.10.20"
SMTP_PORT = 587
SMTP_USER = "platform"
SMTP_FROM = "LV3 Platform <platform@lv3.org>"
SMTP_PASS_FILE = repo_path(".local", "mail-platform", "profiles", "platform-transactional-mailbox-password.txt")
SSH_KEY_FILE = repo_path(".local", "ssh", "bootstrap.id_ed25519")
SSH_PROXY = "ops@100.64.0.1"

# Headscale (self-hosted Tailscale control server)
DEFAULT_HEADSCALE_URL = "https://headscale.lv3.org"
HEADSCALE_API_KEY_FILE = repo_path(".local", "headscale", "api-key.txt")
HEADSCALE_AUTHKEY_DIR = repo_path(".local", "headscale")

# step-ca
STEP_CA_URL = "https://ca.lv3.org"
STEP_CA_ROOT_CERT = repo_path(".local", "step-ca", "certs", "root_ca.crt")

# Role → (realm_roles, groups, openbao_policies)
ROLE_DEFINITIONS: dict[str, dict[str, list[str]]] = {
    role_name: {
        "realm_roles": list(definition.keycloak_roles),
        "groups": list(definition.keycloak_groups),
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


ADMIN_CLIENT_ID = "lv3-admin-runtime"
ADMIN_CLIENT_SECRET_FILE = repo_path(".local", "keycloak", "admin-client-secret.txt")


def get_token(bootstrap_pass: str) -> str:
    """Acquire an admin token from the Keycloak master realm.

    Tries client-credentials grant with lv3-admin-runtime first (more reliable
    when the bootstrap admin password has been rotated).  Falls back to the
    legacy password grant with lv3-bootstrap-admin.
    """
    keycloak_url = configured_url("LV3_KEYCLOAK_URL", DEFAULT_KEYCLOAK_URL)
    token_url = f"{keycloak_url}/realms/master/protocol/openid-connect/token"

    # Try client credentials first if the secret file exists
    if ADMIN_CLIENT_SECRET_FILE.exists():
        client_secret = ADMIN_CLIENT_SECRET_FILE.read_text(encoding="utf-8").strip()
        if client_secret:
            data = urllib.parse.urlencode(
                {
                    "client_id": ADMIN_CLIENT_ID,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                token_url,
                data=data,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                with urllib.request.urlopen(req, context=_ssl_ctx()) as response:
                    return json.loads(response.read())["access_token"]
            except urllib.error.HTTPError:
                print("[token] client-credentials grant failed, falling back to password grant")

    # Fallback: password grant with bootstrap admin
    data = urllib.parse.urlencode(
        {
            "client_id": "admin-cli",
            "grant_type": "password",
            "username": ADMIN_USER,
            "password": bootstrap_pass,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        token_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, context=_ssl_ctx()) as response:
        return json.loads(response.read())["access_token"]


def kc(method: str, path: str, token: str, body: Any = None) -> tuple[int, Any]:
    """Make a Keycloak admin REST API call. Returns (status_code, parsed_body)."""
    keycloak_url = configured_url("LV3_KEYCLOAK_URL", DEFAULT_KEYCLOAK_URL)
    url = f"{keycloak_url}/admin/realms/{REALM}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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


PLAIN_TEMPLATE = """\
Hi {first_name},

Welcome to the lv3.org homelab platform! {requester_name} has provisioned you
a {role} account valid until {expiry}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 YOUR SSO CREDENTIALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Login portal : https://sso.lv3.org
  Username     : {username}
  Password     : {password}
  Expires      : {expiry}

Change your password: https://sso.lv3.org/realms/lv3/account/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PLATFORM SERVICES  (all use SSO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Grafana  (metrics)       https://grafana.lv3.org
  Gitea    (source code)   https://gitea.lv3.org
  Outline  (docs/wiki)     https://outline.lv3.org
  Vikunja  (tasks)         https://vikunja.lv3.org
  Open WebUI (AI)          https://chat.lv3.org
  Mattermost (chat)        https://mattermost.lv3.org
  Harbor (registry)        https://harbor.lv3.org
  Windmill (workflows)     https://windmill.lv3.org

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 VPN ACCESS (Tailscale / Headscale)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The platform uses a self-hosted Tailscale control server (Headscale).

  # 1. Install Tailscale
  brew install tailscale          # macOS
  curl -fsSL https://tailscale.com/install.sh | sh   # Linux

  # 2. Connect (pre-auth key valid until {expiry})
  sudo tailscale up \\
    --login-server https://headscale.lv3.org \\
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
    --ca-url https://ca.lv3.org \\
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
Repo: https://gitea.lv3.org/platform/proxmox_florin_server

  config/                   operators.yaml, schemas, service catalog
  docs/adr/                 Architecture Decision Records — READ FIRST
  collections/...roles/     Ansible roles for all ~40 services
  scripts/                  Operator tooling (this script lives here)
  workstreams.yaml          Active in-progress changes

CI/CD: every push runs 22 validation checks before landing on main.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 QUICK CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  □ Log in at https://sso.lv3.org and change your password
  □ sudo tailscale up --login-server https://headscale.lv3.org --authkey <above>
  □ step ca bootstrap --ca-url https://ca.lv3.org --fingerprint {ca_fingerprint}
  □ Review docs/runbooks/operator-onboarding.md for SSH setup
  □ ssh {username}@100.64.0.1
  □ Browse https://grafana.lv3.org for platform dashboards

Account expires {expiry}.

Welcome aboard,
lv3.org platform (provisioned by Codex agent per ADR 0318)
---
CC: {cc_email} — audit record per ADR 0318.
"""


def build_email(
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
) -> MIMEMultipart:
    requester_name = requester_email.split("@", 1)[0].replace(".", " ").title()
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
    )
    expiry_short = expiry[:10]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[lv3.org] Platform access — {first_name} — expires {expiry_short}"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Cc"] = cc_email
    msg["Reply-To"] = requester_email
    msg.attach(MIMEText(plain, "plain"))
    return msg


def send_email_via_ssh_proxy(
    smtp_pass: str,
    ssh_key: Path,
    msg: MIMEMultipart,
    recipients: list[str],
) -> None:
    """Send email through the SSH proxy host (SMTP is on the internal network)."""
    script = f"""
import smtplib
msg_str = {repr(msg.as_string())}
with smtplib.SMTP("{SMTP_HOST}", {SMTP_PORT}, timeout=15) as s:
    s.ehlo()
    if s.has_extn("STARTTLS"):
        s.starttls(); s.ehlo()
    s.login("{SMTP_USER}", {repr(smtp_pass)})
    s.sendmail("platform@lv3.org", {repr(recipients)}, msg_str)
    print("sent")
"""
    result = subprocess.run(
        ["ssh", "-i", str(ssh_key), "-o", "StrictHostKeyChecking=accept-new", SSH_PROXY, "python3"],
        input=script.encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"SSH/SMTP failed: {result.stderr.decode('utf-8', errors='replace')}")
    print(f"Email sent to {', '.join(recipients)}")


def _fetch_keycloak_user(username: str, bootstrap_pass: str) -> tuple[str | None, bool]:
    token = get_token(bootstrap_pass)
    status, body = kc("GET", f"/users?username={username}&exact=true", token)
    if status != 200:
        raise RuntimeError(f"Keycloak user lookup failed for {username}: HTTP {status}: {body}")
    users = body or []
    if users:
        return users[0]["id"], True
    return None, False


def _verify_assignments(user_id: str, role_def: dict[str, list[str]], bootstrap_pass: str) -> None:
    token = get_token(bootstrap_pass)
    status, roles_body = kc("GET", f"/users/{user_id}/role-mappings/realm", token)
    if status != 200:
        raise RuntimeError(f"Keycloak role verification failed: HTTP {status}: {roles_body}")
    observed_roles = {entry["name"] for entry in (roles_body or [])}

    token = get_token(bootstrap_pass)
    status, groups_body = kc("GET", f"/users/{user_id}/groups", token)
    if status != 200:
        raise RuntimeError(f"Keycloak group verification failed: HTTP {status}: {groups_body}")
    observed_groups = {entry["name"] for entry in (groups_body or [])}

    expected_roles = set(role_def["realm_roles"])
    expected_groups = set(role_def["groups"])
    missing_roles = sorted(expected_roles - observed_roles)
    missing_groups = sorted(expected_groups - observed_groups)
    if missing_roles or missing_groups:
        raise RuntimeError(
            "Keycloak assignment verification failed: "
            f"missing roles={missing_roles}, missing groups={missing_groups}"
        )

    print(f"[5] Roles:  {sorted(observed_roles)}")
    print(f"[5] Groups: {sorted(observed_groups)}")


def provision(args: argparse.Namespace, dry_run: bool = False) -> None:
    role_def = ROLE_DEFINITIONS[args.role]

    PASSWORD_DIR.mkdir(parents=True, exist_ok=True)
    pw_file = PASSWORD_DIR / f"{args.username}-password.txt"
    existing_password = pw_file.read_text(encoding="utf-8").strip() if pw_file.exists() else None

    if existing_password:
        password = existing_password
        print(f"[0] Reusing existing password from {pw_file}")
    else:
        password = secrets.token_urlsafe(24)
        if dry_run:
            print(f"[0] DRY-RUN: would write password to {pw_file}")
        else:
            print(f"[0] Will write a new password to {pw_file} after Keycloak user creation")

    if dry_run:
        print(f"[dry-run] Would provision {args.username} ({args.email}) role={args.role}")
        if args.skip_email:
            print("[dry-run] Would stop after Keycloak provisioning and assignment verification")
        else:
            print(f"[dry-run] Would create or reuse Headscale authkey under {HEADSCALE_AUTHKEY_DIR}")
            print(f"[dry-run] Would send onboarding email via {SMTP_HOST}:{SMTP_PORT} using {SSH_PROXY}")
        return

    bootstrap_pass = read_keycloak_bootstrap_password()

    user_id, user_exists = _fetch_keycloak_user(args.username, bootstrap_pass)
    if user_exists:
        if not existing_password:
            raise RuntimeError(
                "Keycloak user already exists but the local password file is missing: "
                f"{pw_file}"
            )
        assert user_id is not None
        print(f"[1] Keycloak user already exists: {user_id}")
    else:
        first, *rest = args.name.split()
        last = " ".join(rest) if rest else "Tmp"
        payload = {
            "username": args.username,
            "email": args.email,
            "firstName": first,
            "lastName": last,
            "enabled": True,
            "emailVerified": True,
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        }
        token = get_token(bootstrap_pass)
        status, body = kc("POST", "/users", token, payload)
        if status != 201:
            raise RuntimeError(f"Keycloak user creation failed: HTTP {status}: {body}")
        pw_file.write_text(password + "\n", encoding="utf-8")
        print(f"[2] Keycloak user created")
        print(f"[2] Generated password -> {pw_file}")
        user_id, user_exists = _fetch_keycloak_user(args.username, bootstrap_pass)
        if not user_exists or user_id is None:
            raise RuntimeError(f"Keycloak user lookup failed after create for {args.username}")
        print(f"[2] User ID: {user_id}")

    assert user_id is not None

    for role_name in role_def["realm_roles"]:
        token = get_token(bootstrap_pass)
        status, role_obj = kc("GET", f"/roles/{role_name}", token)
        if status != 200 or not role_obj:
            raise RuntimeError(f"Keycloak role lookup failed for {role_name}: HTTP {status}: {role_obj}")
        token = get_token(bootstrap_pass)
        status, body = kc(
            "POST",
            f"/users/{user_id}/role-mappings/realm",
            token,
            [{"id": role_obj["id"], "name": role_obj["name"]}],
        )
        if status not in (204, 409):
            raise RuntimeError(f"Keycloak role assignment failed for {role_name}: HTTP {status}: {body}")
        print(f"[3] Role '{role_name}' -> HTTP {status}")

    token = get_token(bootstrap_pass)
    status, all_groups = kc("GET", "/groups?max=200", token)
    if status != 200:
        raise RuntimeError(f"Keycloak group listing failed: HTTP {status}: {all_groups}")
    group_map = {group["name"]: group["id"] for group in (all_groups or [])}
    missing_group_defs = [name for name in role_def["groups"] if name not in group_map]
    if missing_group_defs:
        raise RuntimeError(f"Keycloak groups missing from realm: {missing_group_defs}")
    for group_name in role_def["groups"]:
        token = get_token(bootstrap_pass)
        status, body = kc("PUT", f"/users/{user_id}/groups/{group_map[group_name]}", token)
        if status not in (204, 409):
            raise RuntimeError(f"Keycloak group assignment failed for {group_name}: HTTP {status}: {body}")
        print(f"[4] Group '{group_name}' -> HTTP {status}")

    _verify_assignments(user_id, role_def, bootstrap_pass)

    if args.skip_email:
        print("\n✓ Keycloak provisioning and assignment verification succeeded.")
        print(f"  Keycloak username  : {args.username}")
        print(f"  Keycloak user ID   : {user_id}")
        print(f"  Password file      : {pw_file}")
        print("  Email / Headscale  : skipped by request (--skip-email)")
        return

    hs_api_key = read_required_text(HEADSCALE_API_KEY_FILE, "Headscale API key")
    smtp_pass = read_platform_smtp_password()
    ca_fingerprint = get_ca_fingerprint()
    print(f"[6] CA fingerprint: {ca_fingerprint}")

    hs_username = args.username.replace(".", "-")
    headscale_authkey = headscale_provision(hs_username, args.expires, hs_api_key, dry_run=False)

    first_name = args.name.split()[0]
    msg = build_email(
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
    send_email_via_ssh_proxy(smtp_pass, SSH_KEY_FILE, msg, [args.email, args.requester])

    print(f"\n✓ Operator '{args.name}' fully provisioned.")
    print(f"  Keycloak username  : {args.username}")
    print(f"  Keycloak user ID   : {user_id}")
    print(f"  Password file      : {pw_file}")
    print(f"  Headscale user     : {hs_username}")
    print(f"  Headscale authkey  : {HEADSCALE_AUTHKEY_DIR / (hs_username + '-authkey.txt')}")
    print(f"  CA fingerprint     : {ca_fingerprint}")
    print(f"  Email sent to      : {args.email} (CC: {args.requester})")
    print(f"  Expires            : {args.expires}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a new operator account on lv3.org (ADR 0318).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--id", required=True, help="Operator ID (e.g. matei-busui-tmp-001)")
    parser.add_argument("--name", required=True, help='Full name (e.g. "Matei Busui")')
    parser.add_argument("--email", required=True, help="Operator email address")
    parser.add_argument("--username", required=True, help="Keycloak username (e.g. matei.busui-tmp)")
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
        help="Verify the Keycloak provisioning path without generating Headscale state or sending email",
    )
    args = parser.parse_args()
    provision(args, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
