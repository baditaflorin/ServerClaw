#!/usr/bin/env python3

import argparse
import json
import secrets
import sys
import threading
import time
from pathlib import Path

import requests
import socketio

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, write_json


DEFAULT_AUTH_FILE = repo_path(".local", "uptime-kuma", "admin-session.json")
DEFAULT_MONITORS_FILE = repo_path("config", "uptime-kuma", "monitors.json")
DEFAULT_STATUS_PAGE_FILE = repo_path("config", "uptime-kuma", "status-page.json")

DEFAULT_MONITOR = {
    "type": "http",
    "name": "",
    "parent": None,
    "url": "https://",
    "method": "GET",
    "location": "world",
    "ipFamily": None,
    "interval": 60,
    "retryInterval": 60,
    "resendInterval": 0,
    "maxretries": 0,
    "retryOnlyOnStatusCodeFailure": False,
    "notificationIDList": {},
    "ignoreTls": False,
    "upsideDown": False,
    "expiryNotification": False,
    "domainExpiryNotification": True,
    "maxredirects": 10,
    "accepted_statuscodes": ["200-299"],
    "kafkaProducerBrokers": [],
    "kafkaProducerSaslOptions": {},
    "rabbitmqNodes": [],
    "conditions": [],
    "active": True,
}

READ_ONLY_MONITOR_FIELDS = {
    "path",
    "pathName",
    "childrenIDs",
    "tags",
    "maintenance",
    "forceInactive",
    "cacheBust",
}
def load_auth_json(path: Path) -> dict:
    return load_json(path, default={})


def save_json(path: Path, payload: dict) -> None:
    write_json(path, payload, indent=2, sort_keys=True, mode=0o600)


def normalize_monitor(monitor: dict) -> dict:
    payload = dict(DEFAULT_MONITOR)
    payload.update(monitor)

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

    return payload


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
        self.monitor_list = {}
        self.monitor_list_event = threading.Event()
        self.maintenance_list = {}
        self.maintenance_list_event = threading.Event()

        @self.sio.on("monitorList")
        def on_monitor_list(data):
            self.monitor_list = data or {}
            self.monitor_list_event.set()

        @self.sio.on("maintenanceList")
        def on_maintenance_list(data):
            self.maintenance_list = data or {}
            self.maintenance_list_event.set()

    def connect(self) -> None:
        self.sio.connect(self.base_url, socketio_path="socket.io", wait_timeout=20)

    def disconnect(self) -> None:
        if self.sio.connected:
            self.sio.disconnect()

    def call(self, event: str, *args):
        payload = tuple(args) if len(args) > 1 else (args[0] if args else None)
        return self.sio.call(event, payload, timeout=30)

    def need_setup(self) -> bool:
        return bool(self.sio.call("needSetup", timeout=30))

    def setup(self, username: str, password: str) -> dict:
        return self.sio.call("setup", (username, password), timeout=30)

    def login(self, username: str, password: str, token: str = "") -> dict:
        payload = {
            "username": username,
            "password": password,
            "token": token,
        }
        return self.sio.call("login", payload, timeout=30)

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

    def get_maintenance_list(self) -> dict:
        self.maintenance_list_event.clear()
        result = self.call("getMaintenanceList")
        if not result.get("ok"):
            raise RuntimeError(result.get("msg", "Unable to read maintenance list"))
        if not self.maintenance_list_event.wait(timeout=30):
            raise RuntimeError("Timed out waiting for maintenance list event")
        return self.maintenance_list

    def add_maintenance(self, maintenance: dict) -> dict:
        return self.call("addMaintenance", maintenance)

    def edit_maintenance(self, maintenance: dict) -> dict:
        return self.call("editMaintenance", maintenance)

    def delete_maintenance(self, maintenance_id: int) -> dict:
        return self.call("deleteMaintenance", maintenance_id)

    def add_monitor_maintenance(self, maintenance_id: int, monitors: list[dict]) -> dict:
        return self.call("addMonitorMaintenance", maintenance_id, monitors)

    def add_maintenance_status_page(self, maintenance_id: int, status_pages: list[dict]) -> dict:
        return self.call("addMaintenanceStatusPage", maintenance_id, status_pages)

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
        payload = response.json()
        if not payload.get("ok"):
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


