#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import datetime
try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone
    UTC = timezone.utc  # type: ignore[assignment]
from pathlib import Path
from typing import Any

from artifact_cache_seed import normalize_registry_host, strip_registry_host
from controller_automation_toolkit import load_json, repo_path, write_json


REPO_ROOT = repo_path()
SBOM_SCANNER_CONFIG_PATH = repo_path("config", "sbom-scanner.json")
SBOM_RECEIPTS_DIR = repo_path("receipts", "sbom")
CVE_RECEIPTS_DIR = repo_path("receipts", "cve")
DEFAULT_SYFT_CACHE_DIR = Path(os.environ.get("LV3_SYFT_CACHE_DIR", "/var/tmp/lv3-syft-cache"))
DEFAULT_GRYPE_DB_CACHE_DIR = Path(os.environ.get("LV3_GRYPE_DB_CACHE_DIR", "/var/tmp/lv3-grype-db"))
DEFAULT_SYFT_TMP_DIR = Path(os.environ.get("LV3_SYFT_TMP_DIR", str(REPO_ROOT / ".local" / "syft-tmp")))
SEVERITY_BUCKETS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def load_scanner_config(path: Path = SBOM_SCANNER_CONFIG_PATH) -> dict[str, Any]:
    return load_json(path)


def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat_utc(timestamp: datetime) -> str:
    return timestamp.isoformat().replace("+00:00", "Z")


def timestamp_slug(timestamp: datetime) -> str:
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def digest_from_ref(image_ref: str) -> str | None:
    if "@sha256:" not in image_ref:
        return None
    return image_ref.rsplit("@", 1)[1]


def digest_short(value: str) -> str:
    digest = digest_from_ref(value) or value
    if digest.startswith("sha256:"):
        return digest.split(":", 1)[1][:12]
    cleaned = "".join(char for char in digest if char.isalnum())
    return cleaned[:12] or "unknown"


def relpath(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def workspace_host_root() -> Path | None:
    raw = os.environ.get("LV3_DOCKER_WORKSPACE_PATH", "").strip()
    return Path(raw) if raw else None


def host_path_for_repo_path(path: Path) -> Path:
    host_root = workspace_host_root()
    if not host_root:
        return path
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return path
    return host_root / rel


def temp_env(temp_dir: Path) -> dict[str, str]:
    resolved = str(temp_dir.resolve())
    return {
        "TMPDIR": resolved,
        "TMP": resolved,
        "TEMP": resolved,
    }


def docker_network_mode(config: dict[str, Any]) -> str | None:
    configured = os.environ.get("LV3_SCANNER_DOCKER_NETWORK", "").strip() or config.get("docker_network", "")
    if configured == "host" and platform.system() != "Linux":
        return None
    return configured or None


def docker_run_prefix(network_mode: str | None) -> list[str]:
    command = ["docker", "run", "--rm"]
    if network_mode:
        command.extend(["--network", network_mode])
    return command


def find_native_syft_binary() -> str | None:
    if platform.system() != "Linux":
        return None
    candidates: list[str] = []
    override = os.environ.get("LV3_SYFT_BINARY", "").strip()
    if override:
        candidates.append(override)
    candidates.extend(("/usr/local/bin/syft", "syft"))
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def find_native_grype_binary() -> str | None:
    if platform.system() != "Linux":
        return None
    candidates: list[str] = []
    override = os.environ.get("LV3_GRYPE_BINARY", "").strip()
    if override:
        candidates.append(override)
    candidates.extend(("/usr/local/bin/grype", "grype"))
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "command failed")
    return result


def artifact_cache_ref(image_ref: str, config: dict[str, Any] | None = None) -> str:
    config = config or load_scanner_config()
    registry_host = normalize_registry_host(image_ref)
    mirror_port = config.get("artifact_cache", {}).get("mirrors", {}).get(registry_host)
    cache_host = os.environ.get("LV3_ARTIFACT_CACHE_HOST", "").strip() or config.get("artifact_cache", {}).get(
        "host", ""
    )
    if not cache_host or mirror_port is None:
        return image_ref
    return f"{cache_host}:{mirror_port}/{strip_registry_host(image_ref)}"


