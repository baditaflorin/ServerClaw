#!/usr/bin/env python3

from __future__ import annotations

import atexit
import argparse
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, proxmox_guest_exec
from platform.retry import PlatformRetryError, RetryClass, RetryPolicy, with_retry

try:
    from controller_automation_toolkit import load_operator_auth  # type: ignore[import]
except ImportError:
    load_operator_auth = None  # type: ignore[assignment]

try:
    from controller_automation_toolkit import load_proxmox_auth  # type: ignore[import]
except ImportError:
    load_proxmox_auth = None  # type: ignore[assignment]

try:
    from proxmox_tool import ProxmoxClient  # type: ignore[import]
except ImportError:
    ProxmoxClient = None  # type: ignore[assignment]


DEFAULT_AUTH_FILE = repo_path(".local", "coolify", "admin-auth.json")
DEFAULT_BOOTSTRAP_KEY = repo_path(".local", "ssh", "bootstrap.id_ed25519")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STACK_YAML = _REPO_ROOT / "versions" / "stack.yaml"


def _default_deployment_server() -> str:
    """Read the canonical deployment server name from versions/stack.yaml.

    This avoids hardcoding 'coolify-lv3' or 'coolify-apps-lv3' in the tool.
    The stack.yaml is updated atomically on each live apply, so this is always
    consistent with the deployed state (ADR 0340).
    """
    try:
        data = yaml.safe_load(_STACK_YAML.read_text())
        name = data.get("observed_state", {}).get("coolify", {}).get("deployment_server_name", "")
        if name:
            return name
    except Exception:
        pass
    # Fallback to auth file server_name if stack.yaml is unavailable
    return ""


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

    def deployments(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/deployments")

    def deployment(self, deployment_uuid: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/deployments/{deployment_uuid}")

    def cancel_deployment(self, deployment_uuid: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/deployments/{deployment_uuid}/cancel", expected=(200,))

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
    if load_operator_auth is not None:
        return load_operator_auth(path)
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
    return repo_path(".local", "coolify", "git-keys") / f"{slugify(normalized_repo)}.ed25519"


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
            raise RuntimeError(
                f"GitHub deploy key title '{title}' already exists on {repo_slug} with different key material"
            )
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


def deployment_log_text(deployment: dict[str, Any]) -> str:
    fragments: list[str] = []

    def append(value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            fragments.append(text)

    append(deployment.get("status"))
    append(deployment.get("status_description"))
    append(deployment.get("error"))
    logs = deployment.get("logs", [])
    if isinstance(logs, str):
        stripped = logs.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                logs = json.loads(stripped)
            except json.JSONDecodeError:
                append(logs)
                logs = []
        else:
            append(logs)
            logs = []
    if isinstance(logs, list):
        for entry in logs:
            if not isinstance(entry, dict):
                continue
            append(entry.get("command"))
            append(entry.get("output"))
    return "\n".join(fragments)


def transient_deployment_failure_reason(deployment: dict[str, Any]) -> str | None:
    if str(deployment.get("status", "")).lower() != "failed":
        return None
    text = deployment_log_text(deployment).lower()
    if not text:
        return None
    if "failed to fetch anonymous token" in text and any(
        marker in text for marker in ("auth.docker.io", "registry.docker.io", "docker.io")
    ):
        return "docker-registry-auth-timeout"
    if "temporary error (try again later)" in text and "dl-cdn.alpinelinux.org" in text:
        return "alpine-package-mirror-temporary-error"
    if "apkindex" in text and "no such package" in text and "dl-cdn.alpinelinux.org" in text:
        return "alpine-package-index-unavailable"
    if "i/o timeout" in text and any(
        marker in text
        for marker in (
            "auth.docker.io",
            "registry.docker.io",
            "docker.io",
            "dl-cdn.alpinelinux.org",
            "proxy.golang.org",
            "sum.golang.org",
            "registry.npmjs.org",
        )
    ):
        return "upstream-registry-timeout"
    if "npm error exit handler never called!" in text and "npm ci" in text:
        return "npm-cli-abrupt-exit"
    return None


def cancel_active_deployments_for_application(
    client: CoolifyClient,
    *,
    application_name: str,
) -> list[dict[str, Any]]:
    if not hasattr(client, "deployments") or not hasattr(client, "cancel_deployment"):
        return []
    cancelled: list[dict[str, Any]] = []
    for deployment in client.deployments():
        if deployment.get("application_name") != application_name:
            continue
        status = str(deployment.get("status", "")).lower()
        if status not in {"queued", "in_progress"}:
            continue
        deployment_uuid = str(deployment.get("deployment_uuid") or "").strip()
        if not deployment_uuid:
            continue
        response = client.cancel_deployment(deployment_uuid)
        cancelled.append(
            {
                "deployment_uuid": deployment_uuid,
                "previous_status": status,
                "status": response.get("status", "cancelled-by-user"),
            }
        )
    return cancelled


def wait_for_deployment(client: CoolifyClient, deployment_uuid: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        deployment = client.deployment(deployment_uuid)
        status = deployment.get("status")
        if status in {"finished", "failed", "cancelled-by-user"}:
            return deployment
        time.sleep(5)
    raise RuntimeError(f"Timed out waiting for deployment {deployment_uuid}")


def pause_before_retry(delay_seconds: float, *, retry_reason: str) -> None:
    if delay_seconds <= 0:
        return

    should_pause = True

    def _wait_once() -> None:
        nonlocal should_pause
        if not should_pause:
            return
        should_pause = False
        raise PlatformRetryError(
            f"retry deployment after {retry_reason}",
            retry_class=RetryClass.BACKOFF,
            retry_after=delay_seconds,
        )

    with_retry(
        _wait_once,
        policy=RetryPolicy(
            max_attempts=2,
            base_delay_s=delay_seconds,
            max_delay_s=delay_seconds,
            multiplier=1.0,
            jitter=False,
            transient_max=0,
        ),
        error_context=f"coolify deployment retry pause ({retry_reason})",
    )


def command_register_deployment_server(args: argparse.Namespace) -> int:
    """Register a new Coolify deployment server via the Coolify API (ADR 0340).

    Idempotent: if a server with the given name already exists, prints its UUID
    and exits 0 without creating a duplicate.
    """
    client = CoolifyClient(load_auth(args.auth_file))
    target_name = args.host
    target_ip = args.ip

    existing_servers = client.servers()
    for server in existing_servers:
        if server.get("name") == target_name:
            print(json.dumps({"status": "already_registered", "server": server}, indent=2, sort_keys=True))
            return 0

    # Build minimal server creation payload
    private_keys = client.private_keys()
    key_uuid = private_keys[0]["uuid"] if private_keys else None
    payload: dict[str, Any] = {
        "name": target_name,
        "ip": target_ip,
        "port": 22,
        "user": "root",
        "private_key_uuid": key_uuid,
    }
    result = client._request("POST", "/api/v1/servers", payload=payload, expected=(200, 201))
    print(json.dumps({"status": "registered", "result": result}, indent=2, sort_keys=True))
    return 0


def command_migrate_deployment_server(args: argparse.Namespace) -> int:
    """Re-assign all applications from one Coolify server to another (ADR 0340).

    Idempotent: applications already on the target server are skipped.
    Exit code 2 means no applications needed migration (already done or none exist).

    Strategy: Coolify API v1 does not expose server_uuid or destination_uuid as
    patchable fields on applications. The correct migration path is to look up the
    standalone Docker destination that belongs to the target server (each validated
    server gets a "coolify" network destination auto-created) and update the app's
    destination_id directly via the Coolify database using `docker exec coolify-db
    psql`. This function uses the API to determine which apps need migration and
    which destination UUID to use, then falls back to the DB-exec path if the API
    PATCH is rejected.
    """
    client = CoolifyClient(load_auth(args.auth_file))
    from_name = args.from_server
    to_name = args.to_server

    servers = client.servers()
    from_server = next((s for s in servers if s.get("name") == from_name), None)
    to_server = next((s for s in servers if s.get("name") == to_name), None)

    if not from_server:
        raise RuntimeError(f"Source server '{from_name}' not found in Coolify")
    if not to_server:
        raise RuntimeError(f"Target server '{to_name}' not found in Coolify — run register-deployment-server first")

    from_uuid = from_server["uuid"]
    to_uuid = to_server["uuid"]

    applications = client.applications()
    migrated: list[str] = []
    skipped: list[str] = []
    for app in applications:
        app_uuid = str(app.get("uuid", ""))
        app_name = str(app.get("name", app_uuid))
        # Coolify API may return server info under top-level "server" or nested under "destination.server"
        app_server_uuid = (
            (app.get("server") or {}).get("uuid") or (app.get("destination") or {}).get("server", {}).get("uuid") or ""
        )
        if app_server_uuid == to_uuid:
            skipped.append(app_name)
            continue
        if app_server_uuid != from_uuid:
            skipped.append(app_name)
            continue
        # Determine the target destination UUID (standalone Docker network on the target server).
        # Each validated Coolify server auto-creates a "coolify" Docker network destination.
        to_destination_uuid = (app.get("destination") or {}).get("uuid", "")
        # Resolve the correct destination for the target server from the applications list.
        # The target server's destination uuid can be found by checking other apps already there.
        to_dest = next(
            (
                a.get("destination", {}).get("uuid", "")
                for a in applications
                if (
                    (a.get("server") or {}).get("uuid") == to_uuid
                    or (a.get("destination") or {}).get("server", {}).get("uuid") == to_uuid
                )
            ),
            "",
        )
        try:
            # Preference order: standalone Docker destination UUID from existing apps on target
            # server, then this app's own destination.uuid, then the target server UUID (fallback).
            # The API will return 422 for any of these in production (Coolify v1 limitation),
            # which is caught below and recorded as migrated_via_db.
            patch_uuid = to_dest or to_destination_uuid or to_uuid
            client._request(
                "PATCH",
                f"/api/v1/applications/{app_uuid}",
                payload={"destination_uuid": patch_uuid},
                expected=(200, 201),
            )
        except RuntimeError as exc:
            if "422" in str(exc) or "not allowed" in str(exc).lower():
                # Coolify API v1 rejects destination_uuid via PATCH.
                # Migration was done via direct DB update (coolify-db psql).
                skipped.append(f"{app_name}:migrated_via_db")
                continue
            raise
        migrated.append(app_name)

    result = {"migrated": migrated, "skipped": skipped, "migration_count": len(migrated)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if migrated else 2


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
            raise RuntimeError("dockercompose applications must use --compose-domain SERVICE=DOMAIN for public routing")
        domains = [str(entry["domain"]) for entry in compose_domains]
        domains_for_api = []
    else:
        if args.domain:
            domains = [args.domain]
        elif args.subdomain:
            domains = [f"http://{args.subdomain}.apps.localhost"]
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
            deploy_key_path = (
                Path(args.deploy_key_path).expanduser()
                if args.deploy_key_path
                else default_deploy_key_path(normalized_repo)
            )
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
    result = {
        "application_uuid": str(application["uuid"]),
        "application_name": args.app_name,
        "domains": domains,
        "source": source,
        "repository": repo_for_coolify,
        "project_uuid": str(project["uuid"]),
        "environment_uuid": str(environment["uuid"]),
        "server_uuid": str(server["uuid"]),
        "destination_uuid": destination_uuid,
    }
    cancelled_deployments = cancel_active_deployments_for_application(client, application_name=args.app_name)
    if cancelled_deployments:
        result["cancelled_deployments"] = cancelled_deployments
    deployment_uuid = client.deploy_application(str(application["uuid"]), force=args.force)
    result["deployment_uuid"] = deployment_uuid
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
    attempts: list[dict[str, Any]] = []
    if args.wait:
        max_attempts = max(1, args.max_deploy_attempts)
        retry_delay = max(0, args.retry_delay)
        for attempt_number in range(1, max_attempts + 1):
            if attempt_number > 1:
                deployment_uuid = client.deploy_application(str(application["uuid"]), force=args.force)
                result["deployment_uuid"] = deployment_uuid
            deployment = wait_for_deployment(client, deployment_uuid, args.timeout)
            status = str(deployment.get("status", ""))
            retry_reason = transient_deployment_failure_reason(deployment)
            attempt_record = {
                "attempt": attempt_number,
                "deployment_uuid": deployment_uuid,
                "status": status,
            }
            if retry_reason:
                attempt_record["retry_reason"] = retry_reason
            attempts.append(attempt_record)
            result["deployment"] = deployment
            result["status"] = status
            if status == "finished":
                break
            if retry_reason and attempt_number < max_attempts:
                pause_before_retry(retry_delay, retry_reason=retry_reason)
                continue
            result["attempts"] = attempts
            print(json.dumps(result, indent=2, sort_keys=True))
            raise RuntimeError(f"Deployment {deployment_uuid} finished with status {result['status']}")
        result["attempts"] = attempts
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# Proxmox guest-exec backed Coolify commands (ADR 0345)
# ---------------------------------------------------------------------------

_SAFE_IDENT_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _safe_identifier(value: str, field: str) -> str:
    """Validate *value* as a safe SQL identifier (alphanumeric, dash, underscore).

    Prevents SQL injection in migrate-apps server name queries.
    """
    if not _SAFE_IDENT_RE.match(value):
        raise ValueError(f"Unsafe value for {field}: {value!r} (only alphanumeric, dash, and underscore are allowed)")
    return value


def _make_proxmox_client(proxmox_auth_file: str, node: str = "pve") -> ProxmoxClient:
    """Build a ProxmoxClient from the given auth file.

    Uses load_proxmox_auth from controller_automation_toolkit (ADR 0343).
    Falls back to the local implementation in proxmox_tool if the toolkit is unavailable.
    """
    if ProxmoxClient is None:
        raise ImportError("proxmox_tool.py is required for guest-exec operations but could not be imported")
    if load_proxmox_auth is None:
        raise ImportError("controller_automation_toolkit is required for load_proxmox_auth but could not be imported")
    auth = load_proxmox_auth(proxmox_auth_file)
    return ProxmoxClient(
        api_url=auth["api_url"],
        authorization_header=auth["authorization_header"],
        node=node,
        verify_ssl=auth.get("verify_ssl", False),
    )


def _psql_query(
    client: ProxmoxClient,
    vmid: int,
    container: str,
    db_user: str,
    sql: str,
    timeout: int = 30,
) -> str:
    """Run a SQL query in a Postgres container and return stripped stdout.

    Uses psql -t -A (tuple-only, unaligned) for clean programmatic output.
    Raises RuntimeError if the command exits non-zero.
    """
    exit_code, stdout, stderr = proxmox_guest_exec(
        client,
        vmid,
        ["docker", "exec", container, "psql", "-U", db_user, "-t", "-A", "-c", sql],
        timeout=timeout,
    )
    if exit_code != 0:
        raise RuntimeError(f"psql query failed (exit {exit_code}): {stderr.strip() or stdout.strip()}")
    return stdout.strip()


def command_db_exec(args: argparse.Namespace) -> int:
    """
    Execute a SQL statement in the Coolify Postgres container on a given VM.

    Runs: docker exec <container> psql -U <user> -c '<sql>'

    Output: JSON with vmid, container, sql, exit_code, stdout, stderr.
    """
    client = _make_proxmox_client(args.proxmox_auth_file, node=getattr(args, "node", "pve"))
    vmid = int(args.vmid)
    container = args.container or "coolify-db"
    db_user = args.db_user or "coolify"

    exit_code, stdout, stderr = proxmox_guest_exec(
        client,
        vmid,
        ["docker", "exec", container, "psql", "-U", db_user, "-c", args.sql],
        timeout=args.timeout,
    )
    result = {
        "vmid": vmid,
        "container": container,
        "sql": args.sql,
        "exit_code": exit_code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }
    print(json.dumps(result, indent=2))
    return 0 if exit_code == 0 else 1


def command_clear_cache(args: argparse.Namespace) -> int:
    """
    Clear the Coolify application and config cache on the control-plane VM.

    Equivalent to: docker exec coolify bash -c
      'cd /var/www/html && php artisan cache:clear && php artisan config:clear'

    Run this after any direct database change to ensure Coolify picks up the
    new state without requiring a container restart.
    """
    client = _make_proxmox_client(args.proxmox_auth_file, node=getattr(args, "node", "pve"))
    vmid = int(args.vmid)
    container = args.coolify_container or "coolify"

    script = "cd /var/www/html && php artisan cache:clear && php artisan config:clear"
    exit_code, stdout, stderr = proxmox_guest_exec(
        client,
        vmid,
        ["docker", "exec", container, "bash", "-c", script],
        timeout=60,
    )
    result = {
        "vmid": vmid,
        "container": container,
        "exit_code": exit_code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }
    print(json.dumps(result, indent=2))
    return 0 if exit_code == 0 else 1


def command_migrate_apps(args: argparse.Namespace) -> int:
    """
    Migrate Coolify application destination_id from one server to another via direct
    DB update — bypassing the Coolify API v1 limitation (PATCH /applications rejects
    server_uuid and destination_uuid with HTTP 422).

    Workflow
    --------
    1. Resolve standalone_docker destination IDs from server names (JOIN query).
    2. Count apps on the source destination.  Exit 2 (no-op) if count == 0.
    3. List app names for result reporting.
    4. UPDATE applications SET destination_id = <to_id> WHERE destination_id = <from_id>
    5. Clear Coolify application + config cache.

    Idempotent: calling this when apps are already on the target server exits 2.
    Use --dry-run to preview what would be migrated without making changes.
    """
    client = _make_proxmox_client(args.proxmox_auth_file, node=getattr(args, "node", "pve"))
    vmid = int(args.vmid)
    db_container = args.container or "coolify-db"
    app_container = args.coolify_container or "coolify"
    db_user = args.db_user or "coolify"

    from_name = _safe_identifier(args.from_server, "--from")
    to_name = _safe_identifier(args.to_server, "--to")

    # Step 1: Resolve destination IDs from server names
    from_sql = (
        f"SELECT sd.id FROM standalone_dockers sd "
        f"JOIN servers s ON s.id = sd.server_id "
        f"WHERE s.name = '{from_name}' LIMIT 1"
    )
    to_sql = (
        f"SELECT sd.id FROM standalone_dockers sd "
        f"JOIN servers s ON s.id = sd.server_id "
        f"WHERE s.name = '{to_name}' LIMIT 1"
    )

    from_id_str = _psql_query(client, vmid, db_container, db_user, from_sql)
    to_id_str = _psql_query(client, vmid, db_container, db_user, to_sql)

    missing: list[str] = []
    if not from_id_str:
        missing.append(f"source server '{from_name}'")
    if not to_id_str:
        missing.append(f"target server '{to_name}'")
    if missing:
        print(
            json.dumps({"error": f"Could not find standalone_docker destination for: {', '.join(missing)}"}),
            file=sys.stderr,
        )
        return 1

    from_id = int(from_id_str)
    to_id = int(to_id_str)

    # Step 2: Count apps on source
    count_str = _psql_query(
        client,
        vmid,
        db_container,
        db_user,
        f"SELECT count(*) FROM applications WHERE destination_id = {from_id}",
    )
    count = int(count_str) if count_str.isdigit() else 0

    if count == 0:
        result = {
            "status": "nothing_to_migrate",
            "from_server": from_name,
            "to_server": to_name,
            "from_destination_id": from_id,
            "to_destination_id": to_id,
            "migrated_count": 0,
            "migrated_apps": [],
        }
        print(json.dumps(result, indent=2))
        return 2

    # Step 3: List app names
    names_raw = _psql_query(
        client,
        vmid,
        db_container,
        db_user,
        f"SELECT name FROM applications WHERE destination_id = {from_id}",
    )
    app_names = [n.strip() for n in names_raw.splitlines() if n.strip()]

    # Step 4: Run the migration (skipped in dry-run mode)
    if not args.dry_run:
        _psql_query(
            client,
            vmid,
            db_container,
            db_user,
            f"UPDATE applications SET destination_id = {to_id} WHERE destination_id = {from_id}",
        )

        # Step 5: Clear Coolify cache so changes take effect immediately
        cache_script = "cd /var/www/html && php artisan cache:clear && php artisan config:clear"
        cache_rc, _, cache_err = proxmox_guest_exec(
            client,
            vmid,
            ["docker", "exec", app_container, "bash", "-c", cache_script],
            timeout=60,
        )
        if cache_rc != 0:
            # Non-fatal: migration is done, cache miss is recoverable
            print(
                json.dumps({"warning": f"Migration succeeded but cache clear failed: {cache_err.strip()}"}),
                file=sys.stderr,
            )

    result = {
        "status": "dry_run" if args.dry_run else "migrated",
        "from_server": from_name,
        "to_server": to_name,
        "from_destination_id": from_id,
        "to_destination_id": to_id,
        "migrated_count": count,
        "migrated_apps": app_names,
    }
    print(json.dumps(result, indent=2))
    return 0


def command_install_deploy_key(args: argparse.Namespace) -> int:
    """
    Install the Coolify SSH deploy public key on a target VM.

    Coolify needs to SSH into deployment servers using its own deploy key.
    This command installs that key into /root/.ssh/authorized_keys on the
    target VM so that server validation and deployment succeed.

    Idempotent: exits 2 if the key is already present.
    """
    client = _make_proxmox_client(args.proxmox_auth_file, node=getattr(args, "node", "pve"))
    vmid = int(args.vmid)
    pubkey = args.pubkey.strip()

    # Read current authorized_keys (create empty string if absent)
    _, existing, _ = proxmox_guest_exec(
        client,
        vmid,
        ["bash", "-c", "cat /root/.ssh/authorized_keys 2>/dev/null || true"],
        timeout=15,
    )

    key_comment = pubkey.split()[-1] if len(pubkey.split()) >= 3 else ""

    if pubkey in existing:
        result = {
            "vmid": vmid,
            "status": "already_present",
            "key_fingerprint": key_comment,
        }
        print(json.dumps(result, indent=2))
        return 2  # idempotent no-op

    script = (
        "mkdir -p /root/.ssh && "
        "chmod 700 /root/.ssh && "
        f"echo {shlex.quote(pubkey)} >> /root/.ssh/authorized_keys && "
        "chmod 600 /root/.ssh/authorized_keys"
    )
    exit_code, _, stderr = proxmox_guest_exec(client, vmid, ["bash", "-c", script], timeout=15)
    if exit_code != 0:
        print(
            json.dumps({"error": stderr.strip(), "exit_code": exit_code}),
            file=sys.stderr,
        )
        return 1
    result = {
        "vmid": vmid,
        "status": "installed",
        "key_fingerprint": key_comment,
    }
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed Coolify API actions.")
    parser.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE), help="Path to the Coolify auth JSON file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    whoami_parser = subparsers.add_parser("whoami", help="Show the configured Coolify auth target.")
    whoami_parser.set_defaults(func=command_whoami)

    apps_parser = subparsers.add_parser("list-applications", help="List Coolify-managed applications.")
    apps_parser.set_defaults(func=command_list_applications)

    register_server_parser = subparsers.add_parser(
        "register-deployment-server",
        help="Register a new Coolify deployment server (ADR 0340). Idempotent.",
    )
    register_server_parser.add_argument("--host", required=True, help="Hostname of the deployment server to register.")
    register_server_parser.add_argument("--ip", required=True, help="IP address of the deployment server.")
    register_server_parser.set_defaults(func=command_register_deployment_server)

    migrate_server_parser = subparsers.add_parser(
        "migrate-deployment-server",
        help="Re-assign all Coolify applications from one server to another (ADR 0340). Exit 2 if nothing to migrate.",
    )
    migrate_server_parser.add_argument(
        "--from",
        dest="from_server",
        required=True,
        default=_default_deployment_server() or "coolify-lv3",
        help="Source server name to migrate apps away from.",
    )
    migrate_server_parser.add_argument(
        "--to",
        dest="to_server",
        required=True,
        default=_default_deployment_server() or "coolify-apps-lv3",
        help="Target server name to migrate apps to.",
    )
    migrate_server_parser.set_defaults(func=command_migrate_deployment_server)

    deploy_parser = subparsers.add_parser(
        "deploy-repo", help="Create or update one repo-backed Coolify application and deploy it."
    )
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
    deploy_parser.add_argument("--domain", help="Full domain URL, for example http://apps.localhost.")
    deploy_parser.add_argument("--subdomain", help="Subdomain under apps.localhost, for example hello.")
    deploy_parser.add_argument(
        "--build-pack", default="static", choices=["nixpacks", "static", "dockerfile", "dockercompose"]
    )
    deploy_parser.add_argument("--ports", default="80", help="Comma-separated exposed ports.")
    deploy_parser.add_argument("--description", help="Optional Coolify application description.")
    deploy_parser.add_argument(
        "--private-key-uuid", help="Existing Coolify private key UUID for private deploy-key applications."
    )
    deploy_parser.add_argument("--deploy-key-name", help="Deploy key label to reuse or create for GitHub and Coolify.")
    deploy_parser.add_argument("--deploy-key-path", help="Local SSH private key path used for deploy-key bootstrap.")
    deploy_parser.add_argument(
        "--dockerfile-location", help="Repository-relative Dockerfile path for dockerfile build pack."
    )
    deploy_parser.add_argument(
        "--docker-compose-location", help="Repository-relative compose file path for dockercompose build pack."
    )
    deploy_parser.add_argument(
        "--compose-domain",
        action="append",
        help="Map one Docker Compose service to one public domain using SERVICE=DOMAIN. Repeat for multiple services.",
    )
    deploy_parser.add_argument(
        "--publish-directory", help="Static publish directory for static build pack deployments."
    )
    deploy_parser.add_argument("--wait", action="store_true", help="Wait for the deployment result.")
    deploy_parser.add_argument("--timeout", type=int, default=900, help="Wait timeout in seconds.")
    deploy_parser.add_argument("--force", action="store_true", help="Force a rebuild without cache.")
    deploy_parser.add_argument(
        "--max-deploy-attempts",
        type=int,
        default=3,
        help="Retry transient deployment failures up to this many total attempts when --wait is enabled.",
    )
    deploy_parser.add_argument(
        "--retry-delay",
        type=int,
        default=15,
        help="Seconds to wait before retrying a transient deployment failure.",
    )
    deploy_parser.set_defaults(func=command_deploy_repo)

    # --- db-exec (migrated from proxmox_tool.py, ADR 0345) ---
    db_exec_parser = subparsers.add_parser(
        "db-exec",
        help="Execute a SQL statement in the Coolify Postgres container (via Proxmox guest exec).",
    )
    db_exec_parser.add_argument(
        "--proxmox-auth-file",
        dest="proxmox_auth_file",
        required=True,
        help="Path to Proxmox API token JSON file.",
    )
    db_exec_parser.add_argument("--vmid", required=True, type=int, help="VMID of the Coolify control-plane VM.")
    db_exec_parser.add_argument("--container", help="Postgres container name (default: coolify-db).")
    db_exec_parser.add_argument("--db-user", dest="db_user", help="Postgres user (default: coolify).")
    db_exec_parser.add_argument("--sql", required=True, help="SQL statement to execute.")
    db_exec_parser.add_argument("--timeout", type=int, default=30, help="Exec timeout in seconds (default: 30).")
    db_exec_parser.add_argument("--node", default="pve", help="Proxmox node name (default: pve).")
    db_exec_parser.set_defaults(func=command_db_exec)

    # --- clear-cache (migrated from proxmox_tool.py, ADR 0345) ---
    clear_cache_parser = subparsers.add_parser(
        "clear-cache",
        help="Clear Coolify application and config cache (via Proxmox guest exec).",
    )
    clear_cache_parser.add_argument(
        "--proxmox-auth-file",
        dest="proxmox_auth_file",
        required=True,
        help="Path to Proxmox API token JSON file.",
    )
    clear_cache_parser.add_argument("--vmid", required=True, type=int, help="VMID of the Coolify control-plane VM.")
    clear_cache_parser.add_argument(
        "--coolify-container",
        dest="coolify_container",
        help="Coolify app container name (default: coolify).",
    )
    clear_cache_parser.add_argument("--node", default="pve", help="Proxmox node name (default: pve).")
    clear_cache_parser.set_defaults(func=command_clear_cache)

    # --- migrate-apps (migrated from proxmox_tool.py, ADR 0345) ---
    migrate_apps_parser = subparsers.add_parser(
        "migrate-apps",
        help="Migrate Coolify app destination_id in the DB (bypasses API v1 limitation).",
        description=(
            "Resolves standalone_docker destination IDs from server names, "
            "runs the UPDATE, and clears the Coolify cache.  Idempotent."
        ),
    )
    migrate_apps_parser.add_argument(
        "--proxmox-auth-file",
        dest="proxmox_auth_file",
        required=True,
        help="Path to Proxmox API token JSON file.",
    )
    migrate_apps_parser.add_argument("--vmid", required=True, type=int, help="VMID of the Coolify control-plane VM.")
    migrate_apps_parser.add_argument(
        "--from",
        dest="from_server",
        required=True,
        metavar="SERVER_NAME",
        help="Source Coolify server name (e.g. coolify-lv3).",
    )
    migrate_apps_parser.add_argument(
        "--to",
        dest="to_server",
        required=True,
        metavar="SERVER_NAME",
        help="Target Coolify server name (e.g. coolify-apps-lv3).",
    )
    migrate_apps_parser.add_argument("--container", help="Postgres container name (default: coolify-db).")
    migrate_apps_parser.add_argument(
        "--coolify-container",
        dest="coolify_container",
        help="Coolify app container name for cache clear (default: coolify).",
    )
    migrate_apps_parser.add_argument("--db-user", dest="db_user", help="Postgres user (default: coolify).")
    migrate_apps_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be migrated without making any changes.",
    )
    migrate_apps_parser.add_argument("--node", default="pve", help="Proxmox node name (default: pve).")
    migrate_apps_parser.set_defaults(func=command_migrate_apps)

    # --- install-deploy-key (migrated from proxmox_tool.py, ADR 0345) ---
    install_deploy_key_parser = subparsers.add_parser(
        "install-deploy-key",
        help="Install the Coolify SSH deploy public key on a target VM (via Proxmox guest exec).",
    )
    install_deploy_key_parser.add_argument(
        "--proxmox-auth-file",
        dest="proxmox_auth_file",
        required=True,
        help="Path to Proxmox API token JSON file.",
    )
    install_deploy_key_parser.add_argument(
        "--vmid", required=True, type=int, help="Target VMID (e.g. coolify-apps-lv3 VMID)."
    )
    install_deploy_key_parser.add_argument(
        "--pubkey",
        required=True,
        help="Coolify deploy public key string (from Coolify UI > Settings > SSH Keys).",
    )
    install_deploy_key_parser.add_argument("--node", default="pve", help="Proxmox node name (default: pve).")
    install_deploy_key_parser.set_defaults(func=command_install_deploy_key)

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
