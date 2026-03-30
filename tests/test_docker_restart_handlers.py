from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLER_PATHS = [
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common_handlers"
    / "handlers"
    / "main.yml",
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_build_observability"
    / "handlers"
    / "main.yml",
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "handlers"
    / "main.yml",
]


def test_docker_restart_handlers_reset_failed_before_restart() -> None:
    for handler_path in HANDLER_PATHS:
        handlers = yaml.safe_load(handler_path.read_text())
        restart_handler = next(item for item in handlers if item["name"] == "Restart Docker")

        assert restart_handler["ansible.builtin.shell"].splitlines() == [
            "set -euo pipefail",
            "systemctl reset-failed docker.service",
            "systemctl restart docker.service",
        ], handler_path
        assert restart_handler["args"]["executable"] == "/bin/bash", handler_path
