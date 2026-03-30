from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sbom_scanner as scanner  # noqa: E402


def test_artifact_cache_ref_rewrites_supported_public_registries() -> None:
    config = {
        "artifact_cache": {
            "host": "10.10.10.30",
            "mirrors": {
                "docker.io": 5001,
                "ghcr.io": 5002,
            },
        }
    }

    assert (
        scanner.artifact_cache_ref(
            "docker.io/library/nginx:1.29.1-alpine@sha256:deadbeef",
            config,
        )
        == "10.10.10.30:5001/library/nginx:1.29.1-alpine@sha256:deadbeef"
    )
    assert (
        scanner.artifact_cache_ref(
            "ghcr.io/dgtlmoon/changedetection.io:0.54.7@sha256:deadbeef",
            config,
        )
        == "10.10.10.30:5002/dgtlmoon/changedetection.io:0.54.7@sha256:deadbeef"
    )


def test_build_summary_counts_blocking_findings_with_fixes() -> None:
    summary = scanner.build_summary(
        [
            {"severity": "CRITICAL", "fix": {"state": "fixed", "versions": ["1.2.3"]}},
            {"severity": "HIGH", "fix": {"state": "unknown", "versions": []}},
            {"severity": "MEDIUM", "fix": {"state": "fixed", "versions": ["2.0.0"]}},
        ]
    )

    assert summary["critical"] == 1
    assert summary["high"] == 1
    assert summary["medium"] == 1
    assert summary["blocking_findings_with_fix"] == 1


def test_net_new_high_or_critical_findings_ignores_previous_duplicates() -> None:
    previous = {
        "matches": [
            {
                "vulnerability_id": "CVE-2026-0001",
                "severity": "HIGH",
                "package": {"name": "openssl", "version": "1.0.0", "locations": ["/usr/lib/libssl.so"]},
                "fix": {"state": "fixed", "versions": ["1.0.1"]},
            }
        ]
    }
    current = {
        "matches": [
            {
                "vulnerability_id": "CVE-2026-0001",
                "severity": "HIGH",
                "package": {"name": "openssl", "version": "1.0.0", "locations": ["/usr/lib/libssl.so"]},
                "fix": {"state": "fixed", "versions": ["1.0.1"]},
            },
            {
                "vulnerability_id": "CVE-2026-0002",
                "severity": "CRITICAL",
                "package": {"name": "bash", "version": "5.2", "locations": ["/bin/bash"]},
                "fix": {"state": "fixed", "versions": ["5.2-r1"]},
            },
        ]
    }

    findings = scanner.net_new_high_or_critical_findings(previous, current)

    assert len(findings) == 1
    assert findings[0]["vulnerability_id"] == "CVE-2026-0002"


def test_find_native_syft_binary_prefers_linux_install(monkeypatch) -> None:
    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        scanner.shutil,
        "which",
        lambda candidate: "/usr/local/bin/syft" if candidate == "/usr/local/bin/syft" else None,
    )

    assert scanner.find_native_syft_binary() == "/usr/local/bin/syft"


def test_syft_scan_image_uses_native_syft_on_linux(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    expected_payload = {"bomFormat": "CycloneDX"}

    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanner, "find_native_syft_binary", lambda: "/usr/local/bin/syft")
    monkeypatch.setattr(
        scanner,
        "run_command",
        lambda command, env=None: recorded.update({"command": command, "env": env})
        or type("Result", (), {"stdout": json.dumps(expected_payload)})(),
    )

    sbom_path = tmp_path / "receipts" / "image.cdx.json"
    payload = scanner.syft_scan_image(
        "ghcr.io/example/service:1.0.0@sha256:deadbeef",
        sbom_path=sbom_path,
        platform_name="linux/amd64",
        config={
            "artifact_cache": {
                "host": "10.10.10.30",
                "mirrors": {"ghcr.io": 5002},
            },
            "syft": {"container_image": "docker.io/anchore/syft:latest"},
        },
        syft_cache_dir=tmp_path / "receipts",
    )

    assert payload == expected_payload
    assert recorded["command"] == [
        "/usr/local/bin/syft",
        "scan",
        "--from",
        "registry",
        "10.10.10.30:5002/example/service:1.0.0@sha256:deadbeef",
        "--source-name",
        "ghcr.io/example/service:1.0.0@sha256:deadbeef",
        "--platform",
        "linux/amd64",
        "-o",
        "cyclonedx-json",
    ]
    env = recorded["env"]
    assert isinstance(env, dict)
    assert env["SYFT_REGISTRY_INSECURE_USE_HTTP"] == "true"
    assert env["SYFT_CACHE_DIR"] == str((tmp_path / "receipts").resolve())
    assert json.loads(sbom_path.read_text(encoding="utf-8")) == expected_payload


def test_syft_scan_image_falls_back_to_container_when_native_syft_missing(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    expected_payload = {"bomFormat": "CycloneDX"}

    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanner, "find_native_syft_binary", lambda: None)
    monkeypatch.setattr(
        scanner,
        "run_command",
        lambda command, env=None: recorded.update({"command": command, "env": env})
        or type("Result", (), {"stdout": json.dumps(expected_payload)})(),
    )

    sbom_path = tmp_path / "receipts" / "image.cdx.json"
    scanner.syft_scan_image(
        "docker.io/library/nginx:1.29.1@sha256:deadbeef",
        sbom_path=sbom_path,
        platform_name="linux/amd64",
        config={
            "docker_network": "host",
            "artifact_cache": {
                "host": "10.10.10.30",
                "mirrors": {"docker.io": 5001},
            },
            "syft": {"container_image": "docker.io/anchore/syft:latest"},
        },
        syft_cache_dir=tmp_path / "receipts",
    )

    assert recorded["command"] == [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-v",
        f"{(tmp_path / 'receipts').resolve()}:/syft-cache",
        "-e",
        "SYFT_CACHE_DIR=/syft-cache",
        "-e",
        "SYFT_REGISTRY_INSECURE_USE_HTTP=true",
        "docker.io/anchore/syft:latest",
        "scan",
        "--from",
        "registry",
        "10.10.10.30:5001/library/nginx:1.29.1@sha256:deadbeef",
        "--source-name",
        "docker.io/library/nginx:1.29.1@sha256:deadbeef",
        "--platform",
        "linux/amd64",
        "-o",
        "cyclonedx-json",
    ]
    assert recorded["env"] is None
