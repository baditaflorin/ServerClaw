#!/usr/bin/env python3

from __future__ import annotations

import atexit
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json


DEFAULT_AUTH_FILE = Path(
    "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/coolify/admin-auth.json"
)
DEFAULT_BOOTSTRAP_KEY = Path(
    "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519"
)


class SSHTunnel:
    def __init__(
        self,
        *,
        ssh_host: str,
        ssh_user: str,
        ssh_key_file: Path,
        target_host: str,
        target_port: int,
        proxy_jump_host: str = "",
    ) -> None:
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key_file = ssh_key_file
        self.target_host = target_host
        self.target_port = target_port
        self.proxy_jump_host = proxy_jump_host.strip()
        self.local_port = self._reserve_local_port()
        self.process: subprocess.Popen[str] | None = None

    @staticmethod
    def _reserve_local_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def start(self) -> None:
        if self.process is not None:
            return
        command = [
            "ssh",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=yes",
            "-i",
            str(self.ssh_key_file),
        ]
        if self.proxy_jump_host:
            proxy_command = (
                f"ssh -i {self.ssh_key_file} -o IdentitiesOnly=yes -o BatchMode=yes "
                f"-o ConnectTimeout=30 -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null {self.ssh_user}@{self.proxy_jump_host} -W %h:%p"
            )
            command.extend(
                [
                    "-o",
                    f"ProxyCommand={proxy_command}",
                ]
            )
        command.extend(
            [
                "-N",
                "-L",
                f"127.0.0.1:{self.local_port}:127.0.0.1:{self.target_port}",
                f"{self.ssh_user}@{self.ssh_host}",
            ]
        )
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Failed to start SSH tunnel to {self.target_host}:{self.target_port} via {self.ssh_user}@{self.ssh_host}"
                )
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                if sock.connect_ex(("127.0.0.1", self.local_port)) == 0:
                    atexit.register(self.stop)
                    return
            time.sleep(0.1)
        self.stop()
        raise RuntimeError(
            f"Timed out waiting for SSH tunnel to {self.target_host}:{self.target_port} via {self.ssh_user}@{self.ssh_host}"
        )

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None


