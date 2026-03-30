#!/usr/bin/env python3
"""Run the repo-managed Semgrep SAST gate and write a SARIF receipt."""

from __future__ import annotations

import argparse
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, repo_path  # type: ignore[import-not-found]
from mutation_audit import build_event, emit_event_best_effort  # type: ignore[import-not-found]


REPO_ROOT = repo_path()
DEFAULT_OUTPUT_DIR = REPO_ROOT / "receipts" / "sast"
SEMGREP_VERSION = "1.155.0"


@dataclass(frozen=True)
class RuleSet:
    name: str
    config_path: Path


@dataclass(frozen=True)
class BaselineResolution:
    results: list[dict[str, Any]]
    resolved: bool
    reason: str | None = None


RULESETS: tuple[RuleSet, ...] = (
    RuleSet("secrets", REPO_ROOT / "config" / "semgrep" / "rules" / "secrets.yaml"),
    RuleSet("sast", REPO_ROOT / "config" / "semgrep" / "rules" / "sast.yaml"),
    RuleSet("dockerfile", REPO_ROOT / "config" / "semgrep" / "rules" / "dockerfile.yaml"),
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the repo-managed Semgrep rule sets and write a merged SARIF report."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to scan.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory that receives the merged SARIF report.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Explicit merged SARIF output path. Defaults to receipts/sast/<git-sha>.sarif.json.",
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        help="Optional JSON summary file.",
    )
    parser.add_argument(
        "--baseline-ref",
        help="Optional git ref used to compute net-new findings against a repo snapshot.",
    )
    parser.add_argument(
        "--baseline-sarif",
        type=Path,
        help="Optional precomputed SARIF baseline used to compute net-new findings.",
    )
    parser.add_argument(
        "--emit-mutation-audit",
        action="store_true",
        help="Emit best-effort mutation audit events for net-new findings.",
    )
    parser.add_argument(
        "--audit-actor-id",
        default=os.environ.get("LV3_SEMGREP_AUDIT_ACTOR_ID", "semgrep-gate"),
        help="Actor id to record when mutation-audit emission is enabled.",
    )
    parser.add_argument(
        "--audit-correlation-id",
        help="Override the mutation-audit correlation id used for new findings.",
    )
    parser.add_argument(
        "--print-summary-json",
        action="store_true",
        help="Print the final JSON summary in addition to the human-readable output.",
    )
    return parser.parse_args(argv)


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def checkout_has_git_index(repo_root: Path) -> bool:
    result = _git(repo_root, "ls-files", "-z", "--cached")
    return result.returncode == 0


def resolve_source_sha(repo_root: Path) -> str:
    for env_name in ("GITHUB_SHA", "CI_COMMIT_SHA", "GITEA_SHA"):
        candidate = os.environ.get(env_name, "").strip()
        if candidate:
            return candidate

    result = _git(repo_root, "rev-parse", "HEAD")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return "manual"


def resolve_semgrep_command() -> list[str]:
    configured = os.environ.get("LV3_SEMGREP_BIN", "").strip()
    if configured:
        return shlex.split(configured)
    if shutil.which("semgrep"):
        return ["semgrep"]
    if shutil.which("uv"):
        return ["uv", "tool", "run", "--from", f"semgrep=={SEMGREP_VERSION}", "semgrep"]
    raise RuntimeError(
        "Semgrep is not available. Install semgrep or provide LV3_SEMGREP_BIN."
    )


