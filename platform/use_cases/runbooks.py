from __future__ import annotations

import ast
import json
import re
import sys
import time
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from platform.circuit import CircuitRegistry, should_count_urllib_exception
from platform.mutation_audit import build_event, emit_event_best_effort
from platform.repo import load_json, load_yaml, write_json
from platform.scheduler import HttpWindmillClient


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_DIR = REPO_ROOT / ".local" / "runbooks" / "runs"
DEFAULT_DELIVERY_SURFACES = ("cli", "windmill")
DELIVERY_SURFACE_LABELS = {
    "api_gateway": "API Gateway",
    "cli": "CLI",
    "ops_portal": "Ops Portal",
    "windmill": "Windmill",
}
LIVE_IMPACT_ORDER = {
    "repo_only": 0,
    "private_only": 1,
    "guest_live": 2,
    "edge_published": 3,
}
TEMPLATE_PATTERN = re.compile(r"{{\s*(.+?)\s*}}")
MARKDOWN_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


class RunbookSurfaceError(PermissionError):
    """Raised when a runbook is not exposed on the requested delivery surface."""


class AttrView(dict):
    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:  # pragma: no cover - simple helper
            raise AttributeError(item) from exc


class WorkflowRunner(Protocol):
    def run_workflow(self, workflow_id: str, payload: dict[str, Any], *, timeout_seconds: int | None = None) -> Any:
        ...


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def viewify(value: Any) -> Any:
    if isinstance(value, dict):
        return AttrView({key: viewify(item) for key, item in value.items()})
    if isinstance(value, list):
        return [viewify(item) for item in value]
    return value


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def safe_step_alias(step_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", step_id)


def expression_context(
    *,
    params: dict[str, Any],
    run_record: dict[str, Any],
    step_results: dict[str, Any],
    workflow_result: Any,
) -> dict[str, Any]:
    aliased_steps = {safe_step_alias(step_id): value for step_id, value in step_results.items()}
    return {
        "params": viewify(params),
        "result": viewify(workflow_result),
        "run": viewify(run_record),
        "steps": viewify(step_results),
        "steps_alias": viewify(aliased_steps),
    }


class SafeExpressionVisitor(ast.NodeVisitor):
    ALLOWED_NODES = (
        ast.Expression,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Load,
        ast.Name,
        ast.Attribute,
        ast.Subscript,
        ast.Constant,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.USub,
        ast.UAdd,
    )

    def __init__(self, *, allowed_names: set[str]) -> None:
        self.allowed_names = allowed_names

    def visit_Name(self, node: ast.Name) -> None:
        if node.id not in self.allowed_names:
            raise ValueError(f"unsupported name in expression: {node.id}")

    def visit_Call(self, node: ast.Call) -> None:
        raise ValueError("function calls are not allowed in runbook expressions")

    def visit(self, node: ast.AST) -> None:
        if not isinstance(node, self.ALLOWED_NODES):
            raise ValueError(f"unsupported expression node: {node.__class__.__name__}")
        super().visit(node)


def normalize_expression(expression: str, step_ids: list[str]) -> str:
    normalized = expression
    for step_id in sorted(step_ids, key=len, reverse=True):
        normalized = re.sub(
            rf"\bsteps\.{re.escape(step_id)}(?=\.|\[|$)",
            f'steps["{step_id}"]',
            normalized,
        )
        normalized = re.sub(
            rf"\bsteps_alias\.{re.escape(safe_step_alias(step_id))}(?=\.|\[|$)",
            f'steps_alias["{safe_step_alias(step_id)}"]',
            normalized,
        )
    return normalized


def evaluate_expression(expression: str, context: dict[str, Any], *, step_ids: list[str]) -> Any:
    normalized = normalize_expression(expression, step_ids)
    tree = ast.parse(normalized, mode="eval")
    SafeExpressionVisitor(allowed_names=set(context)).visit(tree)
    return eval(compile(tree, "<runbook-expression>", "eval"), {"__builtins__": {}}, context)


def render_template_value(value: Any, context: dict[str, Any], *, step_ids: list[str]) -> Any:
    if isinstance(value, dict):
        return {key: render_template_value(item, context, step_ids=step_ids) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template_value(item, context, step_ids=step_ids) for item in value]
    if not isinstance(value, str):
        return value

    single = re.fullmatch(r"\s*{{\s*(.+?)\s*}}\s*", value, re.DOTALL)
    if single:
        return evaluate_expression(single.group(1), context, step_ids=step_ids)

    def replace(match: re.Match[str]) -> str:
        rendered = evaluate_expression(match.group(1), context, step_ids=step_ids)
        if rendered is None:
            return ""
        if isinstance(rendered, (dict, list)):
            return json.dumps(rendered, sort_keys=True)
        return str(rendered)

    return TEMPLATE_PATTERN.sub(replace, value)


def preview_template_value(value: Any, context: dict[str, Any], *, step_ids: list[str]) -> Any:
    try:
        return render_template_value(value, context, step_ids=step_ids)
    except Exception:
        return value


def load_yaml_from_text(text: str, path: Path) -> Any:
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(f"PyYAML is required to parse {path}") from exc
    return yaml.safe_load(text) or {}


def parse_runbook_payload(path: Path) -> dict[str, Any]:
    if path.suffix in {".yaml", ".yml"}:
        payload = load_yaml(path)
    elif path.suffix == ".json":
        payload = load_json(path)
    elif path.suffix == ".md":
        match = MARKDOWN_FRONT_MATTER.match(path.read_text(encoding="utf-8"))
        if not match:
            raise ValueError(f"{path} does not start with YAML front matter")
        payload = load_yaml_from_text(match.group(1), path)
    else:
        raise ValueError(f"unsupported runbook file type: {path.suffix}")
    payload = require_mapping(payload, f"{path}")
    payload["source_path"] = str(path)
    payload.setdefault("automation", {})
    payload.setdefault("steps", [])
    return payload


def normalize_delivery_surfaces(automation: dict[str, Any], *, path: str) -> list[str]:
    surfaces: Any = automation.get("delivery_surfaces")
    if surfaces is None:
        legacy_surface = automation.get("delivery_surface")
        if legacy_surface is not None:
            surfaces = [legacy_surface]
    if surfaces is None:
        return list(DEFAULT_DELIVERY_SURFACES)
    if not isinstance(surfaces, list) or not surfaces:
        raise ValueError(f"{path}.delivery_surfaces must be a non-empty list when present")
    normalized: list[str] = []
    for index, item in enumerate(surfaces):
        surface = require_string(item, f"{path}.delivery_surfaces[{index}]")
        if surface == "portal":
            surface = "ops_portal"
        if surface not in DELIVERY_SURFACE_LABELS:
            raise ValueError(
                f"{path}.delivery_surfaces[{index}] must be one of: {', '.join(sorted(DELIVERY_SURFACE_LABELS))}"
            )
        if surface not in normalized:
            normalized.append(surface)
    return normalized


def validate_runbook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    runbook_id = require_string(payload.get("id"), "runbook.id")
    require_string(payload.get("title"), "runbook.title")
    raw_automation = require_mapping(payload.get("automation") or {}, "runbook.automation")
    normalized_automation = deepcopy(raw_automation)
    normalized_automation["eligible"] = bool(raw_automation.get("eligible"))
    normalized_automation["delivery_surfaces"] = normalize_delivery_surfaces(
        raw_automation,
        path="runbook.automation",
    )
    if "description" in raw_automation:
        normalized_automation["description"] = require_string(raw_automation.get("description"), "runbook.automation.description")
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("runbook.steps must be a non-empty list")

    seen_step_ids: set[str] = set()
    normalized_steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(steps):
        step = require_mapping(raw_step, f"runbook.steps[{index}]")
        step_id = require_string(step.get("id"), f"runbook.steps[{index}].id")
        if step_id in seen_step_ids:
            raise ValueError(f"duplicate runbook step id: {step_id}")
        seen_step_ids.add(step_id)
        workflow_id = step.get("workflow_id")
        if workflow_id is not None:
            workflow_id = require_string(workflow_id, f"runbook.steps[{index}].workflow_id")
        elif step.get("type") != "pause":
            raise ValueError(f"runbook.steps[{index}].workflow_id is required")
        normalized_steps.append(
            {
                "id": step_id,
                "type": str(step.get("type") or "mutation"),
                "description": str(step.get("description") or step_id),
                "workflow_id": workflow_id,
                "params": require_mapping(step.get("params") or {}, f"runbook.steps[{index}].params"),
                "success_condition": step.get("success_condition"),
                "on_failure": str(step.get("on_failure") or "escalate"),
                "wait_seconds": int(step.get("wait_seconds") or 0),
                "timeout_seconds": int(step.get("timeout_seconds") or 30),
                "rollback_workflow_id": step.get("rollback_workflow_id"),
            }
        )

    return {
        "id": runbook_id,
        "title": payload["title"],
        "automation": normalized_automation,
        "rollback_workflow_id": payload.get("rollback_workflow_id"),
        "steps": normalized_steps,
        "source_path": payload.get("source_path"),
    }


class RunbookRegistry:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.search_roots = [repo_root / "docs" / "runbooks", repo_root / "config" / "runbooks"]

    def resolve(self, identifier: str, *, surface: str | None = None) -> dict[str, Any]:
        candidate = Path(identifier).expanduser()
        if candidate.exists():
            runbook = validate_runbook_payload(parse_runbook_payload(candidate))
            self._assert_surface_allowed(runbook, surface=surface)
            return runbook

        for path in self._iter_candidates():
            if path.stem == identifier:
                runbook = validate_runbook_payload(parse_runbook_payload(path))
                self._assert_surface_allowed(runbook, surface=surface)
                return runbook
            try:
                payload = parse_runbook_payload(path)
            except ValueError:
                continue
            if payload.get("id") == identifier:
                runbook = validate_runbook_payload(payload)
                self._assert_surface_allowed(runbook, surface=surface)
                return runbook
        raise FileNotFoundError(f"runbook not found: {identifier}")

    def list_available(self, *, surface: str | None = None) -> list[dict[str, Any]]:
        runbooks: list[dict[str, Any]] = []
        for path in self._iter_candidates():
            try:
                runbook = validate_runbook_payload(parse_runbook_payload(path))
            except ValueError:
                continue
            automation = runbook.get("automation") or {}
            if not bool(automation.get("eligible")):
                continue
            if surface is not None and surface not in automation.get("delivery_surfaces", []):
                continue
            runbooks.append(runbook)
        return sorted(runbooks, key=lambda item: item["id"])

    def _assert_surface_allowed(self, runbook: dict[str, Any], *, surface: str | None) -> None:
        if surface is None:
            return
        allowed = runbook.get("automation", {}).get("delivery_surfaces", [])
        if surface not in allowed:
            raise RunbookSurfaceError(
                f"runbook '{runbook['id']}' is not exposed on the {surface!r} delivery surface"
            )

    def _iter_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        for root in self.search_roots:
            if not root.exists():
                continue
            for suffix in ("*.yaml", "*.yml", "*.json", "*.md"):
                candidates.extend(sorted(root.rglob(suffix)))
        return candidates


class RunbookRunStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DEFAULT_RUNS_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"

    def load(self, run_id: str) -> dict[str, Any]:
        return require_mapping(load_json(self.path_for(run_id)), f"run {run_id}")

    def save(self, record: dict[str, Any]) -> dict[str, Any]:
        record["updated_at"] = utc_now_iso()
        write_json(self.path_for(require_string(record.get("run_id"), "run.run_id")), record, sort_keys=False)
        return record


class WindmillWorkflowRunner:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        workspace: str = "lv3",
        circuit_breaker: Any | None = None,
        circuit_registry: CircuitRegistry | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.workspace = workspace
        self.repo_root = repo_root
        self.circuit_breaker = circuit_breaker
        if self.circuit_breaker is None:
            registry = circuit_registry or CircuitRegistry(repo_root or REPO_ROOT)
            if registry.has_policy("windmill"):
                self.circuit_breaker = registry.sync_breaker(
                    "windmill",
                    exception_classifier=should_count_urllib_exception,
                )
        self._client = HttpWindmillClient(
            base_url=self.base_url,
            token=self.token,
            workspace=self.workspace,
            circuit_breaker=self.circuit_breaker,
        )

    def run_workflow(self, workflow_id: str, payload: dict[str, Any], *, timeout_seconds: int | None = None) -> Any:
        submission = self._client.submit_workflow(workflow_id, payload, timeout_seconds=timeout_seconds)
        if submission.get("completed"):
            return submission.get("result")

        job_id = submission.get("job_id") or submission.get("id")
        if not isinstance(job_id, str) or not job_id.strip():
            raise RuntimeError(f"Windmill submit_workflow returned no job id: {submission!r}")

        deadline = time.monotonic() + float(timeout_seconds or 30)
        while time.monotonic() < deadline:
            status = self._client.get_job(job_id)
            if status.get("type") == "CompletedJob" or status.get("success") is not None:
                if status.get("success") is False:
                    details = status.get("result") or status.get("logs") or status
                    raise RuntimeError(f"Windmill job {job_id} failed: {details!r}")
                return status.get("result")
            time.sleep(2)
        raise TimeoutError(f"Windmill job {job_id} did not complete within {timeout_seconds or 30} seconds")


class RunbookUseCaseService:
    def __init__(
        self,
        *,
        repo_root: Path,
        workflow_runner: WorkflowRunner,
        registry: RunbookRegistry | None = None,
        store: RunbookRunStore | None = None,
        sleep_fn: Any = time.sleep,
        stderr: Any = sys.stderr,
    ) -> None:
        self.repo_root = repo_root
        self.workflow_runner = workflow_runner
        self.registry = registry or RunbookRegistry(repo_root)
        self.store = store or RunbookRunStore(repo_root / ".local" / "runbooks" / "runs")
        self.sleep_fn = sleep_fn
        self.stderr = stderr
        self.workflow_catalog = self._load_workflow_catalog()

    def list_runbooks(self, *, surface: str) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for runbook in self.registry.list_available(surface=surface):
            live_impact = "repo_only"
            execution_class = "diagnostic"
            for step in runbook["steps"]:
                workflow = self.workflow_catalog.get(step.get("workflow_id"), {})
                candidate_impact = str(workflow.get("live_impact") or "repo_only")
                if LIVE_IMPACT_ORDER.get(candidate_impact, 0) > LIVE_IMPACT_ORDER.get(live_impact, 0):
                    live_impact = candidate_impact
                candidate_class = str(workflow.get("execution_class") or step.get("type") or "diagnostic")
                if candidate_class == "mutation" or step.get("type") == "mutation":
                    execution_class = "mutation"
            source_path = str(runbook.get("source_path") or "")
            summaries.append(
                {
                    "id": runbook["id"],
                    "title": runbook["title"],
                    "description": runbook["automation"].get("description") or runbook["title"],
                    "owner_runbook": self._relative_repo_path(source_path),
                    "source_path": source_path,
                    "delivery_surfaces": list(runbook["automation"].get("delivery_surfaces") or []),
                    "execution_class": execution_class,
                    "live_impact": live_impact,
                    "step_count": len(runbook["steps"]),
                }
            )
        return summaries

    def preview(self, runbook_ref: str, params: dict[str, Any], *, surface: str = "cli") -> dict[str, Any]:
        runbook = self.registry.resolve(runbook_ref, surface=surface)
        step_results: dict[str, Any] = {}
        rendered_steps = []
        run_record = {
            "run_id": "preview",
            "runbook_id": runbook["id"],
            "runbook_title": runbook["title"],
            "params": deepcopy(params),
            "delivery_surface": surface,
        }
        step_ids = [step["id"] for step in runbook["steps"]]
        for step in runbook["steps"]:
            context = expression_context(params=params, run_record=run_record, step_results=step_results, workflow_result={})
            rendered_params = preview_template_value(step["params"], context, step_ids=step_ids)
            rendered_steps.append(
                {
                    "id": step["id"],
                    "workflow_id": step["workflow_id"],
                    "on_failure": step["on_failure"],
                    "wait_seconds": step["wait_seconds"],
                    "params": rendered_params,
                }
            )
            step_results[step["id"]] = {"result": {}}
        return {"runbook": runbook, "steps": rendered_steps}

    def execute(
        self,
        runbook_ref: str,
        params: dict[str, Any],
        *,
        actor_id: str = "operator:lv3-cli",
        surface: str = "cli",
    ) -> dict[str, Any]:
        runbook = self.registry.resolve(runbook_ref, surface=surface)
        run_record = {
            "run_id": f"runbook-{uuid.uuid4()}",
            "runbook_id": runbook["id"],
            "runbook_title": runbook["title"],
            "runbook_source": runbook["source_path"],
            "actor_id": actor_id,
            "delivery_surface": surface,
            "status": "running",
            "params": deepcopy(params),
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "current_step": None,
            "next_step_index": 0,
            "step_results": {},
            "history": [],
        }
        self.store.save(run_record)
        self._emit_audit(
            "runbook.execute.started",
            runbook["id"],
            actor_id=actor_id,
            outcome="success",
            evidence_ref=str(self.store.path_for(run_record["run_id"])),
        )
        return self._run_steps(runbook, run_record)

    def resume(self, run_id: str, *, actor_id: str = "operator:lv3-cli") -> dict[str, Any]:
        run_record = self.store.load(run_id)
        if run_record.get("status") != "escalated":
            raise ValueError(f"run {run_id} is not escalated")
        runbook = self.registry.resolve(str(run_record.get("runbook_source") or run_record["runbook_id"]))
        run_record["status"] = "running"
        run_record["actor_id"] = actor_id
        self.store.save(run_record)
        self._emit_audit(
            "runbook.execute.resumed",
            run_record["runbook_id"],
            actor_id=actor_id,
            outcome="success",
            evidence_ref=str(self.store.path_for(run_id)),
        )
        return self._run_steps(runbook, run_record)

    def status(self, run_id: str) -> dict[str, Any]:
        return self.store.load(run_id)

    def _run_steps(self, runbook: dict[str, Any], run_record: dict[str, Any]) -> dict[str, Any]:
        steps = runbook["steps"]
        step_ids = [step["id"] for step in steps]
        start_index = int(run_record.get("next_step_index") or 0)

        for index in range(start_index, len(steps)):
            step = steps[index]
            run_record["current_step"] = step["id"]
            run_record["next_step_index"] = index
            self.store.save(run_record)
            outcome = self._execute_step(runbook, step, run_record, step_ids=step_ids)
            run_record["step_results"][step["id"]] = outcome
            run_record["history"].append(
                {
                    "step_id": step["id"],
                    "status": outcome["status"],
                    "attempts": outcome["attempts"],
                    "finished_at": outcome["finished_at"],
                }
            )
            self.store.save(run_record)
            if outcome["status"] == "escalated":
                run_record["status"] = "escalated"
                self.store.save(run_record)
                return run_record
            if outcome["status"] == "failed":
                run_record["status"] = "failed"
                self.store.save(run_record)
                return run_record

        run_record["status"] = "completed"
        run_record["current_step"] = None
        run_record["next_step_index"] = len(steps)
        self.store.save(run_record)
        self._emit_audit(
            "runbook.execute.completed",
            runbook["id"],
            actor_id=run_record["actor_id"],
            outcome="success",
            evidence_ref=str(self.store.path_for(run_record["run_id"])),
        )
        return run_record

    def _execute_step(
        self,
        runbook: dict[str, Any],
        step: dict[str, Any],
        run_record: dict[str, Any],
        *,
        step_ids: list[str],
    ) -> dict[str, Any]:
        previous_attempts = int((run_record.get("step_results") or {}).get(step["id"], {}).get("attempts") or 0)
        attempts = previous_attempts
        last_error: str | None = None
        last_result: Any = None
        while True:
            attempts += 1
            started_at = utc_now_iso()
            context = expression_context(
                params=run_record["params"],
                run_record=run_record,
                step_results=run_record["step_results"],
                workflow_result=last_result or {},
            )
            rendered_params = render_template_value(step["params"], context, step_ids=step_ids)

            try:
                self._validate_workflow(step["workflow_id"])
                if step["wait_seconds"] > 0:
                    self.sleep_fn(step["wait_seconds"])
                last_result = self.workflow_runner.run_workflow(
                    step["workflow_id"],
                    rendered_params,
                    timeout_seconds=step["timeout_seconds"],
                )
                succeeded = self._evaluate_success_condition(
                    step["success_condition"],
                    run_record=run_record,
                    params=run_record["params"],
                    step_results=run_record["step_results"],
                    workflow_result=last_result,
                    step_ids=step_ids,
                )
                if succeeded:
                    self._emit_audit(
                        f"runbook.step.{safe_step_alias(step['id'])}",
                        runbook["id"],
                        actor_id=run_record["actor_id"],
                        outcome="success",
                        evidence_ref=str(self.store.path_for(run_record["run_id"])),
                    )
                    return {
                        "step_id": step["id"],
                        "status": "completed",
                        "attempts": attempts,
                        "workflow_id": step["workflow_id"],
                        "params": rendered_params,
                        "result": last_result,
                        "started_at": started_at,
                        "finished_at": utc_now_iso(),
                    }
                last_error = f"success condition failed for step {step['id']}"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

            action = step["on_failure"]
            if action == "retry_once" and attempts == 1:
                continue
            if action == "skip" and step["type"] == "diagnostic":
                return {
                    "step_id": step["id"],
                    "status": "skipped",
                    "attempts": attempts,
                    "workflow_id": step["workflow_id"],
                    "params": rendered_params,
                    "result": last_result,
                    "error": last_error,
                    "started_at": started_at,
                    "finished_at": utc_now_iso(),
                }
            if action == "continue":
                return {
                    "step_id": step["id"],
                    "status": "warning",
                    "attempts": attempts,
                    "workflow_id": step["workflow_id"],
                    "params": rendered_params,
                    "result": last_result,
                    "error": last_error,
                    "started_at": started_at,
                    "finished_at": utc_now_iso(),
                }
            if action == "rollback":
                rollback_workflow = step.get("rollback_workflow_id") or runbook.get("rollback_workflow_id")
                if rollback_workflow:
                    rollback_payload = {
                        "run_id": run_record["run_id"],
                        "runbook_id": runbook["id"],
                        "failed_step_id": step["id"],
                        "failed_result": last_result,
                    }
                    try:
                        self.workflow_runner.run_workflow(
                            rollback_workflow,
                            rollback_payload,
                            timeout_seconds=step["timeout_seconds"],
                        )
                    except Exception as exc:  # noqa: BLE001
                        last_error = f"{last_error}; rollback failed: {exc}"
                action = "escalate"

            if action == "escalate":
                self._emit_audit(
                    f"runbook.step.{safe_step_alias(step['id'])}",
                    runbook["id"],
                    actor_id=run_record["actor_id"],
                    outcome="failure",
                    evidence_ref=str(self.store.path_for(run_record["run_id"])),
                )
                return {
                    "step_id": step["id"],
                    "status": "escalated",
                    "attempts": attempts,
                    "workflow_id": step["workflow_id"],
                    "params": rendered_params,
                    "result": last_result,
                    "error": last_error,
                    "started_at": started_at,
                    "finished_at": utc_now_iso(),
                }

            return {
                "step_id": step["id"],
                "status": "failed",
                "attempts": attempts,
                "workflow_id": step["workflow_id"],
                "params": rendered_params,
                "result": last_result,
                "error": last_error,
                "started_at": started_at,
                "finished_at": utc_now_iso(),
            }

    def _evaluate_success_condition(
        self,
        expression: Any,
        *,
        run_record: dict[str, Any],
        params: dict[str, Any],
        step_results: dict[str, Any],
        workflow_result: Any,
        step_ids: list[str],
    ) -> bool:
        if expression in (None, ""):
            return True
        if not isinstance(expression, str):
            raise ValueError("success_condition must be a string or null")
        context = expression_context(
            params=params,
            run_record=run_record,
            step_results=step_results,
            workflow_result=workflow_result,
        )
        value = evaluate_expression(expression, context, step_ids=step_ids)
        return bool(value)

    def _load_workflow_catalog(self) -> dict[str, Any]:
        catalog_path = self.repo_root / "config" / "workflow-catalog.json"
        if not catalog_path.exists():
            return {}
        payload = load_json(catalog_path)
        workflows = payload.get("workflows")
        return workflows if isinstance(workflows, dict) else {}

    def _validate_workflow(self, workflow_id: str | None) -> None:
        if workflow_id is None:
            return
        if "/" in workflow_id:
            return
        if self.workflow_catalog and workflow_id not in self.workflow_catalog:
            raise ValueError(f"workflow not found in catalog: {workflow_id}")

    def _relative_repo_path(self, source_path: str) -> str:
        if not source_path:
            return ""
        path = Path(source_path)
        try:
            return str(path.relative_to(self.repo_root))
        except ValueError:
            return source_path

    def _emit_audit(self, action: str, target: str, *, actor_id: str, outcome: str, evidence_ref: str) -> None:
        event = build_event(
            actor_class="automation",
            actor_id=actor_id,
            surface="windmill",
            action=action,
            target=target,
            outcome=outcome,
            evidence_ref=evidence_ref,
        )
        emit_event_best_effort(event, context="runbook-executor", stderr=self.stderr)


class RunbookExecutor(RunbookUseCaseService):
    """Backward-compatible alias for the shared runbook use-case service."""


def render_status(record: dict[str, Any]) -> str:
    lines = [
        f"Run ID: {record['run_id']}",
        f"Runbook: {record['runbook_id']}",
        f"Status: {record['status']}",
        f"Current step: {record.get('current_step') or '-'}",
    ]
    steps = record.get("step_results") or {}
    if not steps:
        lines.append("Steps: none")
        return "\n".join(lines)
    lines.append("Steps:")
    for step_id, outcome in steps.items():
        status = outcome.get("status", "unknown")
        attempts = outcome.get("attempts", 0)
        detail = outcome.get("error") or ""
        lines.append(f"  - {step_id}: {status} (attempts={attempts}) {detail}".rstrip())
    return "\n".join(lines)


__all__ = [
    "RunbookExecutor",
    "RunbookRegistry",
    "RunbookRunStore",
    "RunbookSurfaceError",
    "RunbookUseCaseService",
    "WindmillWorkflowRunner",
    "parse_runbook_payload",
    "render_status",
    "validate_runbook_payload",
]
