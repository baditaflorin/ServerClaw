from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import docker_publication_assurance as tool


def test_derive_expected_bindings_collects_probe_and_contract_bindings() -> None:
    service_probe = {
        "startup": {
            "kind": "http",
            "url": "http://127.0.0.1:18080/ready",
            "method": "GET",
            "timeout_seconds": 10,
        },
        "liveness": {
            "kind": "tcp",
            "host": "10.10.10.20",
            "port": 19000,
            "timeout_seconds": 10,
        },
        "readiness": {
            "kind": "http",
            "url": "http://127.0.0.1:18080/ready",
            "method": "GET",
            "timeout_seconds": 10,
            "docker_publication": {
                "container_name": "keycloak-keycloak-1",
                "bindings": [{"host": "10.10.10.20", "port": 8091}],
            },
        },
    }

    bindings = tool.derive_expected_bindings(service_probe, {"127.0.0.1", "10.10.10.20"})

    assert bindings == [
        {"host": "127.0.0.1", "port": 18080, "source_phase": "startup"},
        {"host": "10.10.10.20", "port": 19000, "source_phase": "liveness"},
        {"host": "10.10.10.20", "port": 8091, "source_phase": "contract"},
    ]


def test_derive_expected_bindings_supports_disabling_probe_derivation() -> None:
    service_probe = {
        "liveness": {
            "kind": "tcp",
            "host": "127.0.0.1",
            "port": 8222,
            "timeout_seconds": 10,
        },
        "readiness": {
            "kind": "http",
            "url": "https://10.10.10.20:8222/alive",
            "method": "GET",
            "timeout_seconds": 10,
            "docker_publication": {
                "container_name": "vaultwarden",
                "derive_bindings_from_probes": False,
                "bindings": [{"host": "10.10.10.20", "port": 8222}],
            },
        },
    }

    bindings = tool.derive_expected_bindings(service_probe, {"127.0.0.1", "10.10.10.20"})

    assert bindings == [
        {"host": "10.10.10.20", "port": 8222, "source_phase": "contract"},
    ]


def test_binding_matches_accepts_wildcard_bindings_for_loopback_and_guest_ip() -> None:
    assert tool._binding_matches("127.0.0.1", 8201, {"host_ip": "0.0.0.0", "host_port": "8201"}) is True
    assert tool._binding_matches("10.10.10.20", 8200, {"host_ip": "0.0.0.0", "host_port": "8200"}) is True
    assert tool._binding_matches("10.10.10.20", 8200, {"host_ip": "127.0.0.1", "host_port": "8200"}) is False


def test_flatten_published_bindings_falls_back_to_host_config_bindings() -> None:
    assert tool.flatten_published_bindings(
        {},
        fallback_port_map={
            "8080/tcp": [
                {"HostIp": "", "HostPort": "8095"},
                {"HostIp": "10.10.10.20", "HostPort": "8095"},
            ]
        },
    ) == [
        {"host_ip": "", "host_port": "8095"},
        {"host_ip": "10.10.10.20", "host_port": "8095"},
    ]


