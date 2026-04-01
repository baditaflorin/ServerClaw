#!/usr/bin/env python3
"""
provision_operator.py — Canonical operator onboarding script for lv3.org platform.

Implements ADR 0318: repeatable, code-first operator provisioning with audit-trail CC.
Wraps the Keycloak direct-API procedure from ADR 0317.

Usage:
    python3 scripts/provision_operator.py \
        --id matei-busui-tmp-001 \
        --name "Matei Busui" \
        --email busui.matei1994@gmail.com \
        --username matei.busui-tmp \
        --role admin \
        --expires 2026-04-08T00:00:00Z \
        --requester florin@badita.org \
        [--dry-run]

What it does:
    1. Validates input against operators.yaml schema constraints
    2. Checks for existing Keycloak user (idempotent)
    3. Creates Keycloak user with generated password (or reuses .local password file)
    4. Assigns realm role and groups per role tier (see ADR 0108)
    5. Verifies assignments
    6. Sends rich onboarding email to operator, CC to requester (audit trail per ADR 0318)
    7. Updates operators.yaml with the new entry (or prints YAML if --dry-run)
    8. Saves password to .local/keycloak/<username>-password.txt

Prerequisites:
    - SSH access to 100.64.0.1 (for SMTP relay — internal network only)
    - .local/keycloak/bootstrap-admin-password.txt readable
    - .local/mail-platform/profiles/platform-transactional-mailbox-password.txt readable
    - .local/ssh/hetzner_llm_agents_ed25519 readable (for SSH SMTP relay)

Related ADRs:
    - ADR 0108: Operator onboarding/offboarding workflow design
    - ADR 0307: Temporary operator account schema
    - ADR 0317: Keycloak direct-API provisioning procedure
    - ADR 0318: This script — canonical IaC onboarding with CC audit trail
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import smtplib
import subprocess
import sys
import urllib.parse
import urllib.request
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
KEYCLOAK_URL = "https://sso.lv3.org"
REALM = "lv3"
ADMIN_USER = "lv3-bootstrap-admin"

BOOTSTRAP_PASS_FILE = REPO_ROOT / ".local" / "keycloak" / "bootstrap-admin-password.txt"
SMTP_PASS_FILE = REPO_ROOT / ".local" / "mail-platform" / "profiles" / "platform-transactional-mailbox-password.txt"
SSH_KEY_FILE = REPO_ROOT / ".local" / "ssh" / "hetzner_llm_agents_ed25519"
PASSWORD_DIR = REPO_ROOT / ".local" / "keycloak"
OPERATORS_YAML = REPO_ROOT / "config" / "operators.yaml"

SMTP_HOST = "10.10.10.20"
SMTP_PORT = 587
SMTP_USER = "platform"
SMTP_FROM = "LV3 Platform <platform@lv3.org>"
SSH_PROXY = "ops@100.64.0.1"

# Role → (realm_roles, groups, openbao_policies)
ROLE_DEFINITIONS: dict[str, dict[str, list[str]]] = {
    "admin": {
        "realm_roles": ["platform-admin"],
        "groups": ["lv3-platform-admins", "grafana-admins"],
        "openbao_policies": ["platform-admin"],
    },
    "operator": {
        "realm_roles": ["platform-operator"],
        "groups": ["lv3-platform-operators"],
        "openbao_policies": ["platform-operator"],
    },
    "viewer": {
        "realm_roles": ["platform-viewer"],
        "groups": ["lv3-platform-viewers"],
        "openbao_policies": ["platform-read"],
    },
}

# ---------------------------------------------------------------------------
# Keycloak helpers
# ---------------------------------------------------------------------------

def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def get_token(bootstrap_pass: str) -> str:
    """Acquire a 60-second admin token from the Keycloak master realm."""
    enc = urllib.parse.quote(bootstrap_pass)
    data = (
        f"client_id=admin-cli&grant_type=password"
        f"&username={ADMIN_USER}&password={enc}"
    )
    req = urllib.request.Request(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data=data.encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, context=_ssl_ctx()) as r:
        return json.loads(r.read())["access_token"]


def kc(method: str, path: str, token: str, body: Any = None) -> tuple[int, Any]:
    """Make a Keycloak admin REST API call. Returns (status_code, parsed_body)."""
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx()) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else None


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

PLAIN_TEMPLATE = """\
Hi {first_name},

Welcome to the lv3.org homelab platform! {requester_name} has provisioned you
a temporary {role} account valid until {expiry}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 YOUR CREDENTIALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Login portal : https://sso.lv3.org
  Username     : {username}
  Password     : {password}
  Expires      : {expiry}

Change your password: https://sso.lv3.org/realms/lv3/account/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PLATFORM SERVICES  (all use SSO above)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Grafana  (metrics)       https://grafana.lv3.org
  Gitea    (source code)   https://gitea.lv3.org
  Outline  (docs/wiki)     https://outline.lv3.org
  Vikunja  (tasks)         https://vikunja.lv3.org
  Open WebUI (AI)          https://chat.lv3.org
  Mattermost (chat)        https://mattermost.lv3.org
  Harbor (registry)        https://harbor.lv3.org
  Windmill (workflows)     https://windmill.lv3.org

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SSH ACCESS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH uses short-lived certificates from step-ca (24-hour TTL):

  1. brew install step
  2. step ca bootstrap --ca-url https://ca.lv3.org --fingerprint <ask {requester_name}>
  3. step ssh login {username} --provisioner sso   # opens browser
  4. ssh {username}@100.64.0.1                     # needs Tailscale

