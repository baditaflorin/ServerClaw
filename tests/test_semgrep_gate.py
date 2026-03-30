from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "semgrep_gate.py"


def load_module(name: str = "semgrep_gate"):
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fake_semgrep(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "args = sys.argv[1:]",
                "capture = os.environ.get('SEMGREP_CAPTURE_ARGS')",
                "if capture:",
                "    Path(capture).write_text(json.dumps(args), encoding='utf-8')",
                "config = Path(args[args.index('--config') + 1]).stem",
                "output = Path(args[args.index('--output') + 1])",
                "fixture_dir = Path(os.environ['SEMGREP_FIXTURE_DIR'])",
                "payload = json.loads((fixture_dir / f'{config}.json').read_text(encoding='utf-8'))",
                "output.write_text(json.dumps(payload), encoding='utf-8')",
                "raise SystemExit(int(os.environ.get('SEMGREP_EXIT_CODE', '0')))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def sarif_result(rule_id: str, level: str, uri: str, line: int, message: str) -> dict[str, object]:
    return {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": line},
                }
            }
        ],
    }


def sarif_payload(*results: dict[str, object]) -> dict[str, object]:
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {"driver": {"name": "semgrep"}},
                "results": list(results),
            }
        ],
    }


def test_semgrep_gate_merges_sarif_and_accepts_exit_code_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module("semgrep_gate_exit_code")
    fake_semgrep = tmp_path / "fake-semgrep"
    fixture_dir = tmp_path / "fixtures"
    repo_root = tmp_path / "repo"
    output_dir = tmp_path / "receipts" / "sast"
    summary_path = tmp_path / "semgrep-summary.json"

    fixture_dir.mkdir()
    repo_root.mkdir()
    write_fake_semgrep(fake_semgrep)
    (fixture_dir / "secrets.json").write_text(
        json.dumps(
            sarif_payload(
                sarif_result(
                    "lv3.semgrep.secret.live-token-prefix",
                    "error",
                    "scripts/example.py",
                    5,
                    "hardcoded token prefix",
                )
            )
        ),
        encoding="utf-8",
    )
    (fixture_dir / "sast.json").write_text(
        json.dumps(
            sarif_payload(
                sarif_result(
                    "lv3.semgrep.python.eval",
                    "warning",
                    "platform/example.py",
                    9,
                    "avoid eval",
                )
            )
        ),
        encoding="utf-8",
    )
    (fixture_dir / "dockerfile.json").write_text(
        json.dumps(
            sarif_payload(
                sarif_result(
                    "lv3.semgrep.docker.from-latest",
                    "note",
                    "docker/example/Dockerfile",
                    1,
                    "pin from image",
                )
            )
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("LV3_SEMGREP_BIN", str(fake_semgrep))
    monkeypatch.setenv("SEMGREP_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("SEMGREP_EXIT_CODE", "1")
    monkeypatch.setenv("GITHUB_SHA", "deadbeef")

    exit_code = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--output-dir",
            str(output_dir),
            "--summary-file",
            str(summary_path),
        ]
    )

    assert exit_code == 1
    sarif_path = output_dir / "deadbeef.sarif.json"
    merged = json.loads(sarif_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert len(merged["runs"]) == 3
    assert summary["status"] == "failed"
    assert summary["counts"] == {
        "error": 1,
        "warning": 1,
        "note": 1,
        "none": 0,
        "total": 3,
    }
    assert summary["blocking_findings"] == 1


def test_semgrep_gate_emits_only_net_new_mutation_audit_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module("semgrep_gate_mutation_audit")
    fake_semgrep = tmp_path / "fake-semgrep"
    fixture_dir = tmp_path / "fixtures"
    repo_root = tmp_path / "repo"
    output_path = tmp_path / "current.sarif.json"
    summary_path = tmp_path / "semgrep-summary.json"
    baseline_path = tmp_path / "baseline.sarif.json"
    emitted: list[dict[str, object]] = []

    fixture_dir.mkdir()
    repo_root.mkdir()
    write_fake_semgrep(fake_semgrep)
    shared_result = sarif_result(
        "lv3.semgrep.python.subprocess-shell-true",
        "warning",
        "platform/operator_access/adapters.py",
        445,
        "avoid subprocess shell=True",
    )
    new_result = sarif_result(
        "lv3.semgrep.ansible.shell-pipe-to-shell",
        "warning",
        "playbooks/example.yml",
        12,
        "do not pipe remote content into a shell",
    )
    (fixture_dir / "secrets.json").write_text(json.dumps(sarif_payload(shared_result)), encoding="utf-8")
    (fixture_dir / "sast.json").write_text(json.dumps(sarif_payload(new_result)), encoding="utf-8")
    (fixture_dir / "dockerfile.json").write_text(json.dumps(sarif_payload()), encoding="utf-8")
    baseline_path.write_text(json.dumps(sarif_payload(shared_result)), encoding="utf-8")

    monkeypatch.setenv("LV3_SEMGREP_BIN", str(fake_semgrep))
    monkeypatch.setenv("SEMGREP_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("SEMGREP_EXIT_CODE", "0")
    monkeypatch.setenv("GITHUB_SHA", "cafebabe")

    def capture_event(event: dict[str, object], **_: object) -> bool:
        emitted.append(event)
        return True

    monkeypatch.setattr(module, "emit_event_best_effort", capture_event)

    exit_code = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--output-file",
            str(output_path),
            "--summary-file",
            str(summary_path),
            "--baseline-sarif",
            str(baseline_path),
            "--emit-mutation-audit",
        ]
    )

    assert exit_code == 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["status"] == "passed"
    assert summary["net_new_findings"] == 1
    assert summary["mutation_audit_events_emitted"] == 1
    assert len(emitted) == 1
    assert emitted[0]["action"] == "sast_finding_introduced"
    assert str(emitted[0]["target"]).startswith("lv3.semgrep.ansible.shell-pipe-to-shell|")


def test_semgrep_gate_uses_no_git_ignore_for_snapshot_checkouts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module("semgrep_gate_snapshot_checkout")
    fake_semgrep = tmp_path / "fake-semgrep"
    fixture_dir = tmp_path / "fixtures"
    repo_root = tmp_path / "repo"
    output_dir = tmp_path / "receipts" / "sast"
    summary_path = tmp_path / "semgrep-summary.json"
    capture_path = tmp_path / "captured-args.json"

    fixture_dir.mkdir()
    repo_root.mkdir()
    write_fake_semgrep(fake_semgrep)
    (fixture_dir / "secrets.json").write_text(json.dumps(sarif_payload()), encoding="utf-8")
    (fixture_dir / "sast.json").write_text(
        json.dumps(
            sarif_payload(
                sarif_result(
                    "lv3.semgrep.python.eval",
                    "warning",
                    "scripts/example.py",
                    1,
                    "avoid eval",
                )
            )
        ),
        encoding="utf-8",
    )
    (fixture_dir / "dockerfile.json").write_text(json.dumps(sarif_payload()), encoding="utf-8")

    monkeypatch.setenv("LV3_SEMGREP_BIN", str(fake_semgrep))
    monkeypatch.setenv("SEMGREP_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("SEMGREP_CAPTURE_ARGS", str(capture_path))
    monkeypatch.setenv("SEMGREP_EXIT_CODE", "1")

    exit_code = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--output-dir",
            str(output_dir),
            "--summary-file",
            str(summary_path),
        ]
    )

    captured_args = json.loads(capture_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "--no-git-ignore" in captured_args
    assert summary["counts"]["warning"] == 1
    assert summary["baseline_requested"] is False
    assert summary["baseline_resolved"] is False


def test_semgrep_gate_skips_baseline_compare_when_checkout_has_no_git_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module("semgrep_gate_snapshot_baseline")
    fake_semgrep = tmp_path / "fake-semgrep"
    fixture_dir = tmp_path / "fixtures"
    repo_root = tmp_path / "repo"
    output_dir = tmp_path / "receipts" / "sast"
    summary_path = tmp_path / "semgrep-summary.json"
    emitted: list[dict[str, object]] = []

    fixture_dir.mkdir()
    repo_root.mkdir()
    write_fake_semgrep(fake_semgrep)
    (fixture_dir / "secrets.json").write_text(json.dumps(sarif_payload()), encoding="utf-8")
    (fixture_dir / "sast.json").write_text(
        json.dumps(
            sarif_payload(
                sarif_result(
                    "lv3.semgrep.python.subprocess-shell-true",
                    "warning",
                    "scripts/example.py",
                    3,
                    "avoid subprocess shell=True",
                )
            )
        ),
        encoding="utf-8",
    )
    (fixture_dir / "dockerfile.json").write_text(json.dumps(sarif_payload()), encoding="utf-8")

    monkeypatch.setenv("LV3_SEMGREP_BIN", str(fake_semgrep))
    monkeypatch.setenv("SEMGREP_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("SEMGREP_EXIT_CODE", "1")

    def capture_event(event: dict[str, object], **_: object) -> bool:
        emitted.append(event)
        return True

    monkeypatch.setattr(module, "emit_event_best_effort", capture_event)

    exit_code = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--output-dir",
            str(output_dir),
            "--summary-file",
            str(summary_path),
            "--baseline-ref",
            "origin/main",
            "--emit-mutation-audit",
        ]
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert summary["baseline_requested"] is True
    assert summary["baseline_resolved"] is False
    assert summary["baseline_skip_reason"] == "checkout has no git metadata"
    assert summary["net_new_findings"] == 0
    assert summary["mutation_audit_events_emitted"] == 0
    assert emitted == []


def test_semgrep_gate_skips_baseline_compare_when_baseline_lacks_rules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module("semgrep_gate_missing_baseline_rules")
    fake_semgrep = tmp_path / "fake-semgrep"
    fixture_dir = tmp_path / "fixtures"
    repo_root = tmp_path / "repo"
    output_dir = tmp_path / "receipts" / "sast"
    summary_path = tmp_path / "semgrep-summary.json"

    fixture_dir.mkdir()
    repo_root.mkdir()
    rules_root = repo_root / "config" / "semgrep" / "rules"
    rules_root.mkdir(parents=True)
    for name in ("secrets", "sast", "dockerfile"):
        (rules_root / f"{name}.yaml").write_text("rules: []\n", encoding="utf-8")
    write_fake_semgrep(fake_semgrep)
    (fixture_dir / "secrets.json").write_text(json.dumps(sarif_payload()), encoding="utf-8")
    (fixture_dir / "sast.json").write_text(json.dumps(sarif_payload()), encoding="utf-8")
    (fixture_dir / "dockerfile.json").write_text(json.dumps(sarif_payload()), encoding="utf-8")

    monkeypatch.setenv("LV3_SEMGREP_BIN", str(fake_semgrep))
    monkeypatch.setenv("SEMGREP_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("SEMGREP_EXIT_CODE", "0")
    monkeypatch.setattr(module, "checkout_has_git_index", lambda _: True)
    monkeypatch.setattr(
        module,
        "RULESETS",
        (
            module.RuleSet("secrets", rules_root / "secrets.yaml"),
            module.RuleSet("sast", rules_root / "sast.yaml"),
            module.RuleSet("dockerfile", rules_root / "dockerfile.yaml"),
        ),
    )

    def fake_export_git_ref(_: Path, __: str, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(module, "export_git_ref", fake_export_git_ref)

    exit_code = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--output-dir",
            str(output_dir),
            "--summary-file",
            str(summary_path),
            "--baseline-ref",
            "origin/main",
        ]
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert summary["baseline_requested"] is True
    assert summary["baseline_resolved"] is False
    assert summary["baseline_skip_reason"] == (
        "baseline ref origin/main does not contain config/semgrep/rules/secrets.yaml"
    )
