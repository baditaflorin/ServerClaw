#!/usr/bin/env python3
"""Windmill wrapper for the ADR 0126 observation-to-action closure loop."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


def main(
    findings: list[dict[str, Any]] | None = None,
    source: str = "controller-observation-loop",
    repo_path: str = "/srv/proxmox_florin_server",
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    try:
        import yaml  # noqa: F401
    except ModuleNotFoundError:
        script_path = repo_root / "config" / "windmill" / "scripts" / "platform-observation-loop.py"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(findings or [], handle)
            findings_path = Path(handle.name)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            output_path = Path(handle.name)
        command = [
            "uv",
            "run",
            "--with",
            "pyyaml",
            "--with",
            "nats-py",
            "python",
            str(script_path),
            "--repo-path",
            str(repo_root),
            "--source",
            source,
            "--findings-file",
            str(findings_path),
            "--output-file",
            str(output_path),
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
        result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
        findings_path.unlink(missing_ok=True)
        output = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else result.stdout.strip()
        output_path.unlink(missing_ok=True)
        if result.returncode != 0:
            return {
                "status": "error",
                "command": " ".join(shlex.quote(part) for part in command),
                "returncode": result.returncode,
                "stdout": output,
                "stderr": result.stderr.strip(),
            }
        if not output:
            return {
                "status": "error",
                "reason": "fallback subprocess produced no JSON output",
                "command": " ".join(shlex.quote(part) for part in command),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        return json.loads(output)

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
        del sys.modules["platform"]

    agent_module = importlib.import_module("platform.agent")
    closure_loop = importlib.import_module("platform.closure_loop")
    coordination_store = agent_module.AgentCoordinationStore(repo_root)
    context_id = os.environ.get("LV3_CONTEXT_ID", "").strip() or os.environ.get("WM_JOB_ID", "").strip() or str(uuid.uuid4())
    loop = closure_loop.ClosureLoop(repo_root)
    processed: list[dict[str, Any]] = []
    finding_list = findings or []
    with coordination_store.session(
        agent_id="agent/observation-loop",
        context_id=context_id,
        session_label=f"observation-loop {context_id[:8]}",
        current_phase="bootstrapping",
        current_target="observation-loop",
        current_workflow_id="platform-observation-loop",
    ) as session:
        session.transition(
            "executing",
            current_target="batch:observation-findings",
            step_index=0,
            step_count=len(finding_list),
            progress_pct=0.0 if finding_list else 1.0,
        )
        for index, finding in enumerate(finding_list, start=1):
            payload = closure_loop.observation_finding_to_alert_payload(
                finding,
                fallback_ref=f"{source}:{index}",
            )
            if payload is None:
                continue
            session.transition(
                "executing",
                current_target=f"service:{payload['service_id']}",
                step_index=index,
                step_count=len(finding_list),
                progress_pct=round(index / max(len(finding_list), 1), 2),
            )
            run = loop.start(
                trigger_type="observation_finding",
                trigger_ref=str(payload.get("incident_id") or f"{source}:{index}"),
                service_id=str(payload["service_id"]),
                trigger_payload=payload,
            )
            processed.append(
                {
                    "run_id": run["run_id"],
                    "service_id": run["service_id"],
                    "state": run["current_state"],
                    "correction_loop_id": (
                        run.get("correction_loop", {}).get("loop_id")
                        if isinstance(run.get("correction_loop"), dict)
                        else None
                    ),
                }
            )
        session.transition(
            "verifying",
            current_target="batch:observation-findings",
            step_index=len(finding_list),
            step_count=len(finding_list),
            progress_pct=1.0,
        )

    return {
        "status": "ok",
        "source": source,
        "workspace": __import__("os").environ.get("WM_WORKSPACE"),
        "job_id_present": bool(__import__("os").environ.get("WM_JOB_ID")),
        "finding_count": len(finding_list),
        "processed_count": len(processed),
        "correction_loop_id": processed[0]["correction_loop_id"] if processed else None,
        "processed_runs": processed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0126 observation-loop wrapper.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--findings-file", type=Path, help="Optional JSON file containing the finding list.")
    parser.add_argument("--output-file", type=Path, help="Optional JSON output file for fallback execution.")
    parser.add_argument("--source", default="controller-observation-loop")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    payload = json.loads(args.findings_file.read_text(encoding="utf-8")) if args.findings_file else None
    result = main(findings=payload, source=args.source, repo_path=args.repo_path)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output_file:
        args.output_file.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