def resolve_auth(args) -> tuple[Path, dict]:
    auth_file = Path(args.auth_file).expanduser()
    auth = load_auth_json(auth_file)
    if args.base_url:
        auth["base_url"] = args.base_url.rstrip("/")
    return auth_file, auth


def ensure_logged_in(client: UptimeKumaClient, auth: dict, username: str | None, password: str | None) -> dict:
    if auth.get("token"):
        token_result = client.login_by_token(auth["token"])
        if token_result.get("ok"):
            return auth

    need_setup = client.need_setup()

    if need_setup:
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
    payload = {}
    for key, value in monitor.items():
        if key not in READ_ONLY_MONITOR_FIELDS:
            payload[key] = value
    return payload


def ensure_monitors(client: UptimeKumaClient, monitors_path: Path) -> None:
    desired_monitors = json.loads(monitors_path.read_text())
    current = client.get_monitor_list()
    current_by_name = {monitor["name"]: monitor for monitor in current.values()}

    for raw_monitor in desired_monitors:
        desired = normalize_monitor(raw_monitor)
        existing_summary = current_by_name.get(desired["name"])

        if existing_summary:
            existing = sanitize_existing_monitor(client.get_monitor(existing_summary["id"]))
            existing.update(desired)
            result = client.edit_monitor(existing)
            if not result.get("ok"):
                raise RuntimeError(result.get("msg", f"Unable to update monitor {desired['name']}"))
            action = "updated"
        else:
            result = client.add_monitor(desired)
            if not result.get("ok"):
                raise RuntimeError(result.get("msg", f"Unable to create monitor {desired['name']}"))
            action = "created"

        print(f"{action}: {desired['name']}")


def load_status_page_config(path: Path) -> dict:
    payload = json.loads(path.read_text())
    slug = payload.get("slug")
    title = payload.get("title")
    groups = payload.get("groups")
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError("status page config slug must be a non-empty string")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("status page config title must be a non-empty string")
    if not isinstance(groups, list):
        raise ValueError("status page config groups must be a list")
    return payload


def build_status_page_groups(
    config: dict,
    monitor_list: dict[int, dict],
) -> list[dict]:
    monitors_by_name = {monitor["name"]: monitor for monitor in monitor_list.values()}
    groups: list[dict] = []
    for raw_group in config["groups"]:
        monitor_names = raw_group.get("monitor_names", [])
        if not isinstance(monitor_names, list):
            raise ValueError(f"status page group '{raw_group.get('name', '<unnamed>')}' monitor_names must be a list")
        group = {
            "name": raw_group["name"],
            "monitorList": [],
        }
        for monitor_name in monitor_names:
            if monitor_name not in monitors_by_name:
                raise ValueError(f"status page references unknown monitor '{monitor_name}'")
            group["monitorList"].append({"id": monitors_by_name[monitor_name]["id"]})
        groups.append(group)
    return groups


def ensure_status_page(client: UptimeKumaClient, config_path: Path) -> None:
    desired = load_status_page_config(config_path)
    slug = desired["slug"]
    title = desired["title"]
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
    save_config = {
        **current,
        "slug": slug,
        "title": title,
        "description": desired.get("description", ""),
        "theme": desired.get("theme", current.get("theme", "dark")),
        "showTags": bool(desired.get("showTags", False)),
        "customCSS": desired.get("customCSS", ""),
        "footerText": desired.get("footerText", ""),
        "showPoweredBy": bool(desired.get("showPoweredBy", True)),
        "showOnlyLastHeartbeat": bool(desired.get("showOnlyLastHeartbeat", False)),
        "showCertificateExpiry": bool(desired.get("showCertificateExpiry", False)),
        "autoRefreshInterval": int(desired.get("autoRefreshInterval", 300)),
        "domainNameList": desired.get("domainNameList", []),
        "rssTitle": desired.get("rssTitle"),
        "analyticsId": desired.get("analyticsId"),
        "analyticsScriptUrl": desired.get("analyticsScriptUrl"),
        "analyticsType": desired.get("analyticsType"),
    }
    groups = build_status_page_groups(desired, monitor_list)
    result = client.save_status_page(slug, save_config, groups, "")
    if not result.get("ok"):
        raise RuntimeError(result.get("msg", f"Unable to save status page '{slug}'"))
    print(f"{action}: {slug}")


