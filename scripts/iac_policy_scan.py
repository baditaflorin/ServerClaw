#!/usr/bin/env python3
"""Run repo-managed Checkov IaC policy scanning and emit summary plus SARIF."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError as exc:
    if exc.name != "yaml" or os.environ.get("LV3_IAC_POLICY_SCAN_PYYAML_BOOTSTRAPPED") == "1":
        raise
    helper_path = Path(__file__).resolve().with_name("run_python_with_packages.sh")
    if not helper_path.is_file():
        raise
    os.environ["LV3_IAC_POLICY_SCAN_PYYAML_BOOTSTRAPPED"] = "1"
    entrypoint = Path(sys.argv[0])
    if not entrypoint.is_absolute():
        entrypoint = (Path.cwd() / entrypoint).resolve()
    if not entrypoint.is_file():
        entrypoint = Path(__file__).resolve()
    os.execv(
        str(helper_path),
        [str(helper_path), "pyyaml", "--", str(entrypoint), *sys.argv[1:]],
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "checkov" / "policy-gate.yaml"
DEFAULT_SKIP_CATALOG_PATH = REPO_ROOT / "config" / "checkov" / "skip-checks.yaml"
DEFAULT_EXTERNAL_CHECKS_DIR = REPO_ROOT / "config" / "checkov" / "checks"
LEVELS = ("error", "warning", "note")
SEVERITY_TO_LEVEL = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
    "INFO": "note",
}
CUSTOM_RULE_METADATA: dict[str, tuple[str, str]] = {
    "CKV_LV3_1": (
        "Ensure Proxmox VM disks participate in backup",
        "ADR 0306 requires repo-managed Proxmox VMs to keep disk backup enabled.",
    ),
    "CKV_LV3_2": (
        "Ensure Proxmox VM network devices pin a MAC address",
        "ADR 0306 and the repo lessons learned require stable VM MAC identity.",
    ),
    "CKV_LV3_3": (
        "Ensure Proxmox VM module calls declare mac_address",
        "ADR 0306 requires each governed Proxmox VM module call to pin a MAC address.",
    ),
    "CKV_LV3_4": (
        "Ensure Proxmox provider TLS verification stays enabled",
        "ADR 0306 treats insecure=true as a governed warning until the live API path uses trusted TLS.",
    ),
}


@dataclass(frozen=True)
class ScanGroup:
    group_id: str
    title: str
    framework: str
    path: str


@dataclass(frozen=True)
class Suppression:
    check_id: str
    file_pattern: str
    start_line: int | None
    end_line: int | None
    reason: str
    decision_ref: str | None


@dataclass(frozen=True)
class PolicyConfig:
    default_level: str
    blocking_levels: tuple[str, ...]
    level_overrides: dict[str, str]
    scan_groups: tuple[ScanGroup, ...]
    compose_template_globs: tuple[str, ...]
    compose_gap_note: str | None


@dataclass
class Finding:
    check_id: str
    check_name: str
    level: str
    message: str
    path: str
    start_line: int
    end_line: int
    source_group: str
    resource: str | None
    guideline: str | None
    severity: str | None
    suppression: Suppression | None = None

    def to_summary_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "level": self.level,
            "message": self.message,
            "path": self.path,
            "line_range": [self.start_line, self.end_line],
            "source_group": self.source_group,
            "resource": self.resource,
            "guideline": self.guideline,
            "severity": self.severity,
        }
        if self.suppression is not None:
            payload["suppression"] = {
                "reason": self.suppression.reason,
                "decision_ref": self.suppression.decision_ref,
                "file_pattern": self.suppression.file_pattern,
            }
        return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the repo-managed Checkov IaC policy scan and emit summary plus SARIF.",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--skip-catalog", type=Path, default=DEFAULT_SKIP_CATALOG_PATH)
    parser.add_argument(
        "--external-checks-dir",
        type=Path,
        default=DEFAULT_EXTERNAL_CHECKS_DIR,
        help="Directory that contains repo-managed Checkov external checks.",
    )
    parser.add_argument(
        "--checkov-binary",
        default=os.environ.get("LV3_CHECKOV_BIN", "checkov"),
        help="Checkov binary to execute inside the security runner.",
    )
    parser.add_argument("--write-summary", type=Path, help="Write the JSON summary report here.")
    parser.add_argument("--write-sarif", type=Path, help="Write the SARIF report here.")
    parser.add_argument("--print-json", action="store_true", help="Print the JSON summary to stdout.")
    return parser.parse_args(argv)


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def require_level(value: Any, path: str) -> str:
    level = require_str(value, path).lower()
    if level not in LEVELS:
        raise ValueError(f"{path} must be one of {list(LEVELS)}")
    return level


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return require_mapping(payload, str(path))


def load_policy(path: Path) -> PolicyConfig:
    payload = load_yaml(path)
    scan_groups = tuple(
        ScanGroup(
            group_id=require_str(entry.get("id"), f"{path}.scan_groups[{index}].id"),
            title=require_str(entry.get("title"), f"{path}.scan_groups[{index}].title"),
            framework=require_str(entry.get("framework"), f"{path}.scan_groups[{index}].framework"),
            path=require_str(entry.get("path"), f"{path}.scan_groups[{index}].path"),
        )
        for index, entry in enumerate(require_list(payload.get("scan_groups"), f"{path}.scan_groups"))
        for entry in [require_mapping(entry, f"{path}.scan_groups[{index}]")]
    )
    if not scan_groups:
        raise ValueError(f"{path}.scan_groups must not be empty")

    level_overrides_raw = require_mapping(payload.get("level_overrides", {}), f"{path}.level_overrides")
    level_overrides = {
        require_str(check_id, f"{path}.level_overrides.key"): require_level(
            level, f"{path}.level_overrides[{check_id}]"
        )
        for check_id, level in level_overrides_raw.items()
    }

    compose_template_globs = tuple(
        require_str(item, f"{path}.compose_template_globs[{index}]")
        for index, item in enumerate(payload.get("compose_template_globs", []) or [])
    )
    compose_gap_note = payload.get("compose_gap_note")
    if compose_gap_note is not None:
        compose_gap_note = require_str(compose_gap_note, f"{path}.compose_gap_note")

    return PolicyConfig(
        default_level=require_level(payload.get("default_level", "note"), f"{path}.default_level"),
        blocking_levels=tuple(
            require_level(level, f"{path}.blocking_levels[{index}]")
            for index, level in enumerate(require_list(payload.get("blocking_levels"), f"{path}.blocking_levels"))
        ),
        level_overrides=level_overrides,
        scan_groups=scan_groups,
        compose_template_globs=compose_template_globs,
        compose_gap_note=compose_gap_note,
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raise ValueError(f"expected integer or null, received {value!r}")


def load_suppressions(path: Path) -> tuple[Suppression, ...]:
    payload = load_yaml(path)
    suppressions: list[Suppression] = []
    for index, raw_entry in enumerate(require_list(payload.get("suppressions", []), f"{path}.suppressions")):
        entry = require_mapping(raw_entry, f"{path}.suppressions[{index}]")
        line_range = entry.get("line_range")
        start_line: int | None = None
        end_line: int | None = None
        if line_range is not None:
            line_range = require_list(line_range, f"{path}.suppressions[{index}].line_range")
            if len(line_range) != 2:
                raise ValueError(f"{path}.suppressions[{index}].line_range must contain two integers")
            start_line = _optional_int(line_range[0])
            end_line = _optional_int(line_range[1])
        decision_ref = entry.get("decision_ref")
        if decision_ref is not None:
            decision_ref = require_str(decision_ref, f"{path}.suppressions[{index}].decision_ref")
        suppressions.append(
            Suppression(
                check_id=require_str(entry.get("check_id"), f"{path}.suppressions[{index}].check_id"),
                file_pattern=require_str(entry.get("file"), f"{path}.suppressions[{index}].file"),
                start_line=start_line,
                end_line=end_line,
                reason=require_str(entry.get("reason"), f"{path}.suppressions[{index}].reason"),
                decision_ref=decision_ref,
            )
        )
    return tuple(suppressions)


def git_value(repo_root: Path, *args: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def detect_source_commit(repo_root: Path) -> str:
    for env_name in ("LV3_SNAPSHOT_SOURCE_COMMIT", "GITHUB_SHA", "CI_COMMIT_SHA"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return git_value(repo_root, "rev-parse", "HEAD") or "workspace"


def default_output_paths(repo_root: Path, source_commit: str) -> tuple[Path, Path]:
    receipt_dir = repo_root / "receipts" / "checkov"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    token = source_commit.strip().replace("/", "-") or "workspace"
    return receipt_dir / f"{token}.json", receipt_dir / f"{token}.sarif.json"


def normalize_repo_path(path: str, repo_root: Path) -> str:
    value = path.strip()
    if not value:
        return "."
    if value.startswith("/"):
        candidate = Path(value)
        try:
            return candidate.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return value.lstrip("/")
    return value.lstrip("./")


def line_ranges_overlap(start_a: int, end_a: int, start_b: int | None, end_b: int | None) -> bool:
    if start_b is None or end_b is None:
        return True
    return max(start_a, start_b) <= min(end_a, end_b)


def match_suppression(
    *,
    suppressions: tuple[Suppression, ...],
    check_id: str,
    path: str,
    start_line: int,
    end_line: int,
) -> Suppression | None:
    for suppression in suppressions:
        if suppression.check_id != check_id:
            continue
        if not fnmatch(path, suppression.file_pattern):
            continue
        if not line_ranges_overlap(start_line, end_line, suppression.start_line, suppression.end_line):
            continue
        return suppression
    return None


def unwrap(value: Any) -> Any:
    if isinstance(value, list):
        if not value:
            return None
        if len(value) == 1:
            return unwrap(value[0])
    return value


def truthy(value: Any) -> bool:
    value = unwrap(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def has_value(value: Any) -> bool:
    value = unwrap(value)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def iter_block_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        blocks: list[dict[str, Any]] = []
        for item in value:
            blocks.extend(iter_block_dicts(item))
        return blocks
    return []


def line_number_for(path: Path, *needles: str) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines, start=1):
        if all(needle in line for needle in needles):
            return index
    return 1


def custom_finding(
    *,
    check_id: str,
    path: Path,
    repo_root: Path,
    policy: PolicyConfig,
    suppressions: tuple[Suppression, ...],
    source_group: str,
    line: int,
    resource: str | None,
) -> Finding:
    check_name, guideline = CUSTOM_RULE_METADATA[check_id]
    relative_path = normalize_repo_path(path.as_posix(), repo_root)
    suppression = match_suppression(
        suppressions=suppressions,
        check_id=check_id,
        path=relative_path,
        start_line=line,
        end_line=line,
    )
    return Finding(
        check_id=check_id,
        check_name=check_name,
        level=policy.level_overrides.get(check_id, policy.default_level),
        message=check_name if resource is None else f"{check_name} ({resource})",
        path=relative_path,
        start_line=line,
        end_line=line,
        source_group=source_group,
        resource=resource,
        guideline=guideline,
        severity=None,
        suppression=suppression,
    )


def governed_proxmox_module(source: Any) -> bool:
    value = unwrap(source)
    if not isinstance(value, str):
        return False
    return value.endswith("/proxmox-vm") or value.endswith("/proxmox-vm-destroyable")


def scan_tofu_custom_findings(
    *,
    repo_root: Path,
    group: ScanGroup,
    policy: PolicyConfig,
    suppressions: tuple[Suppression, ...],
) -> list[Finding]:
    try:
        import hcl2  # type: ignore[import-not-found, import-untyped]
    except ModuleNotFoundError:
        return [
            build_synthetic_finding(
                check_id="CKV_LV3_EXECUTION",
                check_name="Missing python-hcl2 dependency",
                path=group.path,
                group_id=group.group_id,
                message="python-hcl2 is required for the repo-managed Proxmox OpenTofu invariants.",
            )
        ]

    findings: list[Finding] = []
    tofu_root = repo_root / group.path
    for tf_path in sorted(tofu_root.rglob("*.tf")):
        try:
            with tf_path.open(encoding="utf-8") as handle:
                document = hcl2.load(handle)
        except Exception as exc:  # pragma: no cover - exercised through live scans
            findings.append(
                build_synthetic_finding(
                    check_id="CKV_LV3_PARSING",
                    check_name="OpenTofu parsing failure",
                    path=normalize_repo_path(tf_path.as_posix(), repo_root),
                    group_id=group.group_id,
                    message=f"python-hcl2 failed to parse {tf_path.name}: {exc}",
                )
            )
            continue

        for provider_block in document.get("provider", []) or []:
            if not isinstance(provider_block, dict):
                continue
            proxmox = provider_block.get("proxmox")
            if not isinstance(proxmox, dict):
                continue
            if truthy(proxmox.get("insecure")):
                findings.append(
                    custom_finding(
                        check_id="CKV_LV3_4",
                        path=tf_path,
                        repo_root=repo_root,
                        policy=policy,
                        suppressions=suppressions,
                        source_group=group.group_id,
                        line=line_number_for(tf_path, "insecure"),
                        resource="provider.proxmox",
                    )
                )

        for module_block in document.get("module", []) or []:
            if not isinstance(module_block, dict):
                continue
            for module_name, module_conf in module_block.items():
                if not isinstance(module_conf, dict):
                    continue
                if not governed_proxmox_module(module_conf.get("source")):
                    continue
                if has_value(module_conf.get("mac_address")):
                    continue
                findings.append(
                    custom_finding(
                        check_id="CKV_LV3_3",
                        path=tf_path,
                        repo_root=repo_root,
                        policy=policy,
                        suppressions=suppressions,
                        source_group=group.group_id,
                        line=line_number_for(tf_path, f'module "{module_name}"'),
                        resource=f"module.{module_name}",
                    )
                )

        for resource_block in document.get("resource", []) or []:
            if not isinstance(resource_block, dict):
                continue
            vm_resources = resource_block.get("proxmox_virtual_environment_vm")
            if not isinstance(vm_resources, dict):
                continue
            for resource_name, resource_conf in vm_resources.items():
                if not isinstance(resource_conf, dict):
                    continue
                resource_label = f"proxmox_virtual_environment_vm.{resource_name}"
                resource_line = line_number_for(
                    tf_path,
                    'resource "proxmox_virtual_environment_vm"',
                    f'"{resource_name}"',
                )

                disks = iter_block_dicts(resource_conf.get("disk") or [])
                if not disks or any(not truthy(disk.get("backup")) for disk in disks):
                    findings.append(
                        custom_finding(
                            check_id="CKV_LV3_1",
                            path=tf_path,
                            repo_root=repo_root,
                            policy=policy,
                            suppressions=suppressions,
                            source_group=group.group_id,
                            line=resource_line,
                            resource=resource_label,
                        )
                    )

                devices = iter_block_dicts(resource_conf.get("network_device") or [])
                if not devices or any(not has_value(device.get("mac_address")) for device in devices):
                    findings.append(
                        custom_finding(
                            check_id="CKV_LV3_2",
                            path=tf_path,
                            repo_root=repo_root,
                            policy=policy,
                            suppressions=suppressions,
                            source_group=group.group_id,
                            line=resource_line,
                            resource=resource_label,
                        )
                    )
    return findings


def resolve_finding_level(raw: dict[str, Any], policy: PolicyConfig) -> str:
    check_id = str(raw.get("check_id", "")).strip()
    override = policy.level_overrides.get(check_id)
    if override is not None:
        return override
    severity = raw.get("severity")
    if isinstance(severity, str):
        mapped = SEVERITY_TO_LEVEL.get(severity.strip().upper())
        if mapped is not None:
            return mapped
    return policy.default_level


def build_finding(
    *,
    raw: dict[str, Any],
    policy: PolicyConfig,
    repo_root: Path,
    group_id: str,
    suppressions: tuple[Suppression, ...],
) -> Finding:
    raw_line_range = raw.get("file_line_range") or []
    start_line = 1
    end_line = 1
    if isinstance(raw_line_range, list) and raw_line_range:
        if isinstance(raw_line_range[0], int):
            start_line = raw_line_range[0]
        if len(raw_line_range) > 1 and isinstance(raw_line_range[1], int):
            end_line = raw_line_range[1]
        else:
            end_line = start_line

    path = normalize_repo_path(
        str(raw.get("repo_file_path") or raw.get("file_path") or raw.get("file_abs_path") or "."),
        repo_root,
    )
    check_name = str(raw.get("check_name") or raw.get("check_id") or "Unknown Check").strip()
    resource = raw.get("resource")
    resource_text = resource.strip() if isinstance(resource, str) and resource.strip() else None
    message = check_name if resource_text is None else f"{check_name} ({resource_text})"

    suppression = match_suppression(
        suppressions=suppressions,
        check_id=str(raw.get("check_id", "")).strip(),
        path=path,
        start_line=start_line,
        end_line=end_line,
    )
    return Finding(
        check_id=str(raw.get("check_id", "")).strip(),
        check_name=check_name,
        level=resolve_finding_level(raw, policy),
        message=message,
        path=path,
        start_line=start_line,
        end_line=end_line,
        source_group=group_id,
        resource=resource_text,
        guideline=str(raw.get("guideline")).strip() if raw.get("guideline") else None,
        severity=str(raw.get("severity")).strip() if raw.get("severity") else None,
        suppression=suppression,
    )


def build_synthetic_finding(
    *,
    check_id: str,
    check_name: str,
    path: str,
    group_id: str,
    message: str,
) -> Finding:
    return Finding(
        check_id=check_id,
        check_name=check_name,
        level="error",
        message=message,
        path=path,
        start_line=1,
        end_line=1,
        source_group=group_id,
        resource=None,
        guideline=None,
        severity=None,
    )


def run_scan_group(
    *,
    repo_root: Path,
    group: ScanGroup,
    checkov_binary: str,
    external_checks_dir: Path,
    policy: PolicyConfig,
    suppressions: tuple[Suppression, ...],
) -> dict[str, Any]:
    scan_path = repo_root / group.path
    if not scan_path.exists():
        return {
            "group_id": group.group_id,
            "title": group.title,
            "framework": group.framework,
            "path": group.path,
            "status": "skipped",
            "summary": {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "parsing_errors": 0,
                "resource_count": 0,
            },
            "findings": [],
            "suppressed_findings": [],
            "notes": [f"Skipped because {group.path} does not exist in this checkout."],
        }

    command = [
        checkov_binary,
        "--directory",
        group.path,
        "--framework",
        group.framework,
        "--skip-download",
        "--soft-fail",
        "--output",
        "json",
        "--quiet",
        "--external-checks-dir",
        str(external_checks_dir),
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    stdout = completed.stdout.strip()
    if not stdout:
        finding = build_synthetic_finding(
            check_id="CKV_LV3_EXECUTION",
            check_name="Checkov execution failure",
            path=group.path,
            group_id=group.group_id,
            message=(
                f"Checkov did not emit JSON for {group.path}. stderr: "
                f"{(completed.stderr or 'no stderr').strip()}"
            ),
        )
        return {
            "group_id": group.group_id,
            "title": group.title,
            "framework": group.framework,
            "path": group.path,
            "status": "failed",
            "summary": {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "parsing_errors": 0,
                "resource_count": 0,
            },
            "findings": [finding],
            "suppressed_findings": [],
            "notes": [f"Command failed: {' '.join(command)}"],
        }

    payload = json.loads(stdout)
    payload = require_mapping(payload, f"Checkov payload for {group.group_id}")
    results = require_mapping(payload.get("results", {}), f"{group.group_id}.results")
    summary = require_mapping(payload.get("summary", {}), f"{group.group_id}.summary")
    findings = [
        build_finding(
            raw=require_mapping(raw_entry, f"{group.group_id}.results.failed_checks[{index}]"),
            policy=policy,
            repo_root=repo_root,
            group_id=group.group_id,
            suppressions=suppressions,
        )
        for index, raw_entry in enumerate(results.get("failed_checks", []) or [])
    ]

    parsing_errors = summary.get("parsing_errors", 0)
    if isinstance(parsing_errors, int) and parsing_errors > 0:
        findings.append(
            build_synthetic_finding(
                check_id="CKV_LV3_PARSING",
                check_name="Checkov parsing errors",
                path=group.path,
                group_id=group.group_id,
                message=f"Checkov reported {parsing_errors} parsing error(s) while scanning {group.path}.",
            )
        )

    if group.framework == "terraform":
        findings.extend(
            scan_tofu_custom_findings(
                repo_root=repo_root,
                group=group,
                policy=policy,
                suppressions=suppressions,
            )
        )

    active_findings = [finding for finding in findings if finding.suppression is None]
    suppressed_findings = [finding for finding in findings if finding.suppression is not None]
    status = "failed" if any(finding.level in policy.blocking_levels for finding in active_findings) else "passed"
    if active_findings and status == "passed":
        status = "passed_with_findings"

    return {
        "group_id": group.group_id,
        "title": group.title,
        "framework": group.framework,
        "path": group.path,
        "status": status,
        "summary": {
            "passed": int(summary.get("passed", 0) or 0),
            "failed": int(summary.get("failed", 0) or 0),
            "skipped": int(summary.get("skipped", 0) or 0),
            "parsing_errors": int(summary.get("parsing_errors", 0) or 0),
            "resource_count": int(summary.get("resource_count", 0) or 0),
            "checkov_version": str(summary.get("checkov_version") or ""),
        },
        "findings": active_findings,
        "suppressed_findings": suppressed_findings,
        "notes": [],
    }


def compose_surface_notes(repo_root: Path, policy: PolicyConfig) -> list[str]:
    notes: list[str] = []
    if not policy.compose_template_globs:
        return notes
    matches = {
        path.relative_to(repo_root).as_posix()
        for pattern in policy.compose_template_globs
        for path in repo_root.glob(pattern)
        if path.is_file()
    }
    if matches:
        note = policy.compose_gap_note or "Compose scanning is currently outside the managed Checkov path."
        notes.append(f"Detected {len(matches)} Docker Compose template file(s). {note}")
    return notes


def build_summary_report(
    *,
    repo_root: Path,
    policy: PolicyConfig,
    source_commit: str,
    group_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    active_findings = [
        finding
        for group_report in group_reports
        for finding in group_report["findings"]
    ]
    suppressed_findings = [
        finding
        for group_report in group_reports
        for finding in group_report["suppressed_findings"]
    ]
    counts = {level: 0 for level in LEVELS}
    for finding in active_findings:
        counts[finding.level] += 1

    compose_notes = compose_surface_notes(repo_root, policy)
    status = "failed" if any(counts[level] for level in policy.blocking_levels) else "passed"
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tool_version = next(
        (
            str(group_report["summary"].get("checkov_version", "")).strip()
            for group_report in group_reports
            if str(group_report["summary"].get("checkov_version", "")).strip()
        ),
        "unknown",
    )

    return {
        "status": status,
        "generated_at": generated_at,
        "source_commit": source_commit,
        "tool": {
            "name": "checkov",
            "version": tool_version,
        },
        "policy": {
            "default_level": policy.default_level,
            "blocking_levels": list(policy.blocking_levels),
            "level_overrides": dict(sorted(policy.level_overrides.items())),
        },
        "counts": {
            **counts,
            "suppressed": len(suppressed_findings),
            "active": len(active_findings),
        },
        "compose_surface_notes": compose_notes,
        "scan_groups": [
            {
                "group_id": group_report["group_id"],
                "title": group_report["title"],
                "framework": group_report["framework"],
                "path": group_report["path"],
                "status": group_report["status"],
                "summary": group_report["summary"],
                "notes": group_report["notes"],
                "active_findings": [finding.to_summary_dict() for finding in group_report["findings"]],
                "suppressed_findings": [
                    finding.to_summary_dict() for finding in group_report["suppressed_findings"]
                ],
            }
            for group_report in group_reports
        ],
        "findings": [finding.to_summary_dict() for finding in active_findings],
        "suppressed_findings": [finding.to_summary_dict() for finding in suppressed_findings],
    }


def build_rule_index(summary_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    for finding in summary_report["findings"]:
        check_id = finding["check_id"]
        if check_id in rules:
            continue
        rules[check_id] = {
            "id": check_id,
            "name": finding["check_name"],
            "shortDescription": {"text": finding["check_name"]},
            "helpUri": finding.get("guideline") or "https://github.com/bridgecrewio/checkov",
        }
    return rules


def build_sarif(summary_report: dict[str, Any]) -> dict[str, Any]:
    rule_index = build_rule_index(summary_report)
    results = []
    for finding in summary_report["findings"]:
        results.append(
            {
                "ruleId": finding["check_id"],
                "level": finding["level"],
                "message": {"text": finding["message"]},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": finding["path"]},
                            "region": {
                                "startLine": finding["line_range"][0],
                                "endLine": finding["line_range"][1],
                            },
                        }
                    }
                ],
                "partialFingerprints": {
                    "primaryLocationLineHash": (
                        f"{finding['check_id']}:{finding['path']}:{finding['line_range'][0]}:{finding['line_range'][1]}"
                    )
                },
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Checkov",
                        "version": summary_report["tool"]["version"],
                        "informationUri": "https://github.com/bridgecrewio/checkov",
                        "rules": list(rule_index.values()),
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": summary_report["status"] == "passed",
                        "properties": {
                            "source_commit": summary_report["source_commit"],
                            "counts": summary_report["counts"],
                            "compose_surface_notes": summary_report["compose_surface_notes"],
                        },
                    }
                ],
                "results": results,
            }
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def print_human_summary(summary_report: dict[str, Any], summary_path: Path | None, sarif_path: Path | None) -> None:
    counts = summary_report["counts"]
    print(
        "IaC policy scan "
        f"{summary_report['status']}: "
        f"{counts['error']} error, {counts['warning']} warning, {counts['note']} note, "
        f"{counts['suppressed']} suppressed"
    )
    for group in summary_report["scan_groups"]:
        print(
            f"- {group['group_id']} [{group['framework']}] {group['status']}: "
            f"{len(group['active_findings'])} active, {len(group['suppressed_findings'])} suppressed"
        )
    for note in summary_report["compose_surface_notes"]:
        print(f"- compose: {note}")
    if summary_path is not None:
        print(f"Summary report: {summary_path}")
    if sarif_path is not None:
        print(f"SARIF report: {sarif_path}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = args.repo_root.resolve()
    policy = load_policy(args.policy.resolve())
    suppressions = load_suppressions(args.skip_catalog.resolve())
    source_commit = detect_source_commit(repo_root)
    summary_path, sarif_path = default_output_paths(repo_root, source_commit)
    if args.write_summary is not None:
        summary_path = args.write_summary.resolve()
    if args.write_sarif is not None:
        sarif_path = args.write_sarif.resolve()

    group_reports = [
        run_scan_group(
            repo_root=repo_root,
            group=group,
            checkov_binary=args.checkov_binary,
            external_checks_dir=args.external_checks_dir.resolve(),
            policy=policy,
            suppressions=suppressions,
        )
        for group in policy.scan_groups
    ]
    summary_report = build_summary_report(
        repo_root=repo_root,
        policy=policy,
        source_commit=source_commit,
        group_reports=group_reports,
    )
    sarif_report = build_sarif(summary_report)

    write_json(summary_path, summary_report)
    write_json(sarif_path, sarif_report)
    print_human_summary(summary_report, summary_path, sarif_path)

    if args.print_json:
        print(json.dumps(summary_report, indent=2))

    return 1 if summary_report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