class FakeRunner:
    def __init__(self) -> None:
        self.docker_restarted = False
        self.compose_recreated = False

    def __call__(self, argv: list[str], cwd: str | None) -> tool.CommandResult:
        if argv == ["hostname", "-I"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="10.10.10.20", stderr="", cwd=cwd)
        if argv[:3] == ["docker", "info", "--format"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="28.0.4", stderr="", cwd=cwd)
        if argv[:4] == ["iptables", "-t", "nat", "-S"]:
            return tool.CommandResult(
                argv=argv,
                returncode=0 if self.docker_restarted else 1,
                stdout="-N DOCKER" if self.docker_restarted else "",
                stderr="",
                cwd=cwd,
            )
        if argv[:4] == ["iptables", "-t", "filter", "-S"]:
            return tool.CommandResult(
                argv=argv,
                returncode=0 if self.docker_restarted else 1,
                stdout="-N DOCKER-FORWARD" if self.docker_restarted else "",
                stderr="",
                cwd=cwd,
            )
        if argv == ["systemctl", "restart", "docker"]:
            self.docker_restarted = True
            return tool.CommandResult(argv=argv, returncode=0, stdout="", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "compose"]:
            self.compose_recreated = True
            return tool.CommandResult(argv=argv, returncode=0, stdout="recreated", stderr="", cwd=cwd)
        if argv[:3] == ["docker", "network", "inspect"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="[]", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "inspect"]:
            host_port_bindings = (
                {
                    "8080/tcp": [
                        {"HostIp": "", "HostPort": "8095"},
                        {"HostIp": "10.10.10.20", "HostPort": "8095"},
                    ]
                }
                if self.compose_recreated
                else {}
            )
            payload = [
                {
                    "HostConfig": {
                        "NetworkMode": "bridge",
                        "PortBindings": host_port_bindings,
                    },
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project": "harbor",
                            "com.docker.compose.project.working_dir": "/opt/harbor",
                            "com.docker.compose.project.config_files": "docker-compose.yml",
                        }
                    },
                    "NetworkSettings": {
                        "Ports": {},
                        "Networks": {"harbor_harbor": {}},
                    },
                }
            ]
            return tool.CommandResult(argv=argv, returncode=0, stdout=json.dumps(payload), stderr="", cwd=cwd)
        raise AssertionError(f"Unexpected command: {argv}")


def test_assure_docker_publication_restarts_docker_and_recreates_compose() -> None:
    runner = FakeRunner()
    service_probe = {
        "liveness": {
            "kind": "http",
            "url": "http://127.0.0.1:8095/api/v2.0/ping",
            "method": "GET",
            "timeout_seconds": 10,
        },
        "readiness": {
            "kind": "http",
            "url": "https://registry.lv3.org/api/v2.0/ping",
            "method": "GET",
            "timeout_seconds": 10,
            "docker_publication": {
                "container_name": "nginx",
                "bindings": [{"host": "10.10.10.20", "port": 8095}],
                "required_networks": ["harbor_harbor"],
            },
        },
    }

    def listener_checker(host: str, port: int, timeout: float) -> bool:
        del timeout
        return runner.compose_recreated and (host, port) in {
            ("127.0.0.1", 8095),
            ("10.10.10.20", 8095),
        }

    result = tool.assure_docker_publication(
        service_id="harbor",
        service_probe=service_probe,
        contract=service_probe["readiness"]["docker_publication"],
        heal=True,
        allow_listener_warmup_after_heal=False,
        command_runner=runner,
        listener_checker=listener_checker,
    )

    assert result["ok"] is True
    assert result["healed"] is True
    assert result["compose_recreated"] is True
    assert [action["action"] for action in result["actions"]] == [
        "restart_docker",
        "wait_for_docker",
        "compose_force_recreate",
    ]
    assert result["summary"] == "docker publication contract is satisfied"


class PartialComposeRunner(FakeRunner):
    def __call__(self, argv: list[str], cwd: str | None) -> tool.CommandResult:
        if argv[:2] == ["docker", "compose"]:
            self.compose_recreated = True
            return tool.CommandResult(
                argv=argv,
                returncode=1,
                stdout="",
                stderr="Container nginx Recreated",
                cwd=cwd,
            )
        return super().__call__(argv, cwd)


def test_assure_docker_publication_allows_listener_warmup_after_partial_compose_recreate() -> None:
    runner = PartialComposeRunner()
    service_probe = {
        "liveness": {
            "kind": "http",
            "url": "http://127.0.0.1:8095/api/v2.0/ping",
            "method": "GET",
            "timeout_seconds": 10,
        },
        "readiness": {
            "kind": "http",
            "url": "https://registry.lv3.org/api/v2.0/ping",
            "method": "GET",
            "timeout_seconds": 10,
            "docker_publication": {
                "container_name": "nginx",
                "bindings": [{"host": "10.10.10.20", "port": 8095}],
                "required_networks": ["harbor_harbor"],
            },
        },
    }

    result = tool.assure_docker_publication(
        service_id="harbor",
        service_probe=service_probe,
        contract=service_probe["readiness"]["docker_publication"],
        heal=True,
        allow_listener_warmup_after_heal=True,
        command_runner=runner,
        listener_checker=lambda *_args: False,
    )

    assert result["ok"] is True
    assert result["compose_recreated"] is False
    assert result["summary"] == "docker publication primitives recovered; listener warm-up deferred to readiness verification"