def find_maintenance_by_title(client: UptimeKumaClient, title: str) -> dict | None:
    maintenance_list = client.get_maintenance_list()
    for maintenance in maintenance_list.values():
        if maintenance.get("title") == title:
            return maintenance
    return None


def upsert_status_page_maintenance(
    client: UptimeKumaClient,
    *,
    title: str,
    description: str,
    start_at: str,
    end_at: str,
    status_page_slug: str,
    monitor_names: list[str],
) -> dict:
    status_page = client.get_status_page(status_page_slug)
    monitor_list = client.get_monitor_list()
    monitors_by_name = {monitor["name"]: monitor for monitor in monitor_list.values()}
    monitors = []
    for monitor_name in monitor_names:
        monitor = monitors_by_name.get(monitor_name)
        if monitor is not None:
            monitors.append({"id": monitor["id"]})

    payload = {
        "title": title,
        "description": description,
        "strategy": "single",
        "intervalDay": 1,
        "active": True,
        "dateRange": [start_at, end_at],
        "timeRange": [{"hours": 0, "minutes": 0}, {"hours": 0, "minutes": 0}],
        "weekdays": [],
        "daysOfMonth": [],
        "cron": "",
        "durationMinutes": 0,
        "timezoneOption": "UTC",
    }

    existing = find_maintenance_by_title(client, title)
    if existing is None:
        result = client.add_maintenance(payload)
        action = "created"
    else:
        result = client.edit_maintenance({"id": existing["id"], **payload})
        action = "updated"
    if not result.get("ok"):
        raise RuntimeError(result.get("msg", f"Unable to {action} maintenance '{title}'"))

    maintenance_id = int(result["maintenanceID"])
    monitor_result = client.add_monitor_maintenance(maintenance_id, monitors)
    if not monitor_result.get("ok"):
        raise RuntimeError(monitor_result.get("msg", f"Unable to bind monitors for maintenance '{title}'"))
    status_page_result = client.add_maintenance_status_page(maintenance_id, [{"id": status_page["id"]}])
    if not status_page_result.get("ok"):
        raise RuntimeError(
            status_page_result.get("msg", f"Unable to bind status page for maintenance '{title}'")
        )
    return {"action": action, "maintenance_id": maintenance_id}


def delete_status_page_maintenance(client: UptimeKumaClient, *, title: str) -> dict:
    existing = find_maintenance_by_title(client, title)
    if existing is None:
        return {"action": "noop"}
    result = client.delete_maintenance(int(existing["id"]))
    if not result.get("ok"):
        raise RuntimeError(result.get("msg", f"Unable to delete maintenance '{title}'"))
    return {"action": "deleted", "maintenance_id": int(existing["id"])}


def command_bootstrap(args) -> int:
    auth_file, auth = resolve_auth(args)
    base_url = auth.get("base_url")
    if not base_url:
        raise RuntimeError("--base-url is required the first time you run bootstrap")

    client = UptimeKumaClient(base_url=base_url, verify_ssl=not args.insecure)
    try:
        if client.database_setup_required():
            client.configure_sqlite_database()
            time.sleep(2)

        client.wait_for_socket()
        auth = ensure_logged_in(client, auth, args.username, args.password)
        set_primary_base_url(client, args.primary_base_url or base_url)
        save_json(auth_file, auth)
        print(f"saved auth: {auth_file}")
        if args.seed_file:
            ensure_monitors(client, Path(args.seed_file).expanduser())
    finally:
        client.disconnect()
    return 0


