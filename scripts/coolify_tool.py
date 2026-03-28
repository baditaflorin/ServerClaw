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

    def private_keys(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/security/keys")

    def github_apps(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/github-apps")

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

    def create_private_deploy_key_application(self, payload: dict[str, Any]) -> str:
        response = self._request("POST", "/api/v1/applications/private-deploy-key", payload=payload, expected=(201,))
        return str(response["uuid"])

    def create_private_key(self, *, name: str, description: str, private_key: str) -> str:
        response = self._request(
            "POST",
            "/api/v1/security/keys",
            payload={"name": name, "description": description, "private_key": private_key},
            expected=(201,),
        )
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

    def ensure_private_key(self, *, name: str, description: str, private_key: str) -> dict[str, Any]:
        for entry in self.private_keys():
            if entry.get("name") == name:
                return entry
        private_key_uuid = self.create_private_key(name=name, description=description, private_key=private_key)
        for entry in self.private_keys():
            if entry.get("uuid") == private_key_uuid:
                return entry
        return {"uuid": private_key_uuid, "name": name, "description": description}

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
        source: str = "public",
        private_key_uuid: str | None = None,
        description: str | None = None,
        dockerfile_location: str | None = None,
        docker_compose_location: str | None = None,
        docker_compose_domains: list[dict[str, str]] | None = None,
        publish_directory: str | None = None,
    ) -> dict[str, Any]:
        normalized_domains = ",".join(domain for domain in domains if domain)
        compose_domains = docker_compose_domains or []

        def update_payload(*, include_private_key_uuid: bool) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "name": app_name,
                "git_repository": repo,
                "git_branch": branch,
                "build_pack": build_pack,
                "ports_exposes": ports_exposes,
            }
            if normalized_domains:
                payload["domains"] = normalized_domains
            if description:
                payload["description"] = description
            if base_directory:
                payload["base_directory"] = base_directory
            if include_private_key_uuid and private_key_uuid:
                payload["private_key_uuid"] = private_key_uuid
            if dockerfile_location:
                payload["dockerfile_location"] = dockerfile_location
            if docker_compose_location:
                payload["docker_compose_location"] = docker_compose_location
            if compose_domains:
                payload["docker_compose_domains"] = compose_domains
            if publish_directory:
                payload["publish_directory"] = publish_directory
            return payload

        for application in self.applications():
            if application.get("name") == app_name:
                payload = update_payload(include_private_key_uuid=False)
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
            "autogenerate_domain": False,
        }
        payload.update(update_payload(include_private_key_uuid=True))
        if source == "private-deploy-key":
            if not private_key_uuid:
                raise RuntimeError("private-deploy-key source requires a private_key_uuid")
            application_uuid = self.create_private_deploy_key_application(payload)
        else:
            application_uuid = self.create_public_application(payload)
        for application in self.applications():
            if application.get("uuid") == application_uuid:
                return application
        return {"uuid": application_uuid, **payload}


def load_auth(path: str) -> dict[str, Any]:
    return load_json(Path(path).expanduser())


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"Command failed: {command!r}: {detail}")
    return completed


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


def slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def resolve_source(requested_source: str, repo: str) -> str:
    if requested_source != "auto":
        return requested_source
    if repo.strip().startswith("git@"):
        return "private-deploy-key"
    return "public"


def github_repo_slug(repo: str, normalized_repo: str) -> str | None:
    candidate = repo.strip()
    if candidate.startswith("git@github.com:"):
        return normalize_repository(candidate)
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme and parsed.netloc == "github.com":
        return normalize_repository(candidate)
    if normalized_repo.count("/") == 1 and "://" not in normalized_repo and not normalized_repo.startswith("git@"):
        return normalized_repo
    return None


def default_deploy_key_name(normalized_repo: str) -> str:
    return f"coolify-{slugify(normalized_repo)}"


def default_deploy_key_path(normalized_repo: str) -> Path:
    return Path(
        "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/coolify/git-keys"
    ) / f"{slugify(normalized_repo)}.ed25519"


def ensure_local_keypair(*, key_path: Path, comment: str) -> tuple[Path, Path]:
    public_key_path = Path(f"{key_path}.pub")
    if key_path.exists() and public_key_path.exists():
        return key_path, public_key_path
    key_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            comment,
            "-f",
            str(key_path),
        ]
    )
    if not key_path.exists() or not public_key_path.exists():
        raise RuntimeError(f"Failed to create deploy keypair at {key_path}")
    return key_path, public_key_path


