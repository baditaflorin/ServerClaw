#!/usr/bin/env python3
"""Self-contained Uptime Kuma provisioning agent.

This script runs ON the Uptime Kuma VM (delegated by the
``uptime_kuma_provision`` Ansible role) and talks to the local Uptime Kuma
socket.io API at ``http://127.0.0.1:<port>``.  It has **no** repo-local
dependencies (unlike ``scripts/uptime_kuma_tool.py``, which imports the repo
``platform`` package) so it can be copied to a guest VM and executed inside a
minimal virtualenv that only contains ``requests`` and ``python-socketio``.

It is fully generic: monitors and the public status page are derived from the
health-probe catalog plus the deployment's ``platform_domain`` and Keycloak
realm name.  Adding an enabled service to the catalog automatically adds its
monitor and a status-page entry on the next run.

Subcommands:
  provision           bootstrap (if needed) + ensure monitors + ensure status page
  ensure-monitors     reconcile monitors only
  ensure-status-page  reconcile the public status page only
  list-monitors       print the live monitor list

The command is idempotent: it reconciles live state toward the desired state
and stores the admin session (username/password/token/base_url) in the auth
file so re-runs reuse the token instead of re-creating the admin.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

import requests
import socketio


# Catalog placeholders (safe for the public mirror); substituted at runtime.
CATALOG_PLATFORM_DOMAIN = "example.com"
CATALOG_KEYCLOAK_REALM = "lv3"

# Uptime Kuma rejects monitors whose check interval is below this floor with
# "Interval cannot be less than 20 seconds". Clamp catalog values so a stray
# fast interval never breaks the whole reconcile.
MIN_INTERVAL_SECONDS = 20

DEFAULT_MONITOR: dict[str, Any] = {
    "type": "http",
    "name": "",
    "parent": None,
    "url": "https://",
    "method": "GET",
    "ipFamily": None,
    "interval": 60,
    "retryInterval": 60,
    "resendInterval": 0,
    "maxretries": 0,
    "notificationIDList": {},
    "ignoreTls": False,
    "upsideDown": False,
    "expiryNotification": False,
    "maxredirects": 10,
    "accepted_statuscodes": ["200-299"],
    "kafkaProducerBrokers": [],
    "kafkaProducerSaslOptions": {},
    "rabbitmqNodes": [],
    "conditions": [],
    "active": True,
}

# Fields Uptime Kuma returns on read that must not be echoed back on edit.
READ_ONLY_MONITOR_FIELDS = {
    "path",
    "pathName",
    "childrenIDs",
    "tags",
    "maintenance",
    "forceInactive",
    "cacheBust",
}


# --------------------------------------------------------------------------- #
# Auth file helpers (stdlib only — no repo dependency)
# --------------------------------------------------------------------------- #
def load_auth(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except (ValueError, OSError):
            pass
    return {}


def save_auth(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Desired-state derivation from the health-probe catalog
# --------------------------------------------------------------------------- #
def _apply_substitutions(value: Any, substitutions: list[tuple[str, str]]) -> Any:
    if isinstance(value, str):
        for old, new in substitutions:
            value = value.replace(old, new)
        return value
    if isinstance(value, dict):
        return {k: _apply_substitutions(v, substitutions) for k, v in value.items()}
    if isinstance(value, list):
        return [_apply_substitutions(item, substitutions) for item in value]
    return value


def build_substitutions(platform_domain: str | None, keycloak_realm: str | None) -> list[tuple[str, str]]:
    subs: list[tuple[str, str]] = []
    if platform_domain and platform_domain != CATALOG_PLATFORM_DOMAIN:
        subs.append((CATALOG_PLATFORM_DOMAIN, platform_domain))
    if keycloak_realm and keycloak_realm != CATALOG_KEYCLOAK_REALM:
        # Only rewrite the realm path segment to avoid clobbering unrelated text.
        subs.append((f"/realms/{CATALOG_KEYCLOAK_REALM}/", f"/realms/{keycloak_realm}/"))
    return subs


def build_desired_monitors(
    catalog: dict[str, Any],
    *,
    platform_domain: str | None = None,
    keycloak_realm: str | None = None,
) -> list[dict[str, Any]]:
    services = catalog.get("services")
    if not isinstance(services, dict):
        raise ValueError("health probe catalog must define a 'services' object")
    subs = build_substitutions(platform_domain, keycloak_realm)
    monitors: list[dict[str, Any]] = []
    names: set[str] = set()
    for service_id, service in services.items():
        if not isinstance(service, dict):
            raise ValueError(f"catalog entry '{service_id}' must be an object")
        uptime_kuma = service.get("uptime_kuma")
        if not isinstance(uptime_kuma, dict) or not uptime_kuma.get("enabled"):
            continue
        monitor = uptime_kuma.get("monitor")
        if not isinstance(monitor, dict):
            raise ValueError(f"catalog entry '{service_id}' enables uptime_kuma but defines no monitor")
        name = monitor.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"catalog entry '{service_id}' monitor needs a non-empty name")
        if name in names:
            raise ValueError(f"duplicate monitor name in catalog: {name}")
        names.add(name)
        payload = dict(monitor)
        payload.setdefault("service_id", service_id)
        if subs:
            payload = _apply_substitutions(payload, subs)
        monitors.append(payload)
    if not monitors:
        raise ValueError("catalog defines no enabled Uptime Kuma monitors")
    return monitors


def normalize_monitor(monitor: dict) -> dict:
    payload = dict(DEFAULT_MONITOR)
    payload.update(monitor)
    # `service_id` is catalog metadata used by this agent, not an Uptime Kuma
    # monitor column. Uptime Kuma inserts every payload key as a DB column, so
    # leaving it in raises "table monitor has no column named service_id".
    payload.pop("service_id", None)
    monitor_type = payload["type"]
    if monitor_type != "http" and "url" not in monitor:
        payload["url"] = ""
    if monitor_type == "http" and not payload.get("url"):
        raise ValueError(f"HTTP monitor '{payload.get('name', '<unnamed>')}' is missing a url")
    if monitor_type == "port":
        if not payload.get("hostname"):
            raise ValueError(f"Port monitor '{payload.get('name', '<unnamed>')}' is missing hostname")
        if payload.get("port") is None:
            raise ValueError(f"Port monitor '{payload.get('name', '<unnamed>')}' is missing port")
    if not isinstance(payload.get("accepted_statuscodes"), list):
        raise ValueError(f"Monitor '{payload.get('name', '<unnamed>')}' has invalid accepted_statuscodes")
    # Uptime Kuma enforces a hard floor on check/retry intervals; clamp any
    # catalog value below it rather than letting the server reject the monitor.
    for field in ("interval", "retryInterval"):
        try:
            value = int(payload.get(field, MIN_INTERVAL_SECONDS))
        except (TypeError, ValueError):
            value = MIN_INTERVAL_SECONDS
        payload[field] = max(value, MIN_INTERVAL_SECONDS)
    return payload


def build_status_page_spec(
    monitors: list[dict[str, Any]],
    *,
    platform_domain: str,
    slug: str,
) -> dict[str, Any]:
    """Auto-build a single-group status page covering every monitor."""
    return {
        "slug": slug,
        "title": f"{platform_domain} Platform Status",
        "description": f"Current operational status of {platform_domain} platform services.",
        "theme": "dark",
        "showTags": False,
        "customCSS": "",
        "footerText": f"{platform_domain} — powered by Uptime Kuma",
        "showPoweredBy": True,
        "showOnlyLastHeartbeat": False,
        "showCertificateExpiry": False,
        "autoRefreshInterval": 300,
        "domainNameList": [f"status.{platform_domain}"],
        "groups": [
            {
                "name": "Platform Services",
                "monitor_names": [m["name"] for m in monitors],
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Uptime Kuma socket.io client
# --------------------------------------------------------------------------- #
class UptimeKumaClient:
    def __init__(self, base_url: str, verify_ssl: bool = True):
        session = requests.Session()
        self.sio = socketio.Client(
            logger=False,
            engineio_logger=False,
            reconnection=False,
            ssl_verify=verify_ssl,
            http_session=session,
        )
        self.base_url = base_url.rstrip("/")
        self.http = session
        self.verify_ssl = verify_ssl
        self.monitor_list: dict = {}
        self.monitor_list_event = threading.Event()

        @self.sio.on("monitorList")
        def on_monitor_list(data):  # noqa: ANN001
            self.monitor_list = data or {}
            self.monitor_list_event.set()

    def connect(self) -> None:
        self.sio.connect(self.base_url, socketio_path="socket.io", wait_timeout=20)

    def disconnect(self) -> None:
        if self.sio.connected:
            self.sio.disconnect()

    def call(self, event: str, *args):
        payload = tuple(args) if len(args) > 1 else (args[0] if args else None)
        return self.sio.call(event, payload, timeout=30)

    def need_setup(self, timeout: int = 30) -> bool:
        return bool(self.sio.call("needSetup", timeout=timeout))

    def setup(self, username: str, password: str) -> dict:
        return self.sio.call("setup", (username, password), timeout=30)

    def login(self, username: str, password: str, token: str = "") -> dict:
        return self.sio.call("login", {"username": username, "password": password, "token": token}, timeout=30)

    def login_by_token(self, token: str) -> dict:
        return self.sio.call("loginByToken", token, timeout=30)

    def get_settings(self) -> dict:
        return self.sio.call("getSettings", timeout=30)

    def set_settings(self, settings: dict, current_password: str = "") -> dict:
        return self.sio.call("setSettings", (settings, current_password), timeout=30)

    def get_monitor_list(self) -> dict:
        self.monitor_list_event.clear()
        result = self.sio.call("getMonitorList", timeout=30)
        if not result.get("ok"):
            raise RuntimeError(result.get("msg", "Unable to read monitor list"))
        if not self.monitor_list_event.wait(timeout=30):
            raise RuntimeError("Timed out waiting for monitor list event")
        return self.monitor_list

    def get_monitor(self, monitor_id: int) -> dict:
        result = self.sio.call("getMonitor", monitor_id, timeout=30)
        if not result.get("ok"):
            raise RuntimeError(result.get("msg", f"Unable to read monitor {monitor_id}"))
        return result["monitor"]

    def add_monitor(self, monitor: dict) -> dict:
        return self.sio.call("add", monitor, timeout=30)

    def edit_monitor(self, monitor: dict) -> dict:
        return self.sio.call("editMonitor", monitor, timeout=30)

    def add_status_page(self, title: str, slug: str) -> dict:
        return self.call("addStatusPage", title, slug)

    def get_status_page(self, slug: str) -> dict:
        result = self.call("getStatusPage", slug)
        if not result.get("ok"):
            raise RuntimeError(result.get("msg", f"Unable to read status page '{slug}'"))
        return result["config"]

    def save_status_page(self, slug: str, config: dict, public_group_list: list[dict], img_data_url: str = "") -> dict:
        return self.call("saveStatusPage", slug, config, img_data_url, public_group_list)

    def database_setup_required(self) -> bool:
        response = self.http.get(
            f"{self.base_url}/setup-database-info",
            timeout=15,
            verify=self.verify_ssl,
            allow_redirects=False,
        )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return bool(response.json().get("needSetup"))

    def configure_sqlite_database(self) -> None:
        response = self.http.post(
            f"{self.base_url}/setup-database",
            json={"dbConfig": {"type": "sqlite"}},
            timeout=30,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        if not response.json().get("ok"):
            raise RuntimeError("Uptime Kuma database bootstrap did not report success")

    def wait_for_socket(self, timeout: int = 120) -> None:
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                self.connect()
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(2)
        raise RuntimeError(f"Timed out waiting for Uptime Kuma main server: {last_error}")

    def wait_for_db_ready(self, timeout: int = 180) -> None:
        """After choosing SQLite, the backend restarts; poll the HTTP setup
        endpoint until it stops reporting that a database bootstrap is needed."""
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                if not self.database_setup_required():
                    return
            except Exception as exc:  # noqa: BLE001
                last_error = exc  # server mid-restart — keep polling
            time.sleep(2)
        raise RuntimeError(f"Timed out waiting for Uptime Kuma database bootstrap: {last_error}")

    def connect_when_ready(self, timeout: int = 180) -> None:
        """Connect the socket and confirm the backend actually answers a
        lightweight event. A socket that connects to a still-restarting server
        accepts the connection but never replies, so verify with a short probe
        and reconnect on failure instead of blocking on a 30s call timeout."""
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                if not self.sio.connected:
                    self.connect()
                # Probe with a short timeout; raises on a half-ready backend.
                self.need_setup(timeout=8)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                try:
                    self.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(2)
        raise RuntimeError(f"Timed out waiting for Uptime Kuma socket to respond: {last_error}")


# --------------------------------------------------------------------------- #
# Reconcilers
# --------------------------------------------------------------------------- #
def ensure_logged_in(client: UptimeKumaClient, auth: dict, username: str | None, password: str | None) -> dict:
    if auth.get("token"):
        token_result = client.login_by_token(auth["token"])
        if token_result.get("ok"):
            return auth

    if client.need_setup():
        username = username or auth.get("username") or "lv3-automation"
        password = password or auth.get("password") or secrets.token_urlsafe(24)
        setup_result = client.setup(username, password)
        if not setup_result.get("ok"):
            raise RuntimeError(setup_result.get("msg", "Initial Uptime Kuma setup failed"))
        auth["username"] = username
        auth["password"] = password

    username = username or auth.get("username")
    password = password or auth.get("password")
    if not username or not password:
        raise RuntimeError("No usable Uptime Kuma credentials were provided or stored locally")

    login_result = client.login(username, password)
    if not login_result.get("ok"):
        raise RuntimeError(login_result.get("msg", "Uptime Kuma login failed"))

    auth["username"] = username
    auth["password"] = password
    auth["token"] = login_result["token"]
    return auth


def set_primary_base_url(client: UptimeKumaClient, base_url: str) -> None:
    settings_result = client.get_settings()
    if not settings_result.get("ok"):
        raise RuntimeError(settings_result.get("msg", "Unable to read Uptime Kuma settings"))
    settings = settings_result["data"]
    if settings.get("primaryBaseURL") == base_url:
        return
    settings["primaryBaseURL"] = base_url
    update_result = client.set_settings(settings, "")
    if not update_result.get("ok"):
        raise RuntimeError(update_result.get("msg", "Unable to update Uptime Kuma settings"))


def sanitize_existing_monitor(monitor: dict) -> dict:
    return {k: v for k, v in monitor.items() if k not in READ_ONLY_MONITOR_FIELDS}


def reconcile_monitors(client: UptimeKumaClient, desired_monitors: list[dict]) -> None:
    current = client.get_monitor_list()
    current_by_name = {m["name"]: m for m in current.values()}
    created = updated = 0
    for raw_monitor in desired_monitors:
        desired = normalize_monitor(raw_monitor)
        existing_summary = current_by_name.get(desired["name"])
        if existing_summary:
            existing = sanitize_existing_monitor(client.get_monitor(existing_summary["id"]))
            existing.update(desired)
            result = client.edit_monitor(existing)
            if not result.get("ok"):
                raise RuntimeError(result.get("msg", f"Unable to update monitor {desired['name']}"))
            updated += 1
        else:
            result = client.add_monitor(desired)
            if not result.get("ok"):
                raise RuntimeError(result.get("msg", f"Unable to create monitor {desired['name']}"))
            created += 1
    print(f"monitors: created={created} updated={updated} total={len(desired_monitors)}")


def reconcile_status_page(client: UptimeKumaClient, spec: dict) -> None:
    slug = spec["slug"]
    title = spec["title"]
    try:
        current = client.get_status_page(slug)
        action = "updated"
    except RuntimeError as exc:
        if "No slug?" not in str(exc):
            raise
        created = client.add_status_page(title, slug)
        if not created.get("ok"):
            raise RuntimeError(created.get("msg", f"Unable to create status page '{slug}'"))
        current = client.get_status_page(slug)
        action = "created"

    monitor_list = client.get_monitor_list()
    monitors_by_name = {m["name"]: m for m in monitor_list.values()}
    groups: list[dict] = []
    for raw_group in spec["groups"]:
        group = {"name": raw_group["name"], "monitorList": []}
        for monitor_name in raw_group.get("monitor_names", []):
            if monitor_name not in monitors_by_name:
                raise RuntimeError(f"status page references unknown monitor '{monitor_name}'")
            group["monitorList"].append({"id": monitors_by_name[monitor_name]["id"]})
        groups.append(group)

    save_config = {
        **current,
        "slug": slug,
        "title": title,
        "description": spec.get("description", ""),
        "theme": spec.get("theme", current.get("theme", "dark")),
        "showTags": bool(spec.get("showTags", False)),
        "customCSS": spec.get("customCSS", ""),
        "footerText": spec.get("footerText", ""),
        "showPoweredBy": bool(spec.get("showPoweredBy", True)),
        "showOnlyLastHeartbeat": bool(spec.get("showOnlyLastHeartbeat", False)),
        "showCertificateExpiry": bool(spec.get("showCertificateExpiry", False)),
        "autoRefreshInterval": int(spec.get("autoRefreshInterval", 300)),
        "domainNameList": spec.get("domainNameList", []),
    }
    result = client.save_status_page(slug, save_config, groups, "")
    if not result.get("ok"):
        raise RuntimeError(result.get("msg", f"Unable to save status page '{slug}'"))
    print(f"status-page: {action} slug={slug} groups={len(groups)} monitors={sum(len(g['monitorList']) for g in groups)}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def load_catalog(path: Path) -> dict:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def run(args) -> int:
    auth_file = Path(args.auth_file).expanduser()
    auth = load_auth(auth_file)
    base_url = (args.base_url or auth.get("base_url") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("--base-url is required (no base_url stored in the auth file yet)")
    auth["base_url"] = base_url

    catalog = load_catalog(Path(args.catalog).expanduser())
    desired_monitors = build_desired_monitors(
        catalog,
        platform_domain=args.platform_domain,
        keycloak_realm=args.keycloak_realm,
    )
    status_spec = build_status_page_spec(
        desired_monitors,
        platform_domain=args.platform_domain,
        slug=args.status_slug,
    )

    client = UptimeKumaClient(base_url=base_url, verify_ssl=not args.insecure)
    try:
        # First contact may require the one-time SQLite database bootstrap.
        # Choosing SQLite restarts the backend, so wait for it to come back
        # before opening the socket, then confirm the socket actually answers.
        if client.database_setup_required():
            client.configure_sqlite_database()
            client.wait_for_db_ready()
        client.connect_when_ready()
        auth = ensure_logged_in(client, auth, args.username, args.password)
        save_auth(auth_file, auth)

        if args.command in ("provision",):
            set_primary_base_url(client, args.primary_base_url or base_url)

        if args.command in ("provision", "ensure-monitors"):
            reconcile_monitors(client, desired_monitors)
        if args.command in ("provision", "ensure-status-page"):
            reconcile_status_page(client, status_spec)
        if args.command == "list-monitors":
            for monitor in sorted(client.get_monitor_list().values(), key=lambda m: m["name"].lower()):
                print(f"{monitor['id']}\t{monitor['type']}\t{monitor['name']}")
    finally:
        client.disconnect()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Self-contained Uptime Kuma provisioning agent")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("provision", "ensure-monitors", "ensure-status-page", "list-monitors"):
        p = sub.add_parser(name)
        p.add_argument("--base-url", help="e.g. http://127.0.0.1:3001")
        p.add_argument("--auth-file", required=True, help="admin session JSON (created/updated in place)")
        p.add_argument("--catalog", required=True, help="path to health-probe-catalog.json")
        p.add_argument("--platform-domain", required=True, help="deployment domain, e.g. 0mcp.com")
        p.add_argument("--keycloak-realm", default=None, help="Keycloak realm name (defaults to no substitution)")
        p.add_argument("--status-slug", default="platform", help="status page slug")
        p.add_argument("--primary-base-url", default=None, help="public base URL stored in settings")
        p.add_argument("--username", default=None)
        p.add_argument("--password", default=None)
        p.add_argument("--insecure", action="store_true", help="skip TLS verification")
        p.set_defaults(func=run)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Uptime Kuma provisioning failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