class CoolifyClient:
    def __init__(self, auth: dict[str, Any]) -> None:
        self.auth = auth
        self.controller_url = str(auth["controller_url"]).rstrip("/")
        self.private_url = str(auth.get("private_url", "")).rstrip("/")
        self.public_url = str(auth.get("public_url", "")).rstrip("/")
        self.apps_public_url = str(auth.get("apps_public_url", "")).rstrip("/")
        self.api_token = str(auth["api_token"]).strip()
        self.verify_ssl = bool(auth.get("verify_ssl", False))
        self.tunnel_host = str(auth.get("ssh_tunnel_host", "")).strip()
        self.tunnel_user = str(auth.get("ssh_tunnel_user", "ops")).strip() or "ops"
        self.tunnel: SSHTunnel | None = None
        self.bootstrap_key_file = Path(
            os.environ.get("BOOTSTRAP_KEY") or os.environ.get("LV3_BOOTSTRAP_KEY") or str(DEFAULT_BOOTSTRAP_KEY)
        ).expanduser()

    def _controller_base_url(self) -> str:
        if self.tunnel_host and self.private_url:
            return self._ensure_tunnel()
        return self.controller_url

    def _ensure_tunnel(self) -> str:
        if self.tunnel is None:
            target_url = self.private_url or self.controller_url
            parsed = urllib.parse.urlparse(target_url)
            target_host = parsed.hostname
            target_port = parsed.port
            if not target_host or not target_port:
                raise RuntimeError(f"Coolify tunnel target is missing a host or port: {target_url}")
            if not self.bootstrap_key_file.exists():
                raise RuntimeError(f"Coolify SSH tunnel key does not exist: {self.bootstrap_key_file}")
            self.tunnel = SSHTunnel(
                ssh_host=target_host,
                ssh_user=self.tunnel_user,
                ssh_key_file=self.bootstrap_key_file,
                target_host=target_host,
                target_port=target_port,
                proxy_jump_host=self.tunnel_host,
            )
            self.tunnel.start()
        return f"http://127.0.0.1:{self.tunnel.local_port}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
        base_url: str | None = None,
        parse_json: bool = True,
    ) -> Any:
        url = (base_url or self._controller_base_url()).rstrip("/") + path
        if query:
            encoded = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
            if encoded:
                url = f"{url}?{encoded}"
        data = None
        headers = {"Authorization": f"Bearer {self.api_token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        context = None
        if not self.verify_ssl and url.startswith("https://"):
            import ssl

            context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(request, timeout=30, context=context) as response:
                body = response.read().decode("utf-8")
                if response.status not in expected:
                    raise RuntimeError(f"{method} {path} returned unexpected status {response.status}: {body}")
                if not body:
                    return None
                if not parse_json:
                    return body
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc

    def version(self) -> dict[str, Any]:
        response = self._request("GET", "/api/v1/version", parse_json=False)
        return {"version": str(response).strip()}

    def current_team(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/teams/current")

    def servers(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/servers")

    def projects(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/projects")

    def project(self, project_uuid: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{project_uuid}")

    def applications(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/applications")

    def create_project(self, name: str, description: str | None = None) -> str:
        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        response = self._request("POST", "/api/v1/projects", payload=payload, expected=(201,))
        return str(response["uuid"])

    def create_environment(self, project_uuid: str, name: str) -> str:
        response = self._request(
            "POST",
            f"/api/v1/projects/{project_uuid}/environments",
            payload={"name": name},
            expected=(201,),
        )
        return str(response["uuid"])

    def create_public_application(self, payload: dict[str, Any]) -> str:
        response = self._request("POST", "/api/v1/applications/public", payload=payload, expected=(201,))
        return str(response["uuid"])

    def update_application(self, application_uuid: str, payload: dict[str, Any]) -> None:
        self._request("PATCH", f"/api/v1/applications/{application_uuid}", payload=payload, expected=(200, 201))

    def deploy_application(self, application_uuid: str, *, force: bool = False) -> str:
        response = self._request(
            "POST",
            "/api/v1/deploy",
            query={"uuid": application_uuid, "force": str(force).lower()},
            expected=(200,),
        )
        deployments = response.get("deployments", [])
        if not deployments:
            raise RuntimeError(f"Coolify did not return a deployment UUID for application {application_uuid}")
        deployment_uuid = deployments[0].get("deployment_uuid")
        if not deployment_uuid:
            raise RuntimeError(f"Coolify did not queue a deployment for application {application_uuid}: {response}")
        return str(deployment_uuid)

    def deployment(self, deployment_uuid: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/deployments/{deployment_uuid}")

    def ensure_project(self, name: str, description: str | None = None) -> dict[str, Any]:
        for project in self.projects():
            if project.get("name") == name:
                return project
        project_uuid = self.create_project(name, description=description)
        return self.project(project_uuid)

    def ensure_environment(self, project_uuid: str, environment_name: str) -> dict[str, Any]:
        details = self.project(project_uuid)
        for environment in details.get("environments", []):
            if environment.get("name") == environment_name:
                return environment
        environment_uuid = self.create_environment(project_uuid, environment_name)
        details = self.project(project_uuid)
        for environment in details.get("environments", []):
            if environment.get("uuid") == environment_uuid:
                return environment
        raise RuntimeError(f"Unable to discover environment {environment_name!r} after creation")

    def resolve_server(self, server_uuid: str | None) -> dict[str, Any]:
        if server_uuid:
            for server in self.servers():
                if server.get("uuid") == server_uuid:
                    return server
        auth_server_name = self.auth.get("server_name")
        for server in self.servers():
            if auth_server_name and server.get("name") == auth_server_name:
                return server
        raise RuntimeError("Unable to find the configured Coolify deployment server")

    def ensure_application(
        self,
        *,
        app_name: str,
        project_uuid: str,
        environment_name: str,
        server_uuid: str,
        destination_uuid: str,
        repo: str,
        branch: str,
        build_pack: str,
        ports_exposes: str,
        base_directory: str | None,
        domains: list[str],
    ) -> dict[str, Any]:
        normalized_domains = ",".join(domain for domain in domains if domain)
        for application in self.applications():
            if application.get("name") == app_name:
                payload: dict[str, Any] = {
                    "name": app_name,
                    "git_repository": repo,
                    "git_branch": branch,
                    "build_pack": build_pack,
                    "ports_exposes": ports_exposes,
                    "domains": normalized_domains,
                }
                if base_directory:
                    payload["base_directory"] = base_directory
                self.update_application(str(application["uuid"]), payload)
                application = dict(application)
                application.update(payload)
                return application

        payload = {
            "name": app_name,
            "project_uuid": project_uuid,
            "server_uuid": server_uuid,
            "destination_uuid": destination_uuid,
            "environment_name": environment_name,
            "git_repository": repo,
            "git_branch": branch,
            "build_pack": build_pack,
            "ports_exposes": ports_exposes,
            "domains": normalized_domains,
            "autogenerate_domain": False,
        }
        if base_directory:
            payload["base_directory"] = base_directory
        application_uuid = self.create_public_application(payload)
        for application in self.applications():
            if application.get("uuid") == application_uuid:
                return application
        return {"uuid": application_uuid, **payload}


def load_auth(path: str) -> dict[str, Any]:
    return load_json(Path(path).expanduser())


def normalize_repository(repo: str) -> str:
    candidate = repo.strip()
    if candidate.startswith("git@github.com:"):
        candidate = candidate.split("git@github.com:", 1)[1]
    else:
        parsed = urllib.parse.urlparse(candidate)
        if parsed.scheme and parsed.netloc == "github.com":
            candidate = parsed.path.lstrip("/")
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    return candidate


def app_url_for_domain(domain: str) -> str:
    parsed = urllib.parse.urlparse(domain)
    if parsed.scheme and parsed.netloc:
        return domain
    return f"https://{domain.lstrip('/')}"


def wait_for_deployment(client: CoolifyClient, deployment_uuid: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        deployment = client.deployment(deployment_uuid)
        status = deployment.get("status")
        if status in {"finished", "failed", "cancelled-by-user"}:
            return deployment
        time.sleep(5)
    raise RuntimeError(f"Timed out waiting for deployment {deployment_uuid}")


def command_whoami(args: argparse.Namespace) -> int:
    client = CoolifyClient(load_auth(args.auth_file))
    team = client.current_team()
    version = client.version()
    server = client.resolve_server(client.auth.get("server_uuid"))
    payload = {
        "controller_url": client.controller_url,
        "public_url": client.public_url,
        "apps_public_url": client.apps_public_url,
        "team": team,
        "version": version,
        "server": server,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_list_applications(args: argparse.Namespace) -> int:
    client = CoolifyClient(load_auth(args.auth_file))
    applications = client.applications()
    for application in applications:
        name = application.get("name", "")
        uuid = application.get("uuid", "")
        repository = application.get("git_repository", "")
        branch = application.get("git_branch", "")
        domains = application.get("fqdn", "")
        print(f"{uuid}\t{name}\t{repository}\t{branch}\t{domains}")
    return 0


def command_deploy_repo(args: argparse.Namespace) -> int:
    auth = load_auth(args.auth_file)
    client = CoolifyClient(auth)
    normalized_repo = normalize_repository(args.repo)
    project = client.ensure_project(args.project, description="Repo-managed Coolify applications for ADR 0194.")
    environment = client.ensure_environment(str(project["uuid"]), args.environment)
    server = client.resolve_server(auth.get("server_uuid"))
    destination_uuid = str(auth.get("destination_uuid") or "")
    if not destination_uuid:
        resources = client._request("GET", f"/api/v1/servers/{server['uuid']}/resources")
        destinations = resources.get("destinations", []) if isinstance(resources, dict) else []
        if destinations:
            destination_uuid = str(destinations[0]["uuid"])
    if not destination_uuid:
        raise RuntimeError("Unable to determine the Coolify destination UUID")

    domains: list[str]
    if args.domain:
        domains = [args.domain]
    elif args.subdomain:
        domains = [f"http://{args.subdomain}.apps.lv3.org"]
    else:
        smoke_domains = auth.get("smoke_domains", [])
        if not isinstance(smoke_domains, list) or not smoke_domains:
            raise RuntimeError("No --domain or --subdomain provided, and auth file has no smoke_domains fallback")
        domains = [str(item) for item in smoke_domains]

    application = client.ensure_application(
        app_name=args.app_name,
        project_uuid=str(project["uuid"]),
        environment_name=str(environment["name"]),
        server_uuid=str(server["uuid"]),
        destination_uuid=destination_uuid,
        repo=normalized_repo,
        branch=args.branch,
        build_pack=args.build_pack,
        ports_exposes=args.ports,
        base_directory=args.base_directory,
        domains=domains,
    )
    deployment_uuid = client.deploy_application(str(application["uuid"]), force=args.force)
    result = {
      "application_uuid": str(application["uuid"]),
      "application_name": args.app_name,
      "deployment_uuid": deployment_uuid,
      "domains": domains,
      "project_uuid": str(project["uuid"]),
      "environment_uuid": str(environment["uuid"]),
      "server_uuid": str(server["uuid"]),
      "destination_uuid": destination_uuid,
    }
    if args.wait:
        deployment = wait_for_deployment(client, deployment_uuid, args.timeout)
        result["deployment"] = deployment
        result["status"] = deployment.get("status")
        if result["status"] != "finished":
            print(json.dumps(result, indent=2, sort_keys=True))
            raise RuntimeError(f"Deployment {deployment_uuid} finished with status {result['status']}")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed Coolify API actions.")
    parser.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE), help="Path to the Coolify auth JSON file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    whoami_parser = subparsers.add_parser("whoami", help="Show the configured Coolify auth target.")
    whoami_parser.set_defaults(func=command_whoami)

    apps_parser = subparsers.add_parser("list-applications", help="List Coolify-managed applications.")
    apps_parser.set_defaults(func=command_list_applications)

    deploy_parser = subparsers.add_parser("deploy-repo", help="Create or update one repo-backed Coolify application and deploy it.")
    deploy_parser.add_argument("--repo", required=True, help="Repository URL.")
    deploy_parser.add_argument("--branch", default="main", help="Repository branch.")
    deploy_parser.add_argument("--base-directory", help="Optional base directory inside the repository.")
    deploy_parser.add_argument("--app-name", default="repo-smoke", help="Coolify application name.")
    deploy_parser.add_argument("--project", default="LV3 Apps", help="Coolify project name.")
    deploy_parser.add_argument("--environment", default="production", help="Coolify environment name.")
    deploy_parser.add_argument("--domain", help="Full domain URL, for example http://apps.lv3.org.")
    deploy_parser.add_argument("--subdomain", help="Subdomain under apps.lv3.org, for example hello.")
    deploy_parser.add_argument("--build-pack", default="static", choices=["nixpacks", "static", "dockerfile", "dockercompose"])
    deploy_parser.add_argument("--ports", default="80", help="Comma-separated exposed ports.")
    deploy_parser.add_argument("--wait", action="store_true", help="Wait for the deployment result.")
    deploy_parser.add_argument("--timeout", type=int, default=900, help="Wait timeout in seconds.")
    deploy_parser.add_argument("--force", action="store_true", help="Force a rebuild without cache.")
    deploy_parser.set_defaults(func=command_deploy_repo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (KeyError, OSError, RuntimeError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return emit_cli_error("Coolify", exc)


if __name__ == "__main__":
    sys.exit(main())
