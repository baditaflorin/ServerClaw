import subprocess
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


def extract_run_block(workflow: str, *, step_name: str) -> str:
    marker = f"      - name: {step_name}\n"
    start = workflow.index(marker)
    sub = workflow[start:]
    run_marker = "        run: |\n"
    run_start = sub.index(run_marker) + len(run_marker)
    body: list[str] = []
    for line in sub[run_start:].splitlines():
        if line.startswith("      - name: "):
            break
        if line.startswith("          "):
            body.append(line[10:])
        elif line == "":
            body.append("")
        else:
            body.append(line)
    return "\n".join(body) + "\n"


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
    run_block = extract_run_block(workflow, step_name="Run Renovate through the pinned Harbor image")

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
    assert 'RENOVATE_GIT_CLONE_HOST_PORT:-' in workflow
    assert 'RENOVATE_GIT_CLONE_TARGET_HOST:-' in workflow
    assert 'RENOVATE_GIT_CLONE_TARGET_PORT:-' in workflow
    assert '--add-host=${RENOVATE_GIT_CLONE_HOST}:${RENOVATE_GIT_CLONE_HOST_ADDRESS}' in workflow
    assert "cleanup_clone_proxy()" in workflow
    assert "python3 - <<'PY' &" in workflow
    assert "ThreadedTCPServer" in workflow
    assert "Renovate clone relay did not become ready." in workflow
    assert '-v "${bootstrap_host_dir}:/var/run/lv3/renovate:ro"' in workflow
    assert '"${docker_bin}" run --rm \\' in workflow
    assert '"${docker_bin}" pull "${RENOVATE_IMAGE}"' in workflow
    assert "python3 - <<'PY' &\nimport os\n" in run_block
    assert "python3 - <<'PY'\nimport os\n" in run_block


def test_renovate_workflow_run_block_is_shell_syntax_valid(tmp_path: Path) -> None:
    workflow = RENOVATE_WORKFLOW.read_text(encoding="utf-8")
    script_path = tmp_path / "renovate-run.sh"
    script_path.write_text(
        extract_run_block(workflow, step_name="Run Renovate through the pinned Harbor image"),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