class PostComposeChainLossRunner:
    def __init__(self) -> None:
        self.compose_attempts = 0
        self.docker_restarts = 0

    def __call__(self, argv: list[str], cwd: str | None) -> tool.CommandResult:
        if argv == ["hostname", "-I"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="10.10.10.20", stderr="", cwd=cwd)
        if argv[:3] == ["docker", "info", "--format"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="28.0.4", stderr="", cwd=cwd)
        if argv[:4] == ["iptables", "-t", "nat", "-S"]:
            chain_present = self.compose_attempts == 0 or self.docker_restarts > 0
            return tool.CommandResult(
                argv=argv,
                returncode=0 if chain_present else 1,
                stdout="-N DOCKER" if chain_present else "",
                stderr="",
                cwd=cwd,
            )
        if argv[:4] == ["iptables", "-t", "filter", "-S"]:
            chain_present = self.compose_attempts == 0 or self.docker_restarts > 0
            return tool.CommandResult(
                argv=argv,
                returncode=0 if chain_present else 1,
                stdout="-N DOCKER-FORWARD" if chain_present else "",
                stderr="",
                cwd=cwd,
            )
        if argv == ["systemctl", "restart", "docker"]:
            self.docker_restarts += 1
            return tool.CommandResult(argv=argv, returncode=0, stdout="", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "compose"]:
            self.compose_attempts += 1
            return tool.CommandResult(
                argv=argv,
                returncode=0 if self.compose_attempts > 1 else 1,
                stdout="recreated" if self.compose_attempts > 1 else "",
                stderr="Container harbor-log failed to start" if self.compose_attempts == 1 else "",
                cwd=cwd,
            )
        if argv[:3] == ["docker", "network", "inspect"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="[]", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "inspect"]:
            payload = [
                {
                    "HostConfig": {
                        "NetworkMode": "bridge",
                        "PortBindings": {
                            "8080/tcp": [
                                {"HostIp": "", "HostPort": "8095"},
                                {"HostIp": "10.10.10.20", "HostPort": "8095"},
                            ]
                        },
                    },
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project": "harbor",
                            "com.docker.compose.project.working_dir": "/opt/harbor",
                            "com.docker.compose.project.config_files": "docker-compose.yml",
                        }
                    },
                    "NetworkSettings": {
                        "Ports": {},
                        "Networks": {"harbor_harbor": {}},
                    },
                }
            ]
            return tool.CommandResult(argv=argv, returncode=0, stdout=json.dumps(payload), stderr="", cwd=cwd)
        raise AssertionError(f"Unexpected command: {argv}")


def test_assure_docker_publication_recovers_when_compose_recreate_drops_docker_chains() -> None:
    runner = PostComposeChainLossRunner()
    service_probe = {
        "liveness": {
            "kind": "http",
            "url": "http://127.0.0.1:8095/api/v2.0/ping",
            "method": "GET",
            "timeout_seconds": 10,
        },
        "readiness": {
            "kind": "http",
            "url": "https://registry.lv3.org/api/v2.0/ping",
            "method": "GET",
            "timeout_seconds": 10,
            "docker_publication": {
                "container_name": "nginx",
                "bindings": [{"host": "10.10.10.20", "port": 8095}],
                "required_networks": ["harbor_harbor"],
            },
        },
    }

    def listener_checker(host: str, port: int, timeout: float) -> bool:
        del timeout
        return runner.compose_attempts > 1 and (host, port) in {
            ("127.0.0.1", 8095),
            ("10.10.10.20", 8095),
        }

    result = tool.assure_docker_publication(
        service_id="harbor",
        service_probe=service_probe,
        contract=service_probe["readiness"]["docker_publication"],
        heal=True,
        allow_listener_warmup_after_heal=True,
        command_runner=runner,
        listener_checker=listener_checker,
    )

    assert result["ok"] is True
    assert result["healed"] is True
    assert result["compose_recreated"] is True
    assert [action["action"] for action in result["actions"]] == [
        "compose_force_recreate",
        "restart_docker",
        "wait_for_docker",
        "compose_force_recreate",
    ]
    assert result["summary"] == "docker publication contract is satisfied"
