from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "runbook-executor.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("runbook_executor_windmill_missing", WRAPPER_PATH)
    payload = module.main(repo_path=str(tmp_path / "missing"), runbook_id="renew-certificate")
    assert payload["status"] == "blocked"


def test_wrapper_imports_repo_executor(tmp_path: Path) -> None:
    module = load_module("runbook_executor_windmill_import", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "runbook_executor.py").write_text(
        """
from pathlib import Path

def default_runner(repo_root: Path):
    return {"repo_root": str(repo_root)}

class RunbookExecutor:
    def __init__(self, repo_root, workflow_runner):
        self.repo_root = repo_root
        self.workflow_runner = workflow_runner

    def execute(self, runbook_id, params, actor_id):
        return {"run_id": "run-1", "runbook_id": runbook_id, "params": params, "actor_id": actor_id, "status": "completed"}

    def resume(self, run_id, actor_id):
        return {"run_id": run_id, "actor_id": actor_id, "status": "completed"}

    def status(self, run_id):
        return {"run_id": run_id, "status": "escalated"}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = module.main(runbook_id="renew-certificate", params={"service": "grafana"}, repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["record"]["runbook_id"] == "renew-certificate"
    assert payload["record"]["params"]["service"] == "grafana"