def syft_scan_image(
    image_ref: str,
    *,
    sbom_path: Path,
    platform_name: str,
    config: dict[str, Any],
    use_artifact_cache: bool = True,
    syft_cache_dir: Path = DEFAULT_SYFT_CACHE_DIR,
    syft_tmp_dir: Path = DEFAULT_SYFT_TMP_DIR,
) -> dict[str, Any]:
    syft_cache_dir = ensure_dir(syft_cache_dir)
    syft_tmp_dir = ensure_dir(syft_tmp_dir)
    ensure_dir(sbom_path.parent)
    source_ref = artifact_cache_ref(image_ref, config) if use_artifact_cache else image_ref
    registry_env = {
        **os.environ,
        "SYFT_CACHE_DIR": str(syft_cache_dir.resolve()),
        "SYFT_REGISTRY_INSECURE_USE_HTTP": "true" if source_ref != image_ref else "false",
        **temp_env(syft_tmp_dir),
    }
    native_syft_binary = find_native_syft_binary()
    if native_syft_binary:
        command = [
            native_syft_binary,
            "scan",
            "--from",
            "registry",
            source_ref,
            "--source-name",
            image_ref,
            "--platform",
            platform_name,
            "-o",
            "cyclonedx-json",
        ]
        result = run_command(command, env=registry_env)
    else:
        network_mode = docker_network_mode(config)
        command = docker_run_prefix(network_mode)
        command.extend(
            [
                "-v",
                f"{syft_cache_dir.resolve()}:/syft-cache",
                "-v",
                f"{syft_tmp_dir.resolve()}:/syft-tmp",
                "-e",
                "SYFT_CACHE_DIR=/syft-cache",
                "-e",
                "TMPDIR=/syft-tmp",
                "-e",
                "TMP=/syft-tmp",
                "-e",
                "TEMP=/syft-tmp",
                "-e",
                f"SYFT_REGISTRY_INSECURE_USE_HTTP={'true' if source_ref != image_ref else 'false'}",
                str(config["syft"]["container_image"]),
                "scan",
                "--from",
                "registry",
                source_ref,
                "--source-name",
                image_ref,
                "--platform",
                platform_name,
                "-o",
                "cyclonedx-json",
            ]
        )
        result = run_command(command)
    payload = json.loads(result.stdout)
    write_json(sbom_path, payload)
    return payload


def grype_cache_has_data(cache_dir: Path) -> bool:
    return cache_dir.exists() and any(cache_dir.rglob("*"))


def ensure_grype_database(
    config: dict[str, Any],
    *,
    grype_db_cache_dir: Path = DEFAULT_GRYPE_DB_CACHE_DIR,
) -> None:
    grype_db_cache_dir = ensure_dir(grype_db_cache_dir)
    native_grype_binary = find_native_grype_binary()
    if native_grype_binary:
        command = [native_grype_binary, "db", "update"]
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "GRYPE_DB_CACHE_DIR": str(grype_db_cache_dir.resolve()),
            },
        )
    else:
        network_mode = docker_network_mode(config)
        command = docker_run_prefix(network_mode)
        command.extend(
            [
                "-v",
                f"{grype_db_cache_dir.resolve()}:/grype-db",
                "-e",
                "GRYPE_DB_CACHE_DIR=/grype-db",
                str(config["grype"]["container_image"]),
                "db",
                "update",
            ]
        )
        result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode == 0:
        return
    if grype_cache_has_data(grype_db_cache_dir):
        return
    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "failed to update the Grype database")


def normalize_fix_state(fix: dict[str, Any], versions: list[str]) -> str:
    state = fix.get("state")
    if isinstance(state, str) and state.strip():
        return state.strip()
    return "fixed" if versions else "unknown"


