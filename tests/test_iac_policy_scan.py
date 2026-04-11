from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "iac_policy_scan.py"
CUSTOM_CHECKS_PATH = REPO_ROOT / "config" / "checkov" / "checks" / "terraform" / "lv3_proxmox_checks.py"


def load_module(name: str, path: Path):
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_policy(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "default_level": "note",
                "blocking_levels": ["error"],
                "scan_groups": [
                    {
                        "id": "tofu",
                        "title": "Tofu",
                        "framework": "terraform",
                        "path": "tofu",
                    }
                ],
                "level_overrides": {
                    "CKV_LV3_1": "error",
                    "CKV_LV3_2": "error",
                    "CKV_LV3_3": "error",
                    "CKV_LV3_4": "warning",
                },
                "compose_template_globs": ["roles/*/templates/docker-compose.yml.j2"],
                "compose_gap_note": "bounded gap",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def write_skip_catalog(path: Path) -> None:
    path.write_text(
        yaml.safe_dump({"schema_version": "1.0.0", "suppressions": []}, sort_keys=False),
        encoding="utf-8",
    )


def fake_checkov_payload(*, check_id: str, path: str, line_range: list[int], severity: str | None = None) -> dict:
    return {
        "check_type": "terraform",
        "results": {
            "failed_checks": [
                {
                    "check_id": check_id,
                    "check_name": "example finding",
                    "check_result": {"result": "FAILED", "evaluated_keys": ["disk"]},
                    "file_path": f"/{path}",
                    "repo_file_path": f"/{path}",
                    "file_abs_path": f"/tmp/repo/{path}",
                    "file_line_range": line_range,
                    "resource": "resource.example",
                    "guideline": "https://example.invalid/check",
                    "severity": severity,
                }
            ]
        },
        "summary": {
            "passed": 0,
            "failed": 1,
            "skipped": 0,
            "parsing_errors": 0,
            "resource_count": 1,
            "checkov_version": "3.2.469",
        },
    }


def install_fake_hcl2(monkeypatch, document_or_loader) -> None:
    if callable(document_or_loader):
        loader = document_or_loader
    else:
        loader = lambda _handle: document_or_loader
    monkeypatch.setitem(sys.modules, "hcl2", SimpleNamespace(load=loader))


def test_iac_policy_scan_writes_summary_and_sarif(tmp_path: Path, monkeypatch, capsys) -> None:
    module = load_module("iac_policy_scan_module", MODULE_PATH)
    repo_root = tmp_path / "repo"
    (repo_root / "tofu").mkdir(parents=True)
    (repo_root / "tofu" / "main.tf").write_text("resource {}\n", encoding="utf-8")
    (repo_root / "roles" / "demo" / "templates").mkdir(parents=True)
    (repo_root / "roles" / "demo" / "templates" / "docker-compose.yml.j2").write_text(
        "services: {}\n",
        encoding="utf-8",
    )
    policy_path = repo_root / "policy.yaml"
    skip_path = repo_root / "skip.yaml"
    summary_path = repo_root / "receipts" / "checkov" / "summary.json"
    sarif_path = repo_root / "receipts" / "checkov" / "summary.sarif.json"
    write_policy(policy_path)
    write_skip_catalog(skip_path)

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        if command[:2] == ["checkov", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="3.2.469\n", stderr="")
        if command[0] == "checkov":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    fake_checkov_payload(
                        check_id="CKV_LV3_1",
                        path="tofu/main.tf",
                        line_range=[5, 7],
                    )
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "detect_source_commit", lambda _repo_root: "abc123def456")
    monkeypatch.setattr(module, "scan_tofu_custom_findings", lambda **_kwargs: [])

    exit_code = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--policy",
            str(policy_path),
            "--skip-catalog",
            str(skip_path),
            "--checkov-binary",
            "checkov",
            "--write-summary",
            str(summary_path),
            "--write-sarif",
            str(sarif_path),
            "--print-json",
        ]
    )

    assert exit_code == 1
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    assert summary["counts"]["error"] == 1
    assert summary["compose_surface_notes"] == ["Detected 1 Docker Compose template file(s). bounded gap"]
    assert summary["findings"][0]["check_id"] == "CKV_LV3_1"
    assert sarif["runs"][0]["results"][0]["ruleId"] == "CKV_LV3_1"
    assert "IaC policy scan failed" in capsys.readouterr().out


def test_iac_policy_scan_applies_suppressions(tmp_path: Path, monkeypatch) -> None:
    module = load_module("iac_policy_scan_module_suppressions", MODULE_PATH)
    repo_root = tmp_path / "repo"
    (repo_root / "tofu").mkdir(parents=True)
    (repo_root / "tofu" / "main.tf").write_text("resource {}\n", encoding="utf-8")
    policy_path = repo_root / "policy.yaml"
    skip_path = repo_root / "skip.yaml"
    summary_path = repo_root / "receipts" / "checkov" / "summary.json"
    sarif_path = repo_root / "receipts" / "checkov" / "summary.sarif.json"
    write_policy(policy_path)
    skip_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "suppressions": [
                    {
                        "check_id": "CKV_LV3_1",
                        "file": "tofu/main.tf",
                        "line_range": [1, 20],
                        "reason": "test suppression",
                        "decision_ref": "ADR 0306",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        if command[:2] == ["checkov", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="3.2.469\n", stderr="")
        if command[0] == "checkov":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    fake_checkov_payload(
                        check_id="CKV_LV3_1",
                        path="tofu/main.tf",
                        line_range=[5, 7],
                    )
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "detect_source_commit", lambda _repo_root: "abc123def456")
    monkeypatch.setattr(module, "scan_tofu_custom_findings", lambda **_kwargs: [])

    exit_code = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--policy",
            str(policy_path),
            "--skip-catalog",
            str(skip_path),
            "--checkov-binary",
            "checkov",
            "--write-summary",
            str(summary_path),
            "--write-sarif",
            str(sarif_path),
        ]
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["status"] == "passed"
    assert summary["counts"]["error"] == 0
    assert summary["counts"]["suppressed"] == 1
    assert summary["suppressed_findings"][0]["suppression"]["reason"] == "test suppression"


