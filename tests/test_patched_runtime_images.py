from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_patched_images as patched_images


def test_patched_image_manifest_is_complete_and_valkey_has_one_shared_pin() -> None:
    manifest = patched_images.load_manifest()

    assert set(manifest["images"]) == {"outline", "glitchtip", "minio", "valkey"}
    assert manifest["images"]["valkey"]["catalog_ids"] == ["shared_valkey_runtime"]
    assert manifest["images"]["valkey"]["platform"] == "linux/amd64"
    assert patched_images.DIGEST_PATTERN.fullmatch(manifest["images"]["valkey"]["digest"])
    assert manifest["images"]["valkey"]["digest"] == (
        "sha256:187679e3bd4036959631e3f03983ab2ba503ab21e6fd0454d508e909db2ee989"
    )


def test_minio_micro_runtime_invokes_binary_without_shell_entrypoint() -> None:
    dockerfile = (REPO_ROOT / "build" / "patched-images" / "minio" / "Dockerfile").read_text(encoding="utf-8")
    compose = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "minio_runtime"
        / "templates"
        / "docker-compose.yml.j2"
    ).read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["/usr/bin/minio"]' in dockerfile
    assert 'CMD ["server", "/data"]' in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "docker-entrypoint.sh" not in dockerfile
    assert "ENV MINIO_" not in dockerfile
    assert "- server" in compose
    assert "- /data" in compose


def test_outline_runner_base_argument_is_global_for_from_instruction() -> None:
    dockerfile = (REPO_ROOT / "build" / "patched-images" / "outline" / "Dockerfile").read_text(encoding="utf-8")
    run_arg = "ARG NODE_RUN_IMAGE=node:26.11.1-bookworm-slim@sha256:"
    runner_stage = "FROM ${NODE_RUN_IMAGE} AS runner"

    assert dockerfile.index(run_arg) < dockerfile.index("FROM ${NODE_BUILD_IMAGE} AS build")
    assert dockerfile.index(run_arg) < dockerfile.index(runner_stage)
    assert dockerfile.count(run_arg) == 1


def test_outline_build_caps_node_heap_to_fit_managed_builder() -> None:
    dockerfile = (REPO_ROOT / "build" / "patched-images" / "outline" / "Dockerfile").read_text(encoding="utf-8")

    assert 'NODE_OPTIONS="--max-old-space-size=3072"' in dockerfile
    assert "YARN_NETWORK_CONCURRENCY=4" in dockerfile
    assert "--max-old-space-size=24000" not in dockerfile


def test_glitchtip_remote_build_uses_its_pinned_source_dockerfile() -> None:
    build_script = (REPO_ROOT / "build" / "patched-images" / "build_remote.sh").read_text(encoding="utf-8")

    assert "if [[ $# -ne 10 ]]" in build_script
    assert '--file "$work_dir/source/Dockerfile"' in build_script


def test_remote_buildx_push_preserves_builder_selection_in_isolated_auth_config() -> None:
    build_script = (REPO_ROOT / "build" / "patched-images" / "build_remote.sh").read_text(encoding="utf-8")

    assert 'source_docker_config="${DOCKER_CONFIG:-$HOME/.docker}"' in build_script
    assert 'cp -a "$source_docker_config/buildx" "$docker_config/"' in build_script
    assert 'export DOCKER_CONFIG="$docker_config"' in build_script
    assert build_script.index('cp -a "$source_docker_config/buildx" "$docker_config/"') < build_script.index(
        'export DOCKER_CONFIG="$docker_config"'
    )
    assert build_script.index('export DOCKER_CONFIG="$docker_config"') < build_script.index("\n    docker buildx build")


def test_remote_build_invocation_supplies_the_declared_argument_contract() -> None:
    manifest = patched_images.load_manifest()
    command = patched_images.remote_build_command(
        image_id="glitchtip",
        registry="registry.example.com",
        project="patched-runtime",
        username="robot$patched-runtime+publisher",
        tag="test-tag",
        entry=manifest["images"]["glitchtip"],
    )

    # bash + script + 10 wrapper parameters; never include the secret in argv.
    assert len(shlex.split(command)) == 12


def test_remote_build_keeps_publisher_secret_on_stdin(monkeypatch) -> None:
    secret = "publisher-secret-sentinel"
    digest = "sha256:" + "a" * 64
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        secret_path = Path(kwargs["env"]["REMOTE_EXEC_STDIN_FILE"])
        captured["secret_file_mode"] = secret_path.stat().st_mode & 0o777
        captured["secret_file_content"] = secret_path.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, f"PATCHED_IMAGE_RESULT image=outline digest={digest}\n", "")

    monkeypatch.setattr(patched_images.subprocess, "run", fake_run)

    result = patched_images.build_remote("outline", "bash build/patched-images/build_remote.sh outline", secret)

    args = captured["args"]
    env = captured["env"]
    assert args == [str(REPO_ROOT / "scripts" / "remote_exec.sh"), "remote-image-build"]
    assert env["SERVICE"] == "patched-runtime"
    assert env["COMMAND"] == "bash build/patched-images/build_remote.sh outline"
    assert secret not in repr(args)
    assert secret not in repr(env)
    assert captured["secret_file_mode"] == 0o600
    assert captured["secret_file_content"] == secret + "\n"
    assert not Path(env["REMOTE_EXEC_STDIN_FILE"]).exists()
    assert result == digest


