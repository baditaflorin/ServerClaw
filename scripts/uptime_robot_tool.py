#!/usr/bin/env python3

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, resolve_repo_local_path


DEFAULT_API_KEY_FILE = repo_path(".local", "uptime-robot", "api-key.txt")
DEFAULT_CONFIG_FILE = repo_path("config", "uptime-robot", "public-status-monitoring.json")
DEFAULT_WEBHOOK_FILE = repo_path(".local", "mattermost", "uptime-robot-webhook.txt")
CONTROLLER_SECRETS_PATH = repo_path("config", "controller-local-secrets.json")
API_BASE_URL = "https://api.uptimerobot.com/v2"


def read_secret_value(path: Path) -> str:
    value = path.expanduser().read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"secret file is empty: {path}")
    return value


def load_controller_secret_paths() -> dict[str, Path]:
    manifest = load_json(CONTROLLER_SECRETS_PATH)
    secrets = manifest.get("secrets", {})
    result: dict[str, Path] = {}
    for secret_id, secret in secrets.items():
        if isinstance(secret, dict) and secret.get("kind") == "file" and secret.get("path"):
            result[secret_id] = resolve_repo_local_path(secret["path"], repo_root=REPO_ROOT)
    return result


class UptimeRobotClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def post(self, method: str, **payload: Any) -> dict[str, Any]:
        body = {
            "api_key": self.api_key,
            "format": "json",
            **{key: value for key, value in payload.items() if value is not None},
        }
        encoded = urllib.parse.urlencode(body).encode("utf-8")
        request = urllib.request.Request(
            f"{API_BASE_URL}/{method}",
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        if data.get("stat") != "ok":
            raise RuntimeError(data.get("error", {}).get("message", f"Uptime Robot {method} failed"))
        return data

    def get_alert_contacts(self) -> list[dict[str, Any]]:
        payload = self.post("getAlertContacts")
        return payload.get("alert_contacts", [])

    @staticmethod
    def _extract_id(payload: dict[str, Any], *keys: str) -> int:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict) and "id" in value:
                return int(value["id"])
        raise RuntimeError(f"Unable to extract id from Uptime Robot response keys {keys}")

    def new_alert_contact(self, *, type_id: int, friendly_name: str, value: str) -> int:
        payload = self.post(
            "newAlertContact",
            type=type_id,
            friendly_name=friendly_name,
            value=value,
        )
        return self._extract_id(payload, "alertcontact", "alert_contact")

    def edit_alert_contact(self, *, contact_id: int, type_id: int, friendly_name: str, value: str) -> int:
        payload = self.post(
            "editAlertContact",
            id=contact_id,
            type=type_id,
            friendly_name=friendly_name,
            value=value,
        )
        return self._extract_id(payload, "alertcontact", "alert_contact")

    def get_monitors(self) -> list[dict[str, Any]]:
        payload = self.post("getMonitors")
        return payload.get("monitors", [])

    def new_monitor(self, monitor: dict[str, Any]) -> int:
        payload = self.post("newMonitor", **monitor)
        return self._extract_id(payload, "monitor")

    def edit_monitor(self, monitor: dict[str, Any]) -> int:
        payload = self.post("editMonitor", **monitor)
        return self._extract_id(payload, "monitor")


def load_api_key(path: str) -> str:
    return read_secret_value(Path(path))


def resolve_contact_value(raw_contact: dict[str, Any], secret_paths: dict[str, Path]) -> str:
    if "value" in raw_contact:
        value = str(raw_contact["value"]).strip()
        if not value:
            raise ValueError(f"alert contact '{raw_contact.get('friendly_name', '<unnamed>')}' has an empty value")
        return value
    secret_id = raw_contact.get("value_secret_id")
    if not isinstance(secret_id, str) or not secret_id:
        raise ValueError(
            f"alert contact '{raw_contact.get('friendly_name', '<unnamed>')}' must define value or value_secret_id"
        )
    if secret_id not in secret_paths:
        raise ValueError(f"unknown controller-local secret id: {secret_id}")
    return read_secret_value(secret_paths[secret_id])


def normalize_alert_contact(raw_contact: dict[str, Any], secret_paths: dict[str, Path]) -> dict[str, Any]:
    friendly_name = str(raw_contact.get("friendly_name", "")).strip()
    if not friendly_name:
        raise ValueError("alert contact friendly_name must be a non-empty string")
    type_id = raw_contact.get("type")
    if not isinstance(type_id, int):
        raise ValueError(f"alert contact '{friendly_name}' type must be an integer")
    return {
        "friendly_name": friendly_name,
        "type": type_id,
        "value": resolve_contact_value(raw_contact, secret_paths),
    }


