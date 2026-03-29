from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import service_id_resolver  # noqa: E402


def test_resolve_service_id_maps_public_edge_playbook_to_nginx_edge() -> None:
    assert service_id_resolver.resolve_service_id("public-edge") == "nginx_edge"


def test_resolve_service_id_keeps_canonical_service_ids_stable() -> None:
    assert service_id_resolver.resolve_service_id("nginx_edge") == "nginx_edge"
    assert service_id_resolver.resolve_service_id("platform_context_api") == "platform_context_api"


def test_resolve_service_id_maps_build_artifact_cache_playbook_to_docker_build() -> None:
    assert service_id_resolver.resolve_service_id("build-artifact-cache") == "docker_build"