def test_affected_service_completeness_contracts_have_no_expired_suppressions() -> None:
    completeness = json.loads((REPO_ROOT / "config" / "service-completeness.json").read_text(encoding="utf-8"))
    glitchtip = completeness["services"]["glitchtip"]
    langfuse = completeness["services"]["langfuse"]
    minio = completeness["services"]["minio"]
    dashboard = json.loads((REPO_ROOT / langfuse["dashboard_file"]).read_text(encoding="utf-8"))
    alerts = yaml.safe_load((REPO_ROOT / langfuse["alert_rule_file"]).read_text(encoding="utf-8"))

    assert glitchtip["suppressed_checks"] == {}
    assert glitchtip["requires_api_gateway"] is False
    assert minio["suppressed_checks"] == {}
    assert minio["requires_api_gateway"] is False
    assert "suppression_preset" not in langfuse
    assert {panel["title"] for panel in dashboard["panels"]} == {
        "Sign-in readiness",
        "Runtime liveness",
        "Probe duration",
    }
    assert {rule["alert"] for rule in alerts["groups"][0]["rules"]} == {"LangfuseReadinessDown", "LangfuseLivenessDown"}


def test_shared_valkey_catalog_records_all_redis_compatible_consumers() -> None:
    catalog = json.loads((REPO_ROOT / "config" / "image-catalog.json").read_text(encoding="utf-8"))
    entry = catalog["images"]["shared_valkey_runtime"]
    expected_consumers = {
        "collections/ansible_collections/lv3/platform/roles/outline_runtime/templates/docker-compose.yml.j2",
        "collections/ansible_collections/lv3/platform/roles/glitchtip_runtime/templates/docker-compose.yml.j2",
        "collections/ansible_collections/lv3/platform/roles/langfuse_runtime/templates/docker-compose.yml.j2",
        "collections/ansible_collections/lv3/platform/roles/paperless_runtime/templates/docker-compose.yml.j2",
    }

    assert expected_consumers.issubset(set(entry["consumers"]))
    assert entry["scan_status"] == "pass_no_critical"
    assert "exception" not in entry
    assert "langfuse_redis_runtime" not in catalog["images"]
    assert "glitchtip_valkey_runtime" not in catalog["images"]
    summary = json.loads((REPO_ROOT / entry["scan_receipt"]).read_text(encoding="utf-8"))
    assert summary["image_ref"] == entry["ref"]
    assert summary["summary"]["critical"] == 0
    assert summary["summary"]["blocking_findings_with_fix"] == 0

    for service_id in ("glitchtip", "outline", "langfuse", "paperless"):
        service = yaml.safe_load((REPO_ROOT / "catalog" / "services" / service_id / "service.yaml").read_text())[
            "service"
        ]
        assert "shared_valkey_runtime" in service["image_catalog_ids"]


def test_harbor_patched_runtime_robots_keep_publish_and_pull_capabilities_separate() -> None:
    role_root = (
        REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "harbor_runtime" / "tasks"
    )
    project_tasks = yaml.safe_load((role_root / "patched_runtime_project.yml").read_text())
    robot_tasks = yaml.safe_load((role_root / "reconcile_patched_runtime_robot.yml").read_text())
    project_create = next(
        task
        for task in project_tasks
        if task["name"] == "Create the private patched-runtime Harbor project when missing"
    )
    robot_loop = next(
        task
        for task in project_tasks
        if task["name"] == "Reconcile the patched-runtime Harbor publisher and puller robots"
    )["loop"]
    runtime_login = next(
        task
        for task in project_tasks
        if task["name"] == "Store pull-only Harbor credentials in the Docker runtime config"
    )

    assert project_create["ansible.builtin.uri"]["body"]["metadata"] == {
        "public": "{{ 'true' if harbor_patched_runtime_project_public else 'false' }}",
        "auto_scan": "true",
        "reuse_sys_cve_allowlist": "false",
    }
    assert robot_loop[0]["actions"] == [
        {"resource": "repository", "action": "pull"},
        {"resource": "repository", "action": "push"},
    ]
    assert robot_loop[1]["actions"] == [{"resource": "repository", "action": "pull"}]
    assert runtime_login["no_log"] is True
    permission_reconcile = next(
        task for task in robot_tasks if task["name"] == "Reconcile the patched-runtime Harbor robot permission set"
    )
    assert permission_reconcile["ansible.builtin.uri"]["method"] == "PUT"
    assert permission_reconcile["no_log"] is True
