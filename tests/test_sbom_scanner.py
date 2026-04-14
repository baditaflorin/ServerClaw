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
            "host": "10.10.10.80",
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
        == "10.10.10.80:5001/library/nginx:1.29.1-alpine@sha256:deadbeef"
    )
    assert (
        scanner.artifact_cache_ref(
            "ghcr.io/dgtlmoon/changedetection.io:0.54.7@sha256:deadbeef",
            config,
        )
        == "10.10.10.80:5002/dgtlmoon/changedetection.io:0.54.7@sha256:deadbeef"
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


def test_find_native_syft_binary_prefers_available_install_on_darwin(monkeypatch) -> None:
    monkeypatch.setattr(scanner.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        scanner.shutil,
        "which",
        lambda candidate: "/usr/local/bin/syft" if candidate == "/usr/local/bin/syft" else None,
    )

    assert scanner.find_native_syft_binary() == "/usr/local/bin/syft"


def test_find_native_grype_binary_prefers_available_install_on_darwin(monkeypatch) -> None:
    monkeypatch.setattr(scanner.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        scanner.shutil,
        "which",
        lambda candidate: "/usr/local/bin/grype" if candidate == "/usr/local/bin/grype" else None,
    )

    assert scanner.find_native_grype_binary() == "/usr/local/bin/grype"


def test_host_path_for_repo_path_uses_workspace_host(monkeypatch) -> None:
    monkeypatch.setenv("LV3_DOCKER_WORKSPACE_PATH", "/host/workspace")
    candidate = scanner.REPO_ROOT / "receipts" / "sbom" / "image.cdx.json"

    assert scanner.host_path_for_repo_path(candidate) == Path("/host/workspace/receipts/sbom/image.cdx.json")


def test_relpath_falls_back_to_shared_repo_root_for_worktree_receipts(monkeypatch, tmp_path: Path) -> None:
    shared_root = tmp_path
    worktree_root = shared_root / ".worktrees" / "ws-0368"
    receipt_path = shared_root / "receipts" / "sbom" / "image.cdx.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(scanner, "REPO_ROOT", worktree_root)
    monkeypatch.setattr(scanner, "shared_repo_root", lambda _repo_root=None: shared_root)

    assert scanner.relpath(receipt_path) == "receipts/sbom/image.cdx.json"


def test_host_path_for_repo_path_uses_shared_repo_root_for_worktree_receipts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    shared_root = tmp_path
    worktree_root = shared_root / ".worktrees" / "ws-0368"
    receipt_path = shared_root / "receipts" / "sbom" / "image.cdx.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("LV3_DOCKER_WORKSPACE_PATH", "/host/workspace")
    monkeypatch.setattr(scanner, "REPO_ROOT", worktree_root)
    monkeypatch.setattr(scanner, "shared_repo_root", lambda _repo_root=None: shared_root)

    assert scanner.host_path_for_repo_path(receipt_path) == Path("/host/workspace/receipts/sbom/image.cdx.json")


def test_syft_scan_image_uses_native_syft_on_linux(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    expected_payload = {"bomFormat": "CycloneDX"}

    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanner, "find_native_syft_binary", lambda: "/usr/local/bin/syft")
    monkeypatch.setattr(
        scanner,
        "run_command",
        lambda command, env=None: (
            recorded.update({"command": command, "env": env})
            or type("Result", (), {"stdout": json.dumps(expected_payload)})()
        ),
    )

    sbom_path = tmp_path / "receipts" / "image.cdx.json"
    payload = scanner.syft_scan_image(
        "ghcr.io/example/service:1.0.0@sha256:deadbeef",
        sbom_path=sbom_path,
        platform_name="linux/amd64",
        config={
            "artifact_cache": {
                "host": "10.10.10.80",
                "mirrors": {"ghcr.io": 5002},
            },
            "syft": {"container_image": "docker.io/anchore/syft:latest"},
        },
        syft_cache_dir=tmp_path / "receipts",
        syft_tmp_dir=tmp_path / "syft-tmp",
    )

    assert payload == expected_payload
    assert recorded["command"] == [
        "/usr/local/bin/syft",
        "scan",
        "--from",
        "registry",
        "10.10.10.80:5002/example/service:1.0.0@sha256:deadbeef",
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
    assert env["TMPDIR"] == str((tmp_path / "syft-tmp").resolve())
    assert env["TMP"] == str((tmp_path / "syft-tmp").resolve())
    assert env["TEMP"] == str((tmp_path / "syft-tmp").resolve())
    assert json.loads(sbom_path.read_text(encoding="utf-8")) == expected_payload


def test_syft_scan_image_uses_native_syft_on_darwin(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    expected_payload = {"bomFormat": "CycloneDX"}

    monkeypatch.setattr(scanner.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(scanner, "find_native_syft_binary", lambda: "/opt/homebrew/bin/syft")
    monkeypatch.setattr(
        scanner,
        "run_command",
        lambda command, env=None: (
            recorded.update({"command": command, "env": env})
            or type("Result", (), {"stdout": json.dumps(expected_payload)})()
        ),
    )

    sbom_path = tmp_path / "receipts" / "image.cdx.json"
    scanner.syft_scan_image(
        "docker.io/library/nginx:1.29.1@sha256:deadbeef",
        sbom_path=sbom_path,
        platform_name="linux/amd64",
        config={
            "artifact_cache": {
                "host": "10.10.10.80",
                "mirrors": {"docker.io": 5001},
            },
            "syft": {"container_image": "docker.io/anchore/syft:latest"},
        },
        use_artifact_cache=False,
        syft_cache_dir=tmp_path / "receipts",
        syft_tmp_dir=tmp_path / "syft-tmp",
    )

    assert recorded["command"] == [
        "/opt/homebrew/bin/syft",
        "scan",
        "--from",
        "registry",
        "docker.io/library/nginx:1.29.1@sha256:deadbeef",
        "--source-name",
        "docker.io/library/nginx:1.29.1@sha256:deadbeef",
        "--platform",
        "linux/amd64",
        "-o",
        "cyclonedx-json",
    ]


def test_syft_scan_image_falls_back_to_container_when_native_syft_missing(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    expected_payload = {"bomFormat": "CycloneDX"}

    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanner, "find_native_syft_binary", lambda: None)
    monkeypatch.setattr(
        scanner,
        "run_command",
        lambda command, env=None: (
            recorded.update({"command": command, "env": env})
            or type("Result", (), {"stdout": json.dumps(expected_payload)})()
        ),
    )

    sbom_path = tmp_path / "receipts" / "image.cdx.json"
    scanner.syft_scan_image(
        "docker.io/library/nginx:1.29.1@sha256:deadbeef",
        sbom_path=sbom_path,
        platform_name="linux/amd64",
        config={
            "docker_network": "host",
            "artifact_cache": {
                "host": "10.10.10.80",
                "mirrors": {"docker.io": 5001},
            },
            "syft": {"container_image": "docker.io/anchore/syft:latest"},
        },
        syft_cache_dir=tmp_path / "receipts",
        syft_tmp_dir=tmp_path / "syft-tmp",
    )

    assert recorded["command"] == [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-v",
        f"{(tmp_path / 'receipts').resolve()}:/syft-cache",
        "-v",
        f"{(tmp_path / 'syft-tmp').resolve()}:/syft-tmp",
        "-e",
        "SYFT_CACHE_DIR=/syft-cache",
        "-e",
        "TMPDIR=/syft-tmp",
        "-e",
        "TMP=/syft-tmp",
        "-e",
        "TEMP=/syft-tmp",
        "-e",
        "SYFT_REGISTRY_INSECURE_USE_HTTP=true",
        "docker.io/anchore/syft:latest",
        "scan",
        "--from",
        "registry",
        "10.10.10.80:5001/library/nginx:1.29.1@sha256:deadbeef",
        "--source-name",
        "docker.io/library/nginx:1.29.1@sha256:deadbeef",
        "--platform",
        "linux/amd64",
        "-o",
        "cyclonedx-json",
    ]
    assert recorded["env"] is None


def test_ensure_grype_database_uses_native_grype_on_linux(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}

    def fake_run(command, text, capture_output, check, env=None):  # noqa: ANN001
        recorded["command"] = command
        recorded["env"] = env
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanner, "find_native_grype_binary", lambda: "/usr/local/bin/grype")
    monkeypatch.setattr(scanner.subprocess, "run", fake_run)

    scanner.ensure_grype_database(
        {"grype": {"container_image": "docker.io/anchore/grype:latest"}},
        grype_db_cache_dir=tmp_path / "grype-db",
    )

    assert recorded["command"] == ["/usr/local/bin/grype", "db", "update"]
    env = recorded["env"]
    assert isinstance(env, dict)
    assert env["GRYPE_DB_CACHE_DIR"] == str((tmp_path / "grype-db").resolve())


def test_grype_scan_sbom_uses_native_grype_on_linux(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    expected_payload = {"matches": []}

    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanner, "find_native_grype_binary", lambda: "/usr/local/bin/grype")
    monkeypatch.setattr(scanner, "relpath", lambda path: str(path))
    monkeypatch.setattr(
        scanner,
        "run_command",
        lambda command, env=None: (
            recorded.update({"command": command, "env": env})
            or type("Result", (), {"stdout": json.dumps(expected_payload)})()
        ),
    )

    sbom_path = tmp_path / "receipts" / "image.cdx.json"
    sbom_path.parent.mkdir(parents=True, exist_ok=True)
    sbom_path.write_text("{}", encoding="utf-8")
    cve_path = tmp_path / "receipts" / "image.grype.json"

    scanner.grype_scan_sbom(
        image_id="example",
        image_ref="ghcr.io/example/service:1.0.0@sha256:deadbeef",
        runtime_host="docker-runtime",
        sbom_path=sbom_path,
        cve_path=cve_path,
        scanned_at=scanner.now_utc(),
        config={
            "grype": {"container_image": "docker.io/anchore/grype:latest"},
            "syft": {"container_image": "docker.io/anchore/syft:latest"},
        },
        grype_db_cache_dir=tmp_path / "grype-db",
    )

    assert recorded["command"] == [
        "/usr/local/bin/grype",
        f"sbom:{sbom_path}",
        "--add-cpes-if-none",
        "-o",
        "json",
    ]
    env = recorded["env"]
    assert isinstance(env, dict)
    assert env["GRYPE_DB_CACHE_DIR"] == str((tmp_path / "grype-db").resolve())
    assert env["GRYPE_DB_AUTO_UPDATE"] == "false"


def test_grype_scan_sbom_uses_native_grype_on_darwin(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    expected_payload = {"matches": []}

    monkeypatch.setattr(scanner.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(scanner, "find_native_grype_binary", lambda: "/opt/homebrew/bin/grype")
    monkeypatch.setattr(scanner, "relpath", lambda path: str(path))
    monkeypatch.setattr(
        scanner,
        "run_command",
        lambda command, env=None: (
            recorded.update({"command": command, "env": env})
            or type("Result", (), {"stdout": json.dumps(expected_payload)})()
        ),
    )

    sbom_path = tmp_path / "receipts" / "image.cdx.json"
    sbom_path.parent.mkdir(parents=True, exist_ok=True)
    sbom_path.write_text("{}", encoding="utf-8")
    cve_path = tmp_path / "receipts" / "image.grype.json"

    scanner.grype_scan_sbom(
        image_id="example",
        image_ref="ghcr.io/example/service:1.0.0@sha256:deadbeef",
        runtime_host="docker-runtime",
        sbom_path=sbom_path,
        cve_path=cve_path,
        scanned_at=scanner.now_utc(),
        config={
            "grype": {"container_image": "docker.io/anchore/grype:latest"},
            "syft": {"container_image": "docker.io/anchore/syft:latest"},
        },
        grype_db_cache_dir=tmp_path / "grype-db",
    )

    assert recorded["command"] == [
        "/opt/homebrew/bin/grype",
        f"sbom:{sbom_path}",
        "--add-cpes-if-none",
        "-o",
        "json",
    ]


def test_grype_scan_sbom_falls_back_to_container_when_native_grype_missing(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    expected_payload = {"matches": []}

    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanner, "find_native_grype_binary", lambda: None)
    monkeypatch.setattr(scanner, "relpath", lambda path: str(path))
    monkeypatch.setattr(
        scanner,
        "run_command",
        lambda command, env=None: (
            recorded.update({"command": command, "env": env})
            or type("Result", (), {"stdout": json.dumps(expected_payload)})()
        ),
    )

    sbom_path = tmp_path / "receipts" / "image.cdx.json"
    sbom_path.parent.mkdir(parents=True, exist_ok=True)
    sbom_path.write_text("{}", encoding="utf-8")
    cve_path = tmp_path / "receipts" / "image.grype.json"

    scanner.grype_scan_sbom(
        image_id="example",
        image_ref="ghcr.io/example/service:1.0.0@sha256:deadbeef",
        runtime_host="docker-runtime",
        sbom_path=sbom_path,
        cve_path=cve_path,
        scanned_at=scanner.now_utc(),
        config={
            "docker_network": "host",
            "grype": {"container_image": "docker.io/anchore/grype:latest"},
            "syft": {"container_image": "docker.io/anchore/syft:latest"},
        },
        grype_db_cache_dir=tmp_path / "grype-db",
    )

    assert recorded["command"] == [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-v",
        f"{(tmp_path / 'grype-db').resolve()}:/grype-db",
        "-v",
        f"{sbom_path.parent.resolve()}:/sbom",
        "-e",
        "GRYPE_DB_CACHE_DIR=/grype-db",
        "-e",
        "GRYPE_DB_AUTO_UPDATE=false",
        "docker.io/anchore/grype:latest",
        f"sbom:/sbom/{sbom_path.name}",
        "--add-cpes-if-none",
        "-o",
        "json",
    ]
    assert recorded["env"] is None