def github_deploy_keys(repo_slug: str) -> list[dict[str, Any]]:
    completed = run_command(["gh", "api", f"repos/{repo_slug}/keys"])
    return json.loads(completed.stdout)


def ensure_github_deploy_key(*, repo_slug: str, title: str, public_key_path: Path) -> dict[str, Any]:
    public_key = public_key_path.read_text(encoding="utf-8").strip()
    normalized_public_key = " ".join(public_key.split()[:2])
    for entry in github_deploy_keys(repo_slug):
        if entry.get("key", "").strip() == normalized_public_key:
            return entry
        if entry.get("title") == title:
            raise RuntimeError(f"GitHub deploy key title '{title}' already exists on {repo_slug} with different key material")
    run_command(
        [
            "gh",
            "repo",
            "deploy-key",
            "add",
            str(public_key_path),
            "--repo",
            repo_slug,
            "--title",
            title,
        ]
    )
    for entry in github_deploy_keys(repo_slug):
        if entry.get("key", "").strip() == normalized_public_key:
            return entry
    raise RuntimeError(f"Unable to confirm deploy key '{title}' on GitHub repository {repo_slug}")


def app_url_for_domain(domain: str) -> str:
    parsed = urllib.parse.urlparse(domain)
    if parsed.scheme and parsed.netloc:
        return domain
    return f"https://{domain.lstrip('/')}"