def command_ensure_monitors(args) -> int:
    auth_file, auth = resolve_auth(args)
    base_url = auth.get("base_url")
    if not base_url:
        raise RuntimeError("No base URL found in auth file; run bootstrap first")

    client = UptimeKumaClient(base_url=base_url, verify_ssl=not args.insecure)
    try:
        client.connect()
        auth = ensure_logged_in(client, auth, args.username, args.password)
        save_json(auth_file, auth)
        ensure_monitors(client, Path(args.seed_file).expanduser())
    finally:
        client.disconnect()
    return 0


def command_list_monitors(args) -> int:
    auth_file, auth = resolve_auth(args)
    base_url = auth.get("base_url")
    if not base_url:
        raise RuntimeError("No base URL found in auth file; run bootstrap first")

    client = UptimeKumaClient(base_url=base_url, verify_ssl=not args.insecure)
    try:
        client.connect()
        auth = ensure_logged_in(client, auth, args.username, args.password)
        save_json(auth_file, auth)
        monitor_list = client.get_monitor_list()
        for monitor in sorted(monitor_list.values(), key=lambda item: item["name"].lower()):
            print(f"{monitor['id']}\t{monitor['type']}\t{monitor['name']}")
    finally:
        client.disconnect()
    return 0


def command_ensure_status_page(args) -> int:
    auth_file, auth = resolve_auth(args)
    base_url = auth.get("base_url")
    if not base_url:
        raise RuntimeError("No base URL found in auth file; run bootstrap first")

    client = UptimeKumaClient(base_url=base_url, verify_ssl=not args.insecure)
    try:
        client.connect()
        auth = ensure_logged_in(client, auth, args.username, args.password)
        save_json(auth_file, auth)
        ensure_status_page(client, Path(args.status_page_file).expanduser())
    finally:
        client.disconnect()
    return 0


def command_list_maintenances(args) -> int:
    auth_file, auth = resolve_auth(args)
    base_url = auth.get("base_url")
    if not base_url:
        raise RuntimeError("No base URL found in auth file; run bootstrap first")

    client = UptimeKumaClient(base_url=base_url, verify_ssl=not args.insecure)
    try:
        client.connect()
        auth = ensure_logged_in(client, auth, args.username, args.password)
        save_json(auth_file, auth)
        maintenance_list = client.get_maintenance_list()
        for maintenance in sorted(maintenance_list.values(), key=lambda item: item["title"].lower()):
            print(f"{maintenance['id']}\t{maintenance['title']}")
    finally:
        client.disconnect()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Uptime Kuma from the repo")
    parser.set_defaults(func=None)

    subparsers = parser.add_subparsers(dest="command")

    for name in ("bootstrap", "ensure-monitors", "list-monitors", "ensure-status-page", "list-maintenances"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE))
        subparser.add_argument("--base-url")
        subparser.add_argument("--username")
        subparser.add_argument("--password")
        subparser.add_argument("--insecure", action="store_true")

    bootstrap = subparsers.choices["bootstrap"]
    bootstrap.add_argument("--primary-base-url")
    bootstrap.add_argument("--seed-file", default=str(DEFAULT_MONITORS_FILE))
    bootstrap.set_defaults(func=command_bootstrap)

    ensure_monitors_parser = subparsers.choices["ensure-monitors"]
    ensure_monitors_parser.add_argument("--seed-file", default=str(DEFAULT_MONITORS_FILE))
    ensure_monitors_parser.set_defaults(func=command_ensure_monitors)

    list_monitors = subparsers.choices["list-monitors"]
    list_monitors.set_defaults(func=command_list_monitors)

    ensure_status_page_parser = subparsers.choices["ensure-status-page"]
    ensure_status_page_parser.add_argument("--status-page-file", default=str(DEFAULT_STATUS_PAGE_FILE))
    ensure_status_page_parser.set_defaults(func=command_ensure_status_page)

    list_maintenances = subparsers.choices["list-maintenances"]
    list_maintenances.set_defaults(func=command_list_maintenances)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.func is None:
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("Uptime Kuma", exc, exit_code=1)


if __name__ == "__main__":
    raise SystemExit(main())