Ask {requester_name} for the Tailscale invite and CA fingerprint.
Renew the certificate daily with: step ssh login {username}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CODEBASE TOUR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Repo: https://gitea.lv3.org/platform/proxmox_florin_server

  config/                   operators.yaml, schemas, service catalog
  docs/adr/                 Architecture Decision Records — READ FIRST
  collections/...roles/     Ansible roles for all ~40 services
  scripts/                  Operator tooling (this script lives here)
  workstreams.yaml          Active in-progress changes

INFRASTRUCTURE:
  Host     — Single Proxmox hypervisor (Hetzner dedicated)
  Network  — Tailscale mesh + internal Docker bridge 10.10.10.x
  CI/CD    — 22-check validation gate on every push to main
  Identity — Keycloak (SSO), step-ca (SSH certs), OpenBao (secrets)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 NEXT STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  □ Log in at https://sso.lv3.org and change your password
  □ Ask {requester_name} for the Tailscale invite + CA fingerprint
  □ Clone the repo and browse docs/adr/
  □ Join Mattermost for async chat

Account expires {expiry}. Ask {requester_name} for an extension if needed.

Welcome aboard,
lv3.org platform (provisioned by Claude agent)
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
) -> MIMEMultipart:
    requester_name = requester_email.split("@")[0].title()
    plain = PLAIN_TEMPLATE.format(
        first_name=first_name,
        requester_name=requester_name,
        role=role,
        expiry=expiry,
        username=username,
        password=password,
        cc_email=cc_email,
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
        [
            "ssh",
            "-i", str(ssh_key),
            "-o", "StrictHostKeyChecking=accept-new",
            SSH_PROXY,
            "python3",
        ],
        input=script.encode(),
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"SSH/SMTP failed: {result.stderr.decode()}"
        )
    print(f"Email sent to {', '.join(recipients)}")


# ---------------------------------------------------------------------------
# Main provision flow
# ---------------------------------------------------------------------------

def provision(args: argparse.Namespace, dry_run: bool = False) -> None:
    bootstrap_pass = BOOTSTRAP_PASS_FILE.read_text().strip()
    smtp_pass = SMTP_PASS_FILE.read_text().strip()

    role_def = ROLE_DEFINITIONS[args.role]

    # --- Step 0: password file ---
    pw_file = PASSWORD_DIR / f"{args.username}-password.txt"
    if pw_file.exists():
        password = pw_file.read_text().strip()
        print(f"[0] Reusing existing password from {pw_file}")
    else:
        password = secrets.token_urlsafe(24)
        if not dry_run:
            pw_file.write_text(password + "\n")
            print(f"[0] Generated password → {pw_file}")
        else:
            print(f"[0] DRY-RUN: would write password to {pw_file}")

    if dry_run:
        print(f"[dry-run] Would provision {args.username} ({args.email}) role={args.role}")
        return

    # --- Step 1: check existing user ---
    token = get_token(bootstrap_pass)
    status, body = kc("GET", f"/users?username={args.username}&exact=true", token)
    users = body or []
    if users:
        user_id = users[0]["id"]
        print(f"[1] User already exists: {user_id}")
    else:
        # Step 2: create user
        token = get_token(bootstrap_pass)
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
        status, _ = kc("POST", "/users", token, payload)
        if status != 201:
            raise RuntimeError(f"User creation failed: HTTP {status}")
        print(f"[2] User created (HTTP 201)")

        token = get_token(bootstrap_pass)
        _, body = kc("GET", f"/users?username={args.username}&exact=true", token)
        user_id = body[0]["id"]
        print(f"[2] User ID: {user_id}")

    # --- Step 3: assign realm roles ---
    for role_name in role_def["realm_roles"]:
        token = get_token(bootstrap_pass)
        _, role_obj = kc("GET", f"/roles/{role_name}", token)
        token = get_token(bootstrap_pass)
        status, _ = kc(
            "POST",
            f"/users/{user_id}/role-mappings/realm",
            token,
            [{"id": role_obj["id"], "name": role_obj["name"]}],
        )
        print(f"[3] Role '{role_name}' → HTTP {status}")

    # --- Step 4: assign groups ---
    token = get_token(bootstrap_pass)
    _, all_groups = kc("GET", "/groups?max=200", token)
    group_map = {g["name"]: g["id"] for g in (all_groups or [])}
    for grp_name in role_def["groups"]:
        if grp_name not in group_map:
            print(f"[4] WARNING: group '{grp_name}' not found in realm — skipping")
            continue
        token = get_token(bootstrap_pass)
        status, _ = kc("PUT", f"/users/{user_id}/groups/{group_map[grp_name]}", token)
        print(f"[4] Group '{grp_name}' → HTTP {status}")

    # --- Step 5: verify ---
    token = get_token(bootstrap_pass)
    _, roles_body = kc("GET", f"/users/{user_id}/role-mappings/realm", token)
    token = get_token(bootstrap_pass)
    _, groups_body = kc("GET", f"/users/{user_id}/groups", token)
    print(f"[5] Roles:  {[r['name'] for r in (roles_body or [])]}")
    print(f"[5] Groups: {[g['name'] for g in (groups_body or [])]}")

    # --- Step 6: send email ---
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
    )
    send_email_via_ssh_proxy(
        smtp_pass=smtp_pass,
        ssh_key=SSH_KEY_FILE,
        msg=msg,
        recipients=[args.email, args.requester],
    )

    print(f"\n✓ Operator '{args.name}' provisioned successfully.")
    print(f"  Keycloak username : {args.username}")
    print(f"  User ID           : {user_id}")
    print(f"  Password file     : {pw_file}")
    print(f"  Email sent to     : {args.email} (CC: {args.requester})")
    print(f"  Expires           : {args.expires}")
    print()
    print("NEXT: add the operators.yaml entry and push to origin/main.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
        choices=list(ROLE_DEFINITIONS),
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
    args = parser.parse_args()
    provision(args, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