def normalize_repo_location(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate == "/":
        return candidate
    return f"/{candidate.lstrip('/')}"


def private_repo_url(repo: str, normalized_repo: str) -> str:
    candidate = repo.strip()
    if candidate.startswith("git@"):
        return candidate
    repo_slug = github_repo_slug(candidate, normalized_repo)
    if repo_slug:
        return f"git@github.com:{repo_slug}.git"
    raise RuntimeError(
        "private-deploy-key source requires an SSH-style repository URL or a GitHub repository path that can be converted into one"
    )


def parse_compose_domain_mapping(value: str) -> dict[str, str]:
    service_name, separator, raw_domain = value.partition("=")
    if not separator or not service_name.strip() or not raw_domain.strip():
        raise ValueError("--compose-domain entries must use SERVICE=DOMAIN")
    return {"name": service_name.strip(), "domain": app_url_for_domain(raw_domain.strip())}


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
    source = resolve_source(args.source, args.repo)
    base_directory = normalize_repo_location(args.base_directory)
    dockerfile_location = normalize_repo_location(args.dockerfile_location)
    docker_compose_location = normalize_repo_location(args.docker_compose_location)
    compose_domains = [parse_compose_domain_mapping(item) for item in (args.compose_domain or [])]
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
    domains_for_api: list[str]
    if args.build_pack == "dockercompose":
        if not compose_domains and (args.domain or args.subdomain or auth.get("smoke_domains")):
            raise RuntimeError(
                "dockercompose applications must use --compose-domain SERVICE=DOMAIN for public routing"
            )
        domains = [str(entry["domain"]) for entry in compose_domains]
        domains_for_api = []
    else:
        if args.domain:
            domains = [args.domain]
        elif args.subdomain:
            domains = [f"http://{args.subdomain}.apps.lv3.org"]
        else:
            smoke_domains = auth.get("smoke_domains", [])
            if not isinstance(smoke_domains, list) or not smoke_domains:
                raise RuntimeError("No --domain or --subdomain provided, and auth file has no smoke_domains fallback")
            domains = [str(item) for item in smoke_domains]
        domains_for_api = domains

    private_key_uuid = args.private_key_uuid
    repo_for_coolify = normalized_repo
    github_deploy_key: dict[str, Any] | None = None
    coolify_private_key: dict[str, Any] | None = None
    if source == "private-deploy-key":
        repo_for_coolify = private_repo_url(args.repo, normalized_repo)
        if not private_key_uuid:
            repo_slug = github_repo_slug(args.repo, normalized_repo)
            if not repo_slug:
                raise RuntimeError(
                    "Automatic deploy-key bootstrap currently requires a GitHub repository path or SSH URL; otherwise pass --private-key-uuid"
                )
            deploy_key_name = args.deploy_key_name or default_deploy_key_name(normalized_repo)
            deploy_key_path = Path(args.deploy_key_path).expanduser() if args.deploy_key_path else default_deploy_key_path(normalized_repo)
            private_key_path, public_key_path = ensure_local_keypair(
                key_path=deploy_key_path,
                comment=f"coolify:{repo_slug}",
            )
            github_deploy_key = ensure_github_deploy_key(
                repo_slug=repo_slug,
                title=deploy_key_name,
                public_key_path=public_key_path,
            )
            coolify_private_key = client.ensure_private_key(
                name=deploy_key_name,
                description=args.description or f"Deploy key for {repo_slug}",
                private_key=private_key_path.read_text(encoding="utf-8"),
            )
            private_key_uuid = str(coolify_private_key["uuid"])

    application = client.ensure_application(
        app_name=args.app_name,
        project_uuid=str(project["uuid"]),
        environment_name=str(environment["name"]),
        server_uuid=str(server["uuid"]),
        destination_uuid=destination_uuid,
        repo=repo_for_coolify,
        branch=args.branch,
        build_pack=args.build_pack,
        ports_exposes=args.ports,
        base_directory=base_directory,
        domains=domains_for_api,
        source=source,
        private_key_uuid=private_key_uuid,
        description=args.description,
        dockerfile_location=dockerfile_location,
        docker_compose_location=docker_compose_location,
        docker_compose_domains=compose_domains,
        publish_directory=args.publish_directory,
    )
    deployment_uuid = client.deploy_application(str(application["uuid"]), force=args.force)
    result = {
      "application_uuid": str(application["uuid"]),
      "application_name": args.app_name,
      "deployment_uuid": deployment_uuid,
      "domains": domains,
      "source": source,
      "repository": repo_for_coolify,
      "project_uuid": str(project["uuid"]),
      "environment_uuid": str(environment["uuid"]),
      "server_uuid": str(server["uuid"]),
      "destination_uuid": destination_uuid,
    }
    if compose_domains:
        result["compose_domains"] = compose_domains
    if github_deploy_key is not None:
        result["github_deploy_key"] = {
            "id": github_deploy_key.get("id"),
            "title": github_deploy_key.get("title"),
            "read_only": github_deploy_key.get("read_only"),
        }
    if coolify_private_key is not None:
        result["coolify_private_key"] = {
            "uuid": coolify_private_key.get("uuid"),
            "name": coolify_private_key.get("name"),
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
    deploy_parser.add_argument(
        "--source",
        default="auto",
        choices=["auto", "public", "private-deploy-key"],
        help="Repository source mode. 'auto' treats SSH URLs as private deploy-key repos and HTTPS URLs as public repos.",
    )
    deploy_parser.add_argument("--base-directory", help="Optional base directory inside the repository.")
    deploy_parser.add_argument("--app-name", default="repo-smoke", help="Coolify application name.")
    deploy_parser.add_argument("--project", default="LV3 Apps", help="Coolify project name.")
    deploy_parser.add_argument("--environment", default="production", help="Coolify environment name.")
    deploy_parser.add_argument("--domain", help="Full domain URL, for example http://apps.lv3.org.")
    deploy_parser.add_argument("--subdomain", help="Subdomain under apps.lv3.org, for example hello.")
    deploy_parser.add_argument("--build-pack", default="static", choices=["nixpacks", "static", "dockerfile", "dockercompose"])
    deploy_parser.add_argument("--ports", default="80", help="Comma-separated exposed ports.")
    deploy_parser.add_argument("--description", help="Optional Coolify application description.")
    deploy_parser.add_argument("--private-key-uuid", help="Existing Coolify private key UUID for private deploy-key applications.")
    deploy_parser.add_argument("--deploy-key-name", help="Deploy key label to reuse or create for GitHub and Coolify.")
    deploy_parser.add_argument("--deploy-key-path", help="Local SSH private key path used for deploy-key bootstrap.")
    deploy_parser.add_argument("--dockerfile-location", help="Repository-relative Dockerfile path for dockerfile build pack.")
    deploy_parser.add_argument("--docker-compose-location", help="Repository-relative compose file path for dockercompose build pack.")
    deploy_parser.add_argument(
        "--compose-domain",
        action="append",
        help="Map one Docker Compose service to one public domain using SERVICE=DOMAIN. Repeat for multiple services.",
    )
    deploy_parser.add_argument("--publish-directory", help="Static publish directory for static build pack deployments.")
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