def run_ruleset(
    *,
    semgrep_command: list[str],
    repo_root: Path,
    ruleset: RuleSet,
    output_path: Path,
    checkout_has_git_metadata: bool,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [*semgrep_command, "scan"]
    if not checkout_has_git_metadata:
        # Immutable gate snapshots intentionally omit `.git`, so force Semgrep
        # to walk the extracted tree instead of asking git for tracked files.
        command.append("--no-git-ignore")
    command.extend(
        [
            "--config",
            str(ruleset.config_path),
            "--disable-version-check",
            "--metrics=off",
            "--quiet",
            "--sarif",
            "--output",
            str(output_path),
            str(repo_root),
        ]
    )
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    # `semgrep scan` can legitimately exit 1 when findings are present while
    # still emitting a valid SARIF payload. Reserve hard failure handling for
    # tool/runtime errors.
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            f"Semgrep ruleset '{ruleset.name}' failed with exit code {completed.returncode}:\n"
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to parse SARIF output for ruleset '{ruleset.name}'") from exc


def merge_sarif(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not payloads:
        return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "runs": []}
    merged_runs: list[dict[str, Any]] = []
    for payload in payloads:
        runs = payload.get("runs", [])
        if isinstance(runs, list):
            merged_runs.extend(run for run in runs if isinstance(run, dict))
    return {
        "version": payloads[0].get("version", "2.1.0"),
        "$schema": payloads[0].get("$schema", "https://json.schemastore.org/sarif-2.1.0.json"),
        "runs": merged_runs,
    }


def _extract_result_identity(result: dict[str, Any]) -> str:
    fingerprints = result.get("partialFingerprints", {})
    if isinstance(fingerprints, dict) and fingerprints:
        stable = "|".join(f"{key}={value}" for key, value in sorted(fingerprints.items()))
        if stable:
            return stable

    locations = result.get("locations", [])
    uri = ""
    start_line = 0
    if locations:
        physical = (
            locations[0]
            .get("physicalLocation", {})
            if isinstance(locations[0], dict)
            else {}
        )
        artifact = physical.get("artifactLocation", {}) if isinstance(physical, dict) else {}
        region = physical.get("region", {}) if isinstance(physical, dict) else {}
        if isinstance(artifact, dict):
            uri = str(artifact.get("uri", ""))
        if isinstance(region, dict):
            start_line = int(region.get("startLine", 0) or 0)
    message = result.get("message", {})
    message_text = message.get("text", "") if isinstance(message, dict) else ""
    return "|".join(
        (
            str(result.get("ruleId", "")),
            str(uri),
            str(start_line),
            str(message_text),
        )
    )


def collect_results(sarif: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for run in sarif.get("runs", []):
        if not isinstance(run, dict):
            continue
        results = run.get("results", [])
        if not isinstance(results, list):
            continue
        for result in results:
            if isinstance(result, dict):
                collected.append(result)
    return collected


def summarize_results(sarif: dict[str, Any]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "note": 0, "none": 0}
    for result in collect_results(sarif):
        level = str(result.get("level", "warning")).lower()
        if level not in counts:
            counts["none"] += 1
            continue
        counts[level] += 1
    counts["total"] = sum(counts.values())
    return counts


def export_git_ref(repo_root: Path, ref: str, destination: Path) -> None:
    archive = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "--format=tar", ref],
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise RuntimeError(archive.stderr.decode("utf-8", errors="replace").strip() or f"git archive failed for {ref}")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as handle:
        handle.extractall(destination)


def load_baseline_results(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    semgrep_command: list[str],
    checkout_has_git_metadata: bool,
) -> BaselineResolution:
    if args.baseline_sarif is not None:
        payload = json.loads(args.baseline_sarif.read_text(encoding="utf-8"))
        return BaselineResolution(results=collect_results(payload), resolved=True)

    if not args.baseline_ref:
        return BaselineResolution(results=[], resolved=False)
    if not checkout_has_git_metadata:
        return BaselineResolution(
            results=[],
            resolved=False,
            reason="checkout has no git metadata",
        )

    with tempfile.TemporaryDirectory(prefix="lv3-semgrep-baseline.") as temp_dir:
        baseline_root = Path(temp_dir) / "repo"
        temp_output_dir = Path(temp_dir) / "sast"
        try:
            export_git_ref(repo_root, args.baseline_ref, baseline_root)
        except RuntimeError:
            return BaselineResolution(
                results=[],
                resolved=False,
                reason=f"unable to export baseline ref {args.baseline_ref}",
            )
        baseline_payloads: list[dict[str, Any]] = []
        for ruleset in RULESETS:
            baseline_config_path = baseline_root / ruleset.config_path.relative_to(repo_root)
            if not baseline_config_path.exists():
                return BaselineResolution(
                    results=[],
                    resolved=False,
                    reason=(
                        f"baseline ref {args.baseline_ref} does not contain "
                        f"{ruleset.config_path.relative_to(repo_root)}"
                    ),
                )
            output_path = temp_output_dir / f"{ruleset.name}.sarif.json"
            baseline_payloads.append(
                run_ruleset(
                    semgrep_command=semgrep_command,
                    repo_root=baseline_root,
                    ruleset=RuleSet(ruleset.name, baseline_config_path),
                    output_path=output_path,
                    checkout_has_git_metadata=False,
                )
            )
        return BaselineResolution(
            results=collect_results(merge_sarif(baseline_payloads)),
            resolved=True,
        )


def net_new_results(
    current_results: list[dict[str, Any]],
    baseline_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    baseline_keys = {_extract_result_identity(result) for result in baseline_results}
    return [
        result
        for result in current_results
        if _extract_result_identity(result) not in baseline_keys
    ]


def maybe_emit_mutation_audit(
    *,
    results: list[dict[str, Any]],
    actor_id: str,
    evidence_ref: str,
    correlation_id: str | None,
) -> int:
    emitted = 0
    for result in results:
        target = _extract_result_identity(result)
        event = build_event(
            actor_class="automation",
            actor_id=actor_id,
            surface="manual",
            action="sast_finding_introduced",
            target=target,
            outcome="success",
            correlation_id=correlation_id,
            evidence_ref=evidence_ref,
        )
        if emit_event_best_effort(
            event,
            context="semgrep gate",
            stderr=sys.stderr,
        ):
            emitted += 1
    return emitted


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = args.repo_root.resolve()
    if not repo_root.exists():
        raise RuntimeError(f"Repository root does not exist: {repo_root}")

    semgrep_command = resolve_semgrep_command()
    git_backed_checkout = checkout_has_git_index(repo_root)
    baseline_requested = args.baseline_ref is not None or args.baseline_sarif is not None
    source_sha = resolve_source_sha(repo_root)
    output_path = args.output_file or (args.output_dir.resolve() / f"{source_sha}.sarif.json")

    payloads: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="lv3-semgrep.") as temp_dir:
        temp_output_dir = Path(temp_dir)
        for ruleset in RULESETS:
            if not ruleset.config_path.exists():
                raise RuntimeError(f"Missing Semgrep ruleset: {ruleset.config_path}")
            payloads.append(
                run_ruleset(
                    semgrep_command=semgrep_command,
                    repo_root=repo_root,
                    ruleset=ruleset,
                    output_path=temp_output_dir / f"{ruleset.name}.sarif.json",
                    checkout_has_git_metadata=git_backed_checkout,
                )
            )

    merged_sarif = merge_sarif(payloads)
    write_json(output_path, merged_sarif)

    current_results = collect_results(merged_sarif)
    baseline_resolution = load_baseline_results(
        args=args,
        repo_root=repo_root,
        semgrep_command=semgrep_command,
        checkout_has_git_metadata=git_backed_checkout,
    )
    baseline_results = baseline_resolution.results
    baseline_resolved = baseline_resolution.resolved
    new_results = net_new_results(current_results, baseline_results) if baseline_resolved else []
    counts = summarize_results(merged_sarif)
    blocking_findings = counts["error"]

    emitted_events = 0
    if args.emit_mutation_audit and new_results:
        evidence_ref = os.path.relpath(output_path, repo_root)
        emitted_events = maybe_emit_mutation_audit(
            results=new_results,
            actor_id=args.audit_actor_id,
            evidence_ref=evidence_ref,
            correlation_id=args.audit_correlation_id,
        )

    summary = {
        "schema_version": "1.0.0",
        "status": "failed" if blocking_findings else "passed",
        "repo_root": str(repo_root),
        "source_sha": source_sha,
        "sarif_path": str(output_path),
        "counts": counts,
        "blocking_findings": blocking_findings,
        "baseline_requested": baseline_requested,
        "baseline_resolved": baseline_resolved,
        "baseline_skip_reason": baseline_resolution.reason,
        "net_new_findings": len(new_results),
        "baseline_ref": args.baseline_ref,
        "rulesets": [ruleset.name for ruleset in RULESETS],
        "mutation_audit_events_emitted": emitted_events,
    }
    if args.summary_file is not None:
        write_json(args.summary_file.resolve(), summary)

    print("Semgrep gate summary")
    print(f"  repo: {repo_root}")
    print(f"  source sha: {source_sha}")
    print(f"  sarif: {output_path}")
    print(
        "  findings: "
        f"error={counts['error']} warning={counts['warning']} note={counts['note']} total={counts['total']}"
    )
    if baseline_requested:
        print(f"  net new findings: {len(new_results)}")
    if baseline_requested and not baseline_resolved and baseline_resolution.reason:
        print(f"  baseline comparison: skipped ({baseline_resolution.reason})")
    if args.emit_mutation_audit:
        print(f"  mutation audit events emitted: {emitted_events}")

    if args.print_summary_json:
        print(json.dumps(summary, indent=2))

    return 1 if blocking_findings else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise SystemExit(emit_cli_error("Semgrep gate", exc))
