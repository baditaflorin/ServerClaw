"""ADR 0412 — Keycloak Account Expiry Reaper.

Scans Keycloak users with an `account_expires_at` custom attribute and disables
any whose expiry timestamp is in the past. Runs daily at 02:00 UTC via Windmill
scheduler (see windmill_runtime defaults/main.yml: f/lv3/keycloak_account_expiry_reaper).

Required Windmill variables (set in Windmill UI or via windmill-runtime.env):
  - KEYCLOAK_ADMIN_BASE_URL  — e.g. https://sso.example.com
  - KEYCLOAK_ADMIN_REALM     — realm that holds user accounts (e.g. lv3)
  - KEYCLOAK_ADMIN_CLIENT_ID — admin service account client_id (e.g. lv3-admin-runtime)
  - KEYCLOAK_ADMIN_CLIENT_SECRET — client secret for the above client

Returns a structured summary: disabled accounts, skipped accounts, errors.
"""

import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _get_token(base_url: str, client_id: str, client_secret: str) -> str:
    """Obtain a Keycloak admin API token via client_credentials grant."""
    token_url = f"{base_url}/realms/master/protocol/openid-connect/token"
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(token_url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


def _api(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, Any]:
    """Execute a Keycloak admin REST API call."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None


def main(
    dry_run: bool = False,
    realm: str = "",
    base_url: str = "",
    client_id: str = "",
    client_secret: str = "",
) -> dict[str, Any]:
    """Disable expired Keycloak accounts.

    Parameters can be passed as Windmill arguments; if omitted, environment
    variables KEYCLOAK_ADMIN_* are used.
    """
    base_url = base_url or os.environ.get("KEYCLOAK_ADMIN_BASE_URL", "")
    realm = realm or os.environ.get("KEYCLOAK_ADMIN_REALM", "")
    client_id = client_id or os.environ.get("KEYCLOAK_ADMIN_CLIENT_ID", "lv3-admin-runtime")
    client_secret = client_secret or os.environ.get("KEYCLOAK_ADMIN_CLIENT_SECRET", "")

    if not all([base_url, realm, client_id, client_secret]):
        return {
            "status": "blocked",
            "reason": (
                "Missing required configuration. Set KEYCLOAK_ADMIN_BASE_URL, "
                "KEYCLOAK_ADMIN_REALM, KEYCLOAK_ADMIN_CLIENT_ID, and "
                "KEYCLOAK_ADMIN_CLIENT_SECRET in Windmill variables or pass as args."
            ),
        }

    now = datetime.datetime.utcnow()
    disabled: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []

    try:
        token = _get_token(base_url, client_id, client_secret)
    except Exception as exc:
        return {"status": "error", "reason": f"Token acquisition failed: {exc}"}

    # Fetch all users with the account_expires_at attribute
    first = 0
    page_size = 100
    while True:
        _, users = _api(
            "GET",
            f"{base_url}/admin/realms/{realm}/users?first={first}&max={page_size}&q=account_expires_at:*",
            token,
        )
        if not users:
            break

        for user in users:
            uid = user.get("id", "")
            username = user.get("username", "")
            attrs = user.get("attributes", {})
            expires_vals = attrs.get("account_expires_at", [])
            if not expires_vals:
                skipped.append({"username": username, "reason": "no account_expires_at attribute"})
                continue

            try:
                expires_at = datetime.datetime.strptime(expires_vals[0], "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                errors.append({"username": username, "reason": f"invalid expires_at: {expires_vals[0]}"})
                continue

            if expires_at > now:
                days_left = (expires_at - now).days
                skipped.append({"username": username, "reason": f"not expired (expires in {days_left}d)"})
                continue

            if not user.get("enabled", True):
                skipped.append({"username": username, "reason": "already disabled"})
                continue

            if dry_run:
                disabled.append({"username": username, "expires_at": expires_vals[0], "action": "dry_run"})
                continue

            status, _ = _api(
                "PUT",
                f"{base_url}/admin/realms/{realm}/users/{uid}",
                token,
                body={"enabled": False},
            )
            if status == 204:
                disabled.append({"username": username, "expires_at": expires_vals[0], "action": "disabled"})
            else:
                errors.append({"username": username, "reason": f"disable returned HTTP {status}"})

        if len(users) < page_size:
            break
        first += page_size

    return {
        "status": "ok",
        "run_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": dry_run,
        "disabled_count": len(disabled),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "disabled": disabled,
        "skipped": skipped,
        "errors": errors,
    }