def alert_contact_spec(contact_id: int, *, threshold: int = 0, recurrence: int = 0) -> str:
    return f"{contact_id}_{threshold}_{recurrence}"


def ensure_alert_contacts(
    client: UptimeRobotClient, config: dict[str, Any], secret_paths: dict[str, Path]
) -> dict[str, int]:
    existing_by_name = {item["friendly_name"]: item for item in client.get_alert_contacts()}
    contact_ids: dict[str, int] = {}

    for raw_contact in config.get("alert_contacts", []):
        desired = normalize_alert_contact(raw_contact, secret_paths)
        existing = existing_by_name.get(desired["friendly_name"])
        if existing is None:
            contact_id = client.new_alert_contact(
                type_id=desired["type"],
                friendly_name=desired["friendly_name"],
                value=desired["value"],
            )
            print(f"created alert contact: {desired['friendly_name']}")
        else:
            contact_id = client.edit_alert_contact(
                contact_id=int(existing["id"]),
                type_id=desired["type"],
                friendly_name=desired["friendly_name"],
                value=desired["value"],
            )
            print(f"updated alert contact: {desired['friendly_name']}")
        contact_ids[desired["friendly_name"]] = contact_id

    return contact_ids


def normalize_monitor(raw_monitor: dict[str, Any], contact_ids: dict[str, int]) -> dict[str, Any]:
    friendly_name = str(raw_monitor.get("friendly_name", "")).strip()
    if not friendly_name:
        raise ValueError("monitor friendly_name must be a non-empty string")

    type_id = raw_monitor.get("type")
    if not isinstance(type_id, int):
        raise ValueError(f"monitor '{friendly_name}' type must be an integer")

    url = str(raw_monitor.get("url", "")).strip()
    if not url:
        raise ValueError(f"monitor '{friendly_name}' url must be a non-empty string")

    payload: dict[str, Any] = {
        "friendly_name": friendly_name,
        "type": type_id,
        "url": url,
    }

    interval = raw_monitor.get("interval")
    if interval is not None:
        if not isinstance(interval, int):
            raise ValueError(f"monitor '{friendly_name}' interval must be an integer")
        payload["interval"] = interval

    contact_names = raw_monitor.get("alert_contacts", [])
    if not isinstance(contact_names, list):
        raise ValueError(f"monitor '{friendly_name}' alert_contacts must be a list")
    if contact_names:
        specs = []
        for name in contact_names:
            if name not in contact_ids:
                raise ValueError(f"monitor '{friendly_name}' references unknown alert contact '{name}'")
            specs.append(alert_contact_spec(contact_ids[name]))
        payload["alert_contacts"] = "-".join(specs)

    return payload


def ensure_monitors(client: UptimeRobotClient, config: dict[str, Any], contact_ids: dict[str, int]) -> None:
    existing_by_name = {item["friendly_name"]: item for item in client.get_monitors()}

    for raw_monitor in config.get("monitors", []):
        desired = normalize_monitor(raw_monitor, contact_ids)
        existing = existing_by_name.get(desired["friendly_name"])
        if existing is None:
            client.new_monitor(desired)
            print(f"created monitor: {desired['friendly_name']}")
        else:
            client.edit_monitor({"id": int(existing["id"]), **desired})
            print(f"updated monitor: {desired['friendly_name']}")


def command_ensure(args: argparse.Namespace) -> int:
    config = load_json(Path(args.config_file))
    secret_paths = load_controller_secret_paths()
    client = UptimeRobotClient(load_api_key(args.api_key_file))
    contact_ids = ensure_alert_contacts(client, config, secret_paths)
    ensure_monitors(client, config, contact_ids)
    return 0


def command_list_monitors(args: argparse.Namespace) -> int:
    client = UptimeRobotClient(load_api_key(args.api_key_file))
    monitors = client.get_monitors()
    for monitor in sorted(monitors, key=lambda item: item["friendly_name"].lower()):
        print(f"{monitor['id']}\t{monitor['friendly_name']}\t{monitor['url']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Uptime Robot public status monitoring from the repo.")
    parser.set_defaults(func=None)
    subparsers = parser.add_subparsers(dest="command")

    ensure = subparsers.add_parser("ensure")
    ensure.add_argument("--api-key-file", default=str(DEFAULT_API_KEY_FILE))
    ensure.add_argument("--config-file", default=str(DEFAULT_CONFIG_FILE))
    ensure.set_defaults(func=command_ensure)

    list_monitors = subparsers.add_parser("list-monitors")
    list_monitors.add_argument("--api-key-file", default=str(DEFAULT_API_KEY_FILE))
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
    except Exception as exc:
        return emit_cli_error("Uptime Robot", exc, exit_code=1)


if __name__ == "__main__":
    raise SystemExit(main())