def test_iac_policy_scan_enforces_custom_tofu_invariants(tmp_path: Path, monkeypatch) -> None:
    module = load_module("iac_policy_scan_module_custom_tofu", MODULE_PATH)
    repo_root = tmp_path / "repo"
    (repo_root / "tofu" / "environments" / "production").mkdir(parents=True)
    (repo_root / "tofu" / "modules" / "proxmox-vm").mkdir(parents=True)
    (repo_root / "tofu" / "environments" / "production" / "main.tf").write_text(
        "\n".join(
            [
                'provider "proxmox" {',
                "  insecure = true",
                "}",
                "",
                'module "docker_runtime" {',
                '  source = "../../modules/proxmox-vm"',
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "tofu" / "modules" / "proxmox-vm" / "main.tf").write_text(
        "\n".join(
            [
                'resource "proxmox_virtual_environment_vm" "this" {',
                "  disk {",
                "    backup = false",
                "  }",
                "  network_device {",
                '    bridge = "vmbr10"',
                "  }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    policy_path = repo_root / "policy.yaml"
    skip_path = repo_root / "skip.yaml"
    summary_path = repo_root / "receipts" / "checkov" / "summary.json"
    sarif_path = repo_root / "receipts" / "checkov" / "summary.sarif.json"
    write_policy(policy_path)
    write_skip_catalog(skip_path)

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        if command[0] == "checkov":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "passed": 0,
                        "failed": 0,
                        "skipped": 0,
                        "parsing_errors": 0,
                        "resource_count": 0,
                        "checkov_version": "3.2.469",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "detect_source_commit", lambda _repo_root: "abc123def456")
    install_fake_hcl2(
        monkeypatch,
        lambda handle: (
            {
                "provider": [{"proxmox": {"insecure": True}}],
                "module": [{"docker_runtime": {"source": "../../modules/proxmox-vm"}}],
            }
            if "environments/production/main.tf" in Path(handle.name).as_posix()
            else {
                "resource": [
                    {
                        "proxmox_virtual_environment_vm": {
                            "this": {
                                "disk": [{"backup": False}],
                                "network_device": [{"bridge": "vmbr10"}],
                            }
                        }
                    }
                ]
            }
        ),
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--policy",
            str(policy_path),
            "--skip-catalog",
            str(skip_path),
            "--checkov-binary",
            "checkov",
            "--write-summary",
            str(summary_path),
            "--write-sarif",
            str(sarif_path),
        ]
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ids = {item["check_id"] for item in summary["findings"]}
    assert exit_code == 1
    assert {"CKV_LV3_1", "CKV_LV3_2", "CKV_LV3_3", "CKV_LV3_4"} <= ids
    assert summary["counts"]["error"] == 3
    assert summary["counts"]["warning"] == 1


def test_custom_proxmox_checks_cover_current_invariants() -> None:
    pytest = __import__("pytest")
    pytest.importorskip("checkov.common.models.enums")
    custom_checks = load_module("lv3_proxmox_checks", CUSTOM_CHECKS_PATH)
    from checkov.common.models.enums import CheckResult  # type: ignore[import-not-found]

    disk_check = custom_checks.EnsureProxmoxVmDisksParticipateInBackup()
    mac_check = custom_checks.EnsureProxmoxVmMacAddressIsPinned()
    module_check = custom_checks.EnsureProxmoxModuleCallsDeclareMacAddress()
    provider_check = custom_checks.EnsureProxmoxProviderTlsVerificationStaysEnabled()

    assert disk_check.scan_resource_conf({"disk": [{"backup": [True]}, {"backup": [True]}]}) == CheckResult.PASSED
    assert disk_check.scan_resource_conf({"disk": [{"backup": [False]}]}) == CheckResult.FAILED
    assert (
        mac_check.scan_resource_conf({"network_device": [{"mac_address": ["BC:24:11:00:00:01"]}]}) == CheckResult.PASSED
    )
    assert mac_check.scan_resource_conf({"network_device": [{"bridge": ["vmbr10"]}]}) == CheckResult.FAILED
    assert (
        module_check.scan_module_conf({"source": ["../../modules/proxmox-vm"], "mac_address": ["BC:24:11:00:00:02"]})
        == CheckResult.PASSED
    )
    assert module_check.scan_module_conf({"source": ["../../modules/proxmox-vm"]}) == CheckResult.FAILED
    assert module_check.scan_module_conf({"source": ["../../modules/other"]}) == CheckResult.UNKNOWN
    assert provider_check.scan_provider_conf({"insecure": [True]}) == CheckResult.FAILED
    assert provider_check.scan_provider_conf({"insecure": [False]}) == CheckResult.PASSED
