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


def test_flatten_published_bindings_only_reports_live_network_settings_bindings() -> None:
    assert tool.flatten_published_bindings(
        {
            "8080/tcp": [
                {"HostIp": "", "HostPort": "8095"},
                {"HostIp": "10.10.10.20", "HostPort": "8095"},
            ]
        }
    ) == [
        {"host_ip": "", "host_port": "8095"},
        {"host_ip": "10.10.10.20", "host_port": "8095"},
    ]


def test_flatten_configured_bindings_reads_host_config_bindings() -> None:
    assert tool.flatten_configured_bindings(
        {
            "8080/tcp": [
                {"HostIp": "", "HostPort": "8095"},
                {"HostIp": "10.10.10.20", "HostPort": "8095"},
            ]
        }
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
            network_port_bindings = host_port_bindings if self.compose_recreated else {}
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
                        "Ports": network_port_bindings,
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
            network_port_bindings = (
                {
                    "8080/tcp": [
                        {"HostIp": "", "HostPort": "8095"},
                        {"HostIp": "10.10.10.20", "HostPort": "8095"},
                    ]
                }
                if self.compose_attempts > 1
                else {}
            )
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
                        "Ports": network_port_bindings,
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


class HostConfigOnlyPortBindingRunner:
    def __init__(self) -> None:
        self.compose_recreated = False

    def __call__(self, argv: list[str], cwd: str | None) -> tool.CommandResult:
        if argv == ["hostname", "-I"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="10.10.10.20", stderr="", cwd=cwd)
        if argv[:3] == ["docker", "info", "--format"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="28.0.4", stderr="", cwd=cwd)
        if argv[:4] == ["iptables", "-t", "nat", "-S"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="-N DOCKER", stderr="", cwd=cwd)
        if argv[:4] == ["iptables", "-t", "filter", "-S"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="-N DOCKER-FORWARD", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "compose"]:
            self.compose_recreated = True
            return tool.CommandResult(argv=argv, returncode=0, stdout="recreated", stderr="", cwd=cwd)
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


def test_assure_docker_publication_rejects_host_config_only_port_bindings_after_recreate() -> None:
    runner = HostConfigOnlyPortBindingRunner()
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

    assert result["ok"] is False
    assert result["compose_recreated"] is True
    assert result["after"]["published_bindings"] == []
    assert result["after"]["configured_bindings"] == [
        {"host_ip": "", "host_port": "8095"},
        {"host_ip": "10.10.10.20", "host_port": "8095"},
    ]
    assert result["after"]["issues"]["missing_port_bindings"] == [
        {"host": "127.0.0.1", "port": 8095, "source_phase": "liveness"},
        {"host": "10.10.10.20", "port": 8095, "source_phase": "contract"},
    ]
    assert result["summary"] == "port bindings missing, listeners missing"


class StaleNetworkComposeRunner:
    def __init__(self) -> None:
        self.compose_attempts = 0
        self.compose_downs = 0
        self.network_removals: list[str] = []

    def __call__(self, argv: list[str], cwd: str | None) -> tool.CommandResult:
        if argv == ["hostname", "-I"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="10.10.10.20", stderr="", cwd=cwd)
        if argv[:3] == ["docker", "info", "--format"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="28.0.4", stderr="", cwd=cwd)
        if argv[:4] == ["iptables", "-t", "nat", "-S"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="-N DOCKER", stderr="", cwd=cwd)
        if argv[:4] == ["iptables", "-t", "filter", "-S"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="-N DOCKER-FORWARD", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "compose"] and "down" in argv:
            self.compose_downs += 1
            return tool.CommandResult(argv=argv, returncode=0, stdout="removed", stderr="", cwd=cwd)
        if argv[:3] == ["docker", "network", "rm"]:
            self.network_removals.append(argv[-1])
            return tool.CommandResult(argv=argv, returncode=0, stdout=argv[-1], stderr="", cwd=cwd)
        if argv[:2] == ["docker", "compose"]:
            self.compose_attempts += 1
            if self.compose_attempts == 1:
                return tool.CommandResult(
                    argv=argv,
                    returncode=1,
                    stdout="",
                    stderr="failed to create endpoint dify-web on network dify_default: network deadbeef does not exist",
                    cwd=cwd,
                )
            return tool.CommandResult(argv=argv, returncode=0, stdout="recreated", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "inspect"]:
            payload = [
                {
                    "HostConfig": {
                        "NetworkMode": "dify_default",
                        "PortBindings": {
                            "80/tcp": [
                                {"HostIp": "", "HostPort": "8094"},
                            ]
                        },
                    },
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project": "dify",
                            "com.docker.compose.project.working_dir": "/opt/dify",
                            "com.docker.compose.project.config_files": "/opt/dify/docker-compose.yml",
                        }
                    },
                    "NetworkSettings": {
                        "Ports": (
                            {
                                "80/tcp": [
                                    {"HostIp": "", "HostPort": "8094"},
                                ]
                            }
                            if self.compose_attempts > 1
                            else {}
                        ),
                        "Networks": {"dify_default": {}},
                    },
                }
            ]
            return tool.CommandResult(argv=argv, returncode=0, stdout=json.dumps(payload), stderr="", cwd=cwd)
        raise AssertionError(f"Unexpected command: {argv}")


