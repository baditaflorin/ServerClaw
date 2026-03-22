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

        @self.sio.on("monitorList")
        def on_monitor_list(data):
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Uptime Kuma from the repo")
    parser.set_defaults(func=None)

    subparsers = parser.add_subparsers(dest="command")

    for name in ("bootstrap", "ensure-monitors", "list-monitors"):
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
