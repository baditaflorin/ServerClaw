#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

import requests
import urllib3

from controller_automation_toolkit import emit_cli_error, load_json


DEFAULT_AUTH_FILE = Path(
    "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/portainer/admin-auth.json"
)


class PortainerClient:
    def __init__(self, auth: dict):
        self.base_url = auth["base_url"].rstrip("/")
        self.username = auth["username"]
        self.password = auth["password"]
        self.endpoint_id = str(auth["endpoint_id"])
        self.verify_ssl = bool(auth.get("verify_ssl", True))
        self.session = requests.Session()
        self.jwt = ""
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def login(self) -> None:
        response = self.session.post(
            f"{self.base_url}/api/auth",
            json={"username": self.username, "password": self.password},
            timeout=20,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        payload = response.json()
        self.jwt = payload["jwt"]
        self.session.cookies.clear()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.jwt}",
                "Referer": self.base_url,
            }
        )

    def list_containers(self, *, all_containers: bool = True) -> list[dict]:
        response = self.session.get(
            f"{self.base_url}/api/endpoints/{self.endpoint_id}/docker/containers/json",
            params={"all": int(all_containers)},
            timeout=20,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        return response.json()

    def list_endpoints(self) -> list[dict]:
        response = self.session.get(
            f"{self.base_url}/api/endpoints",
            timeout=20,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        return response.json()

    def find_container(self, query: str) -> dict:
        query = query.strip()
        containers = self.list_containers(all_containers=True)
        exact_name = None
        prefix_id = None
        for container in containers:
            container_id = container["Id"]
            names = [name.lstrip("/") for name in container.get("Names", [])]
            if query == container_id:
                return container
            if any(query == name for name in names):
                exact_name = container
            if container_id.startswith(query):
                prefix_id = container
        if exact_name:
            return exact_name
        if prefix_id:
            return prefix_id
        raise RuntimeError(f"Container not found: {query}")

    def resolve_container_id(self, query: str) -> str:
        return self.find_container(query)["Id"]

    def container_logs(self, container: str, tail: int) -> str:
        container_id = self.resolve_container_id(container)
        response = self.session.get(
            f"{self.base_url}/api/endpoints/{self.endpoint_id}/docker/containers/{container_id}/logs",
            params={"stdout": 1, "stderr": 1, "tail": tail},
            timeout=30,
            verify=self.verify_ssl,
        )
        response.raise_for_status()
        return decode_docker_log_stream(response.content)

    def restart_container(self, container: str) -> None:
        target = self.find_container(container)
        target_names = [name.lstrip("/") for name in target.get("Names", [])]
        try:
            response = self.session.post(
                f"{self.base_url}/api/endpoints/{self.endpoint_id}/docker/containers/{target['Id']}/restart",
                timeout=20,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
        except requests.ConnectionError:
            if self.base_url and self.endpoint_id and "portainer" in target_names:
                return
            raise

    def whoami(self) -> dict:
        endpoints = self.list_endpoints()
        return {
            "base_url": self.base_url,
            "username": self.username,
            "endpoint_id": self.endpoint_id,
            "endpoint_count": len(endpoints),
            "login_verified": True,
        }


def decode_docker_log_stream(payload: bytes) -> str:
    if len(payload) < 8:
        return payload.decode("utf-8", errors="replace")

    decoded_chunks: list[str] = []
    cursor = 0
    demuxed = False
    while cursor + 8 <= len(payload):
        stream_type = payload[cursor]
        if stream_type not in (0, 1, 2):
            break
        frame_size = int.from_bytes(payload[cursor + 4 : cursor + 8], byteorder="big")
        frame_end = cursor + 8 + frame_size
        if frame_end > len(payload):
            break
        decoded_chunks.append(payload[cursor + 8 : frame_end].decode("utf-8", errors="replace"))
        cursor = frame_end
        demuxed = True
    if demuxed and cursor == len(payload):
        return "".join(decoded_chunks)
    return payload.decode("utf-8", errors="replace")


def load_auth(path: str) -> dict:
    return load_json(Path(path).expanduser())


def command_whoami(args) -> int:
    client = PortainerClient(load_auth(args.auth_file))
    client.login()
    print(json.dumps(client.whoami(), indent=2, sort_keys=True))
    return 0


def command_list_containers(args) -> int:
    client = PortainerClient(load_auth(args.auth_file))
    client.login()
    containers = client.list_containers(all_containers=args.all)
    for container in containers:
        names = ",".join(name.lstrip("/") for name in container.get("Names", []))
        print(f"{container['Id'][:12]}\t{container.get('State', '')}\t{container.get('Status', '')}\t{names}")
    return 0


def command_container_logs(args) -> int:
    client = PortainerClient(load_auth(args.auth_file))
    client.login()
    print(client.container_logs(args.container, args.tail), end="")
    return 0


def command_restart_container(args) -> int:
    client = PortainerClient(load_auth(args.auth_file))
    client.login()
    client.restart_container(args.container)
    print(f"restarted: {args.container}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed Portainer API actions.")
    parser.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE), help="Path to the Portainer auth JSON file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    whoami_parser = subparsers.add_parser("whoami", help="Show the configured Portainer auth target.")
    whoami_parser.set_defaults(func=command_whoami)

    list_parser = subparsers.add_parser("list-containers", help="List Portainer-managed Docker containers.")
    list_parser.add_argument("--all", action="store_true", help="Include stopped containers.")
    list_parser.set_defaults(func=command_list_containers)

    logs_parser = subparsers.add_parser("container-logs", help="Read logs for a named container.")
    logs_parser.add_argument("--container", required=True, help="Container name, ID, or ID prefix.")
    logs_parser.add_argument("--tail", type=int, default=100, help="Number of log lines to request.")
    logs_parser.set_defaults(func=command_container_logs)

    restart_parser = subparsers.add_parser("restart-container", help="Restart a named container.")
    restart_parser.add_argument("--container", required=True, help="Container name, ID, or ID prefix.")
    restart_parser.set_defaults(func=command_restart_container)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, KeyError, RuntimeError, requests.RequestException, ValueError) as exc:
        return emit_cli_error("Portainer", exc)


if __name__ == "__main__":
    sys.exit(main())
