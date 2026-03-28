from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .toolchain import PolicyToolchain, ensure_policy_toolchain


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = REPO_ROOT / "policy"


class PolicyEvaluationError(RuntimeError):
    """Raised when ADR 0230 policy evaluation cannot complete."""


def _extract_opa_value(payload: dict[str, Any], query: str) -> Any:
    results = payload.get("result", [])
    if not results:
        raise PolicyEvaluationError(f"OPA returned no result for query {query}")
    expressions = results[0].get("expressions", [])
    if not expressions:
        raise PolicyEvaluationError(f"OPA returned no expressions for query {query}")
    if "value" not in expressions[0]:
        raise PolicyEvaluationError(f"OPA returned no value for query {query}")
    return expressions[0]["value"]


def evaluate_policy_query(
    *,
    query: str,
    input_payload: dict[str, Any],
    repo_root: Path | None = None,
    toolchain: PolicyToolchain | None = None,
) -> Any:
    effective_repo_root = repo_root.resolve() if repo_root is not None else REPO_ROOT
    effective_policy_root = effective_repo_root / "policy"
    effective_toolchain = toolchain or ensure_policy_toolchain(repo_root=effective_repo_root)
    command = [
        str(effective_toolchain.opa.path),
        "eval",
        "--format=json",
        "--stdin-input",
        "--data",
        str(effective_policy_root),
        query,
    ]
    result = subprocess.run(
        command,
        cwd=effective_repo_root,
        input=json.dumps(input_payload),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise PolicyEvaluationError(
            f"OPA evaluation failed for {query}: {(result.stderr or result.stdout).strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PolicyEvaluationError(f"OPA returned invalid JSON for {query}: {exc}") from exc
    return _extract_opa_value(payload, query)


def evaluate_command_approval_policy(
    input_payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
    toolchain: PolicyToolchain | None = None,
) -> dict[str, Any]:
    value = evaluate_policy_query(
        query="data.lv3.command.approval.decision",
        input_payload=input_payload,
        repo_root=repo_root,
        toolchain=toolchain,
    )
    if not isinstance(value, dict):
        raise PolicyEvaluationError("ADR 0230 command approval policy returned a non-object decision")
    return value


def evaluate_promotion_gate_policy(
    input_payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
    toolchain: PolicyToolchain | None = None,
) -> dict[str, Any]:
    value = evaluate_policy_query(
        query="data.lv3.release.promotion.decision",
        input_payload=input_payload,
        repo_root=repo_root,
        toolchain=toolchain,
    )
    if not isinstance(value, dict):
        raise PolicyEvaluationError("ADR 0230 promotion policy returned a non-object decision")
    return value