def test_assure_docker_publication_resets_stale_compose_networks_before_retry() -> None:
    runner = StaleNetworkComposeRunner()
    service_probe = {
        "startup": {
            "kind": "http",
            "url": "http://10.10.10.20:8094/console/api/setup",
            "method": "GET",
            "timeout_seconds": 10,
        },
        "readiness": {
            "kind": "http",
            "url": "https://agents.lv3.org/healthz",
            "method": "GET",
            "timeout_seconds": 10,
            "docker_publication": {
                "container_name": "dify-nginx",
                "required_networks": ["dify_default"],
            },
        },
    }

    def listener_checker(host: str, port: int, timeout: float) -> bool:
        del timeout
        return runner.compose_attempts > 1 and (host, port) == ("10.10.10.20", 8094)

    result = tool.assure_docker_publication(
        service_id="dify",
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
        "compose_reset_down",
        "remove_compose_network",
        "compose_force_recreate",
    ]
    assert runner.compose_downs == 1
    assert runner.network_removals == ["dify_default"]


class ComposeEofRecoveryRunner:
    def __init__(self) -> None:
        self.compose_attempts = 0
        self.docker_restarts = 0

    def __call__(self, argv: list[str], cwd: str | None) -> tool.CommandResult:
        if argv == ["hostname", "-I"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="10.10.10.20", stderr="", cwd=cwd)
        if argv[:3] == ["docker", "info", "--format"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="28.0.4", stderr="", cwd=cwd)
        if argv[:4] == ["iptables", "-t", "nat", "-S"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="-N DOCKER", stderr="", cwd=cwd)
        if argv[:4] == ["iptables", "-t", "filter", "-S"]:
            return tool.CommandResult(argv=argv, returncode=0, stdout="-N DOCKER-FORWARD", stderr="", cwd=cwd)
        if argv == ["systemctl", "restart", "docker"]:
            self.docker_restarts += 1
            return tool.CommandResult(argv=argv, returncode=0, stdout="", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "compose"]:
            self.compose_attempts += 1
            if self.compose_attempts == 1:
                return tool.CommandResult(
                    argv=argv,
                    returncode=1,
                    stdout="",
                    stderr='error during connect: Post "http://%2Fvar%2Frun%2Fdocker.sock/v1.54/containers/harbor-core/stop": EOF',
                    cwd=cwd,
                )
            return tool.CommandResult(argv=argv, returncode=0, stdout="recreated", stderr="", cwd=cwd)
        if argv[:2] == ["docker", "inspect"]:
            payload = [
                {
                    "HostConfig": {
                        "NetworkMode": "harbor_harbor",
                        "PortBindings": {
                            "8080/tcp": [
                                {"HostIp": "", "HostPort": "8095"},
                            ]
                        },
                    },
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project": "harbor",
                            "com.docker.compose.project.working_dir": "/opt/harbor/installer/harbor",
                            "com.docker.compose.project.config_files": "/opt/harbor/installer/harbor/docker-compose.yml",
                        }
                    },
                    "NetworkSettings": {
                        "Ports": (
                            {
                                "8080/tcp": [
                                    {"HostIp": "", "HostPort": "8095"},
                                ]
                            }
                            if self.compose_attempts > 1
                            else {}
                        ),
                        "Networks": {"harbor_harbor": {}},
                    },
                }
            ]
            return tool.CommandResult(argv=argv, returncode=0, stdout=json.dumps(payload), stderr="", cwd=cwd)
        raise AssertionError(f"Unexpected command: {argv}")


def test_assure_docker_publication_restarts_docker_after_compose_eof_when_bindings_stay_missing() -> None:
    runner = ComposeEofRecoveryRunner()
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
    assert runner.docker_restarts == 1
    assert [action["action"] for action in result["actions"]] == [
        "compose_force_recreate",
        "restart_docker",
        "wait_for_docker",
        "compose_force_recreate",
    ]