def normalize_grype_match(match: dict[str, Any]) -> dict[str, Any]:
    vulnerability = match.get("vulnerability") if isinstance(match.get("vulnerability"), dict) else {}
    artifact = match.get("artifact") if isinstance(match.get("artifact"), dict) else {}
    fix = match.get("fix") if isinstance(match.get("fix"), dict) else {}
    aliases: list[str] = []
    related = vulnerability.get("relatedVulnerabilities")
    if isinstance(related, list):
        for item in related:
            if isinstance(item, dict):
                candidate = item.get("id")
                if isinstance(candidate, str) and candidate and candidate not in aliases:
                    aliases.append(candidate)
    vulnerability_id = str(vulnerability.get("id", "UNKNOWN"))
    if vulnerability_id.startswith("CVE-") and vulnerability_id not in aliases:
        aliases.insert(0, vulnerability_id)
    locations: list[str] = []
    raw_locations = artifact.get("locations")
    if isinstance(raw_locations, list):
        for item in raw_locations:
            if isinstance(item, dict):
                path = item.get("path")
                if isinstance(path, str) and path:
                    locations.append(path)
    versions = [
        item
        for item in (fix.get("versions") if isinstance(fix.get("versions"), list) else [])
        if isinstance(item, str) and item
    ]
    return {
        "vulnerability_id": vulnerability_id,
        "aliases": aliases,
        "severity": str(vulnerability.get("severity", "UNKNOWN")).upper(),
        "namespace": vulnerability.get("namespace"),
        "description": vulnerability.get("description"),
        "package": {
            "name": artifact.get("name"),
            "version": artifact.get("version"),
            "type": artifact.get("type"),
            "locations": locations,
        },
        "fix": {
            "state": normalize_fix_state(fix, versions),
            "versions": versions,
        },
    }


def finding_has_fix(finding: dict[str, Any]) -> bool:
    fix = finding.get("fix") if isinstance(finding.get("fix"), dict) else {}
    versions = fix.get("versions")
    if isinstance(versions, list) and any(isinstance(item, str) and item for item in versions):
        return True
    state = fix.get("state")
    return isinstance(state, str) and state == "fixed"


def finding_fingerprint(finding: dict[str, Any]) -> str:
    package = finding.get("package") if isinstance(finding.get("package"), dict) else {}
    locations = package.get("locations") if isinstance(package.get("locations"), list) else []
    first_location = next((item for item in locations if isinstance(item, str) and item), "")
    return "|".join(
        (
            str(finding.get("vulnerability_id", "UNKNOWN")),
            str(package.get("name", "")),
            str(package.get("version", "")),
            first_location,
        )
    )


def build_summary(matches: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "unknown": 0,
        "blocking_findings_with_fix": 0,
        "total_matches": len(matches),
    }
    for finding in matches:
        severity = str(finding.get("severity", "UNKNOWN")).upper()
        if severity in SEVERITY_BUCKETS:
            summary[severity.lower()] += 1
        else:
            summary["unknown"] += 1
        if severity in {"CRITICAL", "HIGH"} and finding_has_fix(finding):
            summary["blocking_findings_with_fix"] += 1
    return summary


def grype_scan_sbom(
    *,
    image_id: str,
    image_ref: str,
    runtime_host: str | None,
    sbom_path: Path,
    cve_path: Path,
    scanned_at: datetime,
    config: dict[str, Any],
    grype_db_cache_dir: Path = DEFAULT_GRYPE_DB_CACHE_DIR,
) -> dict[str, Any]:
    grype_db_cache_dir = ensure_dir(grype_db_cache_dir)
    ensure_dir(cve_path.parent)
    native_grype_binary = find_native_grype_binary()
    if native_grype_binary:
        command = [
            native_grype_binary,
            f"sbom:{sbom_path}",
            "--add-cpes-if-none",
            "-o",
            "json",
        ]
        result = run_command(
            command,
            env={
                **os.environ,
                "GRYPE_DB_CACHE_DIR": str(grype_db_cache_dir.resolve()),
                "GRYPE_DB_AUTO_UPDATE": "false",
            },
        )
    else:
        network_mode = docker_network_mode(config)
        sbom_mount_source = host_path_for_repo_path(sbom_path.parent)
        command = docker_run_prefix(network_mode)
        command.extend(
            [
                "-v",
                f"{grype_db_cache_dir.resolve()}:/grype-db",
                "-v",
                f"{sbom_mount_source.resolve()}:/sbom",
                "-e",
                "GRYPE_DB_CACHE_DIR=/grype-db",
                "-e",
                "GRYPE_DB_AUTO_UPDATE=false",
                str(config["grype"]["container_image"]),
                f"sbom:/sbom/{sbom_path.name}",
                "--add-cpes-if-none",
                "-o",
                "json",
            ]
        )
        result = run_command(command)
    raw_payload = json.loads(result.stdout)
    normalized_matches = [
        normalize_grype_match(item) for item in raw_payload.get("matches", []) if isinstance(item, dict)
    ]
    receipt = {
        "schema_version": "1.0.0",
        "scanner": "grype",
        "scanner_image": config["grype"]["container_image"],
        "sbom_generator_image": config["syft"]["container_image"],
        "generated_at": isoformat_utc(scanned_at),
        "scanned_on": scanned_at.date().isoformat(),
        "image_id": image_id,
        "image_ref": image_ref,
        "runtime_host": runtime_host,
        "sbom_receipt": relpath(sbom_path),
        "summary": build_summary(normalized_matches),
        "matches": normalized_matches,
    }
    write_json(cve_path, receipt)
    return receipt


