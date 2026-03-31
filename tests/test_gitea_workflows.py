from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "validate.yml"
RENOVATE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "renovate.yml"
RELEASE_BUNDLE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "release-bundle.yml"
PYTHON_RUNNER_IMAGE = (
    "registry.lv3.org/check-runner/python:3.12.10"
    "@sha256:9dd2ea22539ed61d0aed774d0f29d2a2de674531b80f852484849500d64169ff"
)
SHALLOW_MANUAL_CHECKOUT_FETCH = (
    'git -c http.extraHeader="Authorization: token ${WORKFLOW_TOKEN}" '
    'fetch --depth=1 origin "${WORKFLOW_REF}"'
)
VALIDATE_CHECKOUT_FETCH = (
    'git -c http.extraHeader="Authorization: token ${WORKFLOW_TOKEN}" '
    'fetch origin "${WORKFLOW_REF}"'
)
VALIDATE_MAIN_FETCH = (
    'git -c http.extraHeader="Authorization: token ${WORKFLOW_TOKEN}" '
    "fetch origin main"
)


def test_validate_workflow_uses_pinned_python_runner_and_manual_checkout() -> None:
    workflow = VALIDATE_WORKFLOW.read_text(encoding="utf-8")

    assert PYTHON_RUNNER_IMAGE in workflow
    assert "uses: actions/checkout@v4" not in workflow
    assert "uses: actions/setup-python@v5" not in workflow
    assert "uses: actions/upload-artifact@v4" not in workflow
    assert VALIDATE_CHECKOUT_FETCH in workflow
    assert VALIDATE_MAIN_FETCH in workflow
    assert "--depth=1" not in workflow
    assert 'git checkout --force "${WORKFLOW_SHA}"' in workflow
    assert "Bootstrap validation toolchain" in workflow
    assert "apt-get install -y --no-install-recommends docker-cli" in workflow
    assert "docker-bin.path" in workflow
    assert 'current_container_id="${HOSTNAME:-$(hostname)}"' in workflow
    assert "cgroup_container_id" in workflow
    assert 'inspect "${candidate}"' in workflow
    assert 'name=WORKFLOW-validate_JOB-validate' in workflow
    assert "workspace-host.path" in workflow
    assert "Bundle validation artifacts" in workflow
    assert '--docker-binary "${DOCKER_BIN}"' in workflow
    assert 'LV3_DOCKER_WORKSPACE_PATH="$(cat .local/validation-gate/workspace-host.path)"' in workflow
    assert "gitea-validation-receipts.tar.gz" in workflow


def test_release_bundle_workflow_uses_pinned_python_runner_and_manual_checkout() -> None:
    workflow = RELEASE_BUNDLE_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count(PYTHON_RUNNER_IMAGE) == 2
    assert "uses: actions/checkout@v4" not in workflow
    assert workflow.count(SHALLOW_MANUAL_CHECKOUT_FETCH) == 2
    assert workflow.count('git checkout --force "${WORKFLOW_SHA}"') == 2


def test_renovate_workflow_bootstraps_inside_pinned_python_runner() -> None:
    workflow = RENOVATE_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count(PYTHON_RUNNER_IMAGE) == 2
    assert "uses: actions/checkout@v4" not in workflow
    assert SHALLOW_MANUAL_CHECKOUT_FETCH in workflow
    assert 'git checkout --force "${WORKFLOW_SHA}"' in workflow
    assert "/var/run/docker.sock:/var/run/docker.sock" not in workflow
    assert "apt-get install -y --no-install-recommends docker-cli" in workflow
    assert "hash -r" in workflow
    assert "Bootstrap Docker CLI and discover runner host paths" in workflow
    assert 'current_container_id="${HOSTNAME:-$(hostname)}"' in workflow
    assert "cgroup_container_id" in workflow
    assert 'inspect "${candidate}"' in workflow
    assert 'name=WORKFLOW-renovate_JOB-renovate' in workflow
    assert '/var/run/lv3/renovate' in workflow
    assert ".tmp/docker-bin.path" in workflow
    assert 'docker_bin="$(ensure_docker_bin)"' not in workflow
    assert workflow.count("ensure_docker_bin") >= 8
    assert workflow.count("resolve_docker_bin") >= 8
    assert 'test -d "${workspace_host_path}"' not in workflow
    assert 'test -s "${bootstrap_host_dir}/renovate.env"' not in workflow
    assert '.tmp/workspace-host.path' in workflow
    assert '.tmp/bootstrap-host.path' in workflow
    assert 'renovate_add_host_arg=""' in workflow
    assert 'RENOVATE_GIT_CLONE_HOST:-' in workflow
    assert 'RENOVATE_GIT_CLONE_HOST_ADDRESS:-' in workflow
    assert '--add-host=${RENOVATE_GIT_CLONE_HOST}:${RENOVATE_GIT_CLONE_HOST_ADDRESS}' in workflow
    assert '-v "${bootstrap_host_dir}:/var/run/lv3/renovate:ro"' in workflow
    assert '"${docker_bin}" run --rm \\' in workflow
    assert '"${docker_bin}" pull "${RENOVATE_IMAGE}"' in workflow
