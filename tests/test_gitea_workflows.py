from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "validate.yml"
RENOVATE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "renovate.yml"
RELEASE_BUNDLE_WORKFLOW = REPO_ROOT / ".gitea" / "workflows" / "release-bundle.yml"
PYTHON_RUNNER_IMAGE = (
    "registry.lv3.org/check-runner/python:3.12.10"
    "@sha256:46d20437274843950b96491eecd061156f8e23cba5e4514bfec336b64d913acb"
)
MANUAL_CHECKOUT_FETCH = (
    'git -c http.extraHeader="Authorization: token ${WORKFLOW_TOKEN}" '
    'fetch --depth=1 origin "${WORKFLOW_REF}"'
)


def test_validate_workflow_uses_pinned_python_runner_and_manual_checkout() -> None:
    workflow = VALIDATE_WORKFLOW.read_text(encoding="utf-8")

    assert PYTHON_RUNNER_IMAGE in workflow
    assert "uses: actions/checkout@v4" not in workflow
    assert MANUAL_CHECKOUT_FETCH in workflow
    assert 'git checkout --force "${WORKFLOW_SHA}"' in workflow


def test_release_bundle_workflow_uses_pinned_python_runner_and_manual_checkout() -> None:
    workflow = RELEASE_BUNDLE_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count(PYTHON_RUNNER_IMAGE) == 2
    assert "uses: actions/checkout@v4" not in workflow
    assert workflow.count(MANUAL_CHECKOUT_FETCH) == 2
    assert workflow.count('git checkout --force "${WORKFLOW_SHA}"') == 2


def test_renovate_workflow_bootstraps_inside_pinned_python_runner() -> None:
    workflow = RENOVATE_WORKFLOW.read_text(encoding="utf-8")

    assert PYTHON_RUNNER_IMAGE in workflow
    assert "uses: actions/checkout@v4" not in workflow
    assert MANUAL_CHECKOUT_FETCH in workflow
    assert 'git checkout --force "${WORKFLOW_SHA}"' in workflow
    assert "/var/run/docker.sock:/var/run/docker.sock" in workflow
    assert "apt-get install -y --no-install-recommends docker.io" in workflow