def scan_catalog_image(
    *,
    image_id: str,
    image_ref: str,
    runtime_host: str | None,
    platform_name: str = "linux/amd64",
    sbom_dir: Path = SBOM_RECEIPTS_DIR,
    cve_dir: Path = CVE_RECEIPTS_DIR,
    config: dict[str, Any] | None = None,
    scanned_at: datetime | None = None,
    syft_cache_dir: Path = DEFAULT_SYFT_CACHE_DIR,
    grype_db_cache_dir: Path = DEFAULT_GRYPE_DB_CACHE_DIR,
    update_grype_db: bool = False,
    use_artifact_cache: bool = True,
) -> tuple[Path, Path, dict[str, Any]]:
    config = config or load_scanner_config()
    scanned_at = scanned_at or now_utc()
    sbom_dir = ensure_dir(sbom_dir)
    cve_dir = ensure_dir(cve_dir)
    sbom_path = sbom_dir / f"{digest_short(image_ref)}.cdx.json"
    cve_path = cve_dir / f"{digest_short(image_ref)}-{timestamp_slug(scanned_at)}.grype.json"
    if not sbom_path.exists():
        syft_scan_image(
            image_ref,
            sbom_path=sbom_path,
            platform_name=platform_name,
            config=config,
            use_artifact_cache=use_artifact_cache,
            syft_cache_dir=syft_cache_dir,
        )
    if update_grype_db:
        ensure_grype_database(config, grype_db_cache_dir=grype_db_cache_dir)
    receipt = grype_scan_sbom(
        image_id=image_id,
        image_ref=image_ref,
        runtime_host=runtime_host,
        sbom_path=sbom_path,
        cve_path=cve_path,
        scanned_at=scanned_at,
        config=config,
        grype_db_cache_dir=grype_db_cache_dir,
    )
    return sbom_path, cve_path, receipt


def latest_cve_receipt_for_image(
    image_id: str, cve_dir: Path, *, exclude: Path | None = None
) -> tuple[Path, dict[str, Any]] | None:
    candidates = sorted(cve_dir.glob("*.grype.json"), reverse=True)
    for path in candidates:
        if exclude is not None and path.resolve() == exclude.resolve():
            continue
        try:
            payload = load_json(path)
        except Exception:
            continue
        if payload.get("image_id") == image_id:
            return path, payload
    return None


def net_new_high_or_critical_findings(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[dict[str, Any]]:
    previous_fingerprints = {
        finding_fingerprint(item)
        for item in (previous or {}).get("matches", [])
        if isinstance(item, dict) and str(item.get("severity", "UNKNOWN")).upper() in {"CRITICAL", "HIGH"}
    }
    findings: list[dict[str, Any]] = []
    for item in current.get("matches", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("severity", "UNKNOWN")).upper() not in {"CRITICAL", "HIGH"}:
            continue
        fingerprint = finding_fingerprint(item)
        if fingerprint not in previous_fingerprints:
            findings.append(item)
    return findings
