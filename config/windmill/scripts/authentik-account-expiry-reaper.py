"""ADR 0412 — Authentik account expiry reaper.

Scans Authentik users with an ``account_expires_at`` attribute and disables any
whose expiry timestamp is in the past. The Windmill schedule runs daily at
02:00 UTC. The only credential accepted is an Authentik API token; it is never
returned in the job result or included in an error message.

Required Windmill environment variables (or equivalent script arguments):
  - LV3_AUTHENTIK_URL
  - LV3_AUTHENTIK_BOOTSTRAP_TOKEN
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


USERS_PATH = "/core/users/"


def _api(
    method: str,
    base_url: str,
    path: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Execute one Authentik API request without exposing response bodies on failure."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v3{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Authentik API transport failure: {exc.reason}") from None


def _expiry_value(attributes: Any) -> str | None:
    """Return a supported expiry attribute while tolerating legacy list values."""
    if not isinstance(attributes, dict):
        return None
    value = attributes.get("account_expires_at")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str) and value[0].strip():
        return value[0].strip()
    return None


def _parse_expiry(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def main(
    dry_run: bool = False,
    authentik_url: str = "",
    api_token: str = "",
) -> dict[str, Any]:
    """Disable expired Authentik accounts and return a safe structured summary."""
    authentik_url = authentik_url or os.environ.get("LV3_AUTHENTIK_URL", "")
    api_token = api_token or os.environ.get("LV3_AUTHENTIK_BOOTSTRAP_TOKEN", "")
    if not authentik_url or not api_token:
        return {
            "status": "blocked",
            "reason": "Missing LV3_AUTHENTIK_URL or LV3_AUTHENTIK_BOOTSTRAP_TOKEN.",
        }

    now = dt.datetime.now(dt.UTC)
    disabled: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    page = 1

    while True:
        query = urllib.parse.urlencode({"page": page, "page_size": 100})
        try:
            status, payload = _api("GET", authentik_url, f"{USERS_PATH}?{query}", api_token)
        except RuntimeError as exc:
            return {"status": "error", "reason": str(exc)}
        if status != 200 or not isinstance(payload, dict):
            return {"status": "error", "reason": f"Authentik user listing returned HTTP {status}."}
        users = payload.get("results")
        pagination = payload.get("pagination")
        if not isinstance(users, list) or not isinstance(pagination, dict):
            return {"status": "error", "reason": "Authentik user listing returned an invalid pagination payload."}

        for user in users:
            if not isinstance(user, dict):
                errors.append({"username": "unknown", "reason": "invalid user record"})
                continue
            user_id = user.get("pk")
            username = str(user.get("username") or user_id or "unknown")
            expiry_raw = _expiry_value(user.get("attributes"))
            if expiry_raw is None:
                skipped.append({"username": username, "reason": "no account_expires_at attribute"})
                continue
            try:
                expires_at = _parse_expiry(expiry_raw)
            except ValueError:
                errors.append({"username": username, "reason": f"invalid expires_at: {expiry_raw}"})
                continue
            if expires_at > now:
                days_left = (expires_at - now).days
                skipped.append({"username": username, "reason": f"not expired (expires in {days_left}d)"})
                continue
            if not user.get("is_active", True):
                skipped.append({"username": username, "reason": "already disabled"})
                continue
            if user_id is None or isinstance(user_id, bool) or not str(user_id).strip():
                errors.append({"username": username, "reason": "missing user primary key"})
                continue
            if dry_run:
                disabled.append({"username": username, "expires_at": expiry_raw, "action": "dry_run"})
                continue
            status, _ = _api(
                "PATCH",
                authentik_url,
                f"{USERS_PATH}{urllib.parse.quote(str(user_id), safe='')}/",
                api_token,
                body={"is_active": False},
            )
            if status == 200:
                disabled.append({"username": username, "expires_at": expiry_raw, "action": "disabled"})
            else:
                errors.append({"username": username, "reason": f"disable returned HTTP {status}"})

        next_page = pagination.get("next")
        if not next_page:
            break
        if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page <= page:
            return {"status": "error", "reason": "Authentik user listing returned an invalid next page."}
        page = next_page

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
