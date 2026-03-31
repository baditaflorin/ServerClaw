from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_repo(tmp_path: Path) -> Path:
    write(
        tmp_path / ".gitleaks.toml",
        "\n".join(
            [
                "[[rules]]",
                'id = "openbao-token"',
                'description = "OpenBao token"',
                "regex = '''TESTSECRET_[A-Za-z0-9_-]{20,}'''",
                "",
                "[[rules]]",
                'id = "placeholder-token"',
                'description = "Placeholder token"',
                "regex = '''example-token-here'''",
                "",
                "[allowlist]",
                'description = "placeholders"',
                "regexes = [",
                "  '''example-token-here''',",
                "]",
            ]
        )
        + "\n",
    )
    return tmp_path


def test_builtin_scan_detects_dummy_secret_in_receipt(tmp_path: Path) -> None:
    module = load_module("published_artifact_secret_scan_builtin", "scripts/published_artifact_secret_scan.py")
    repo_root = make_repo(tmp_path)
    write(
        repo_root / "receipts" / "live-applies" / "2026-03-24-test.json",
        json.dumps({"summary": "contains secret", "token": "TESTSECRET_DUMMYTOKEN12345678901234567890"}, indent=2)
        + "\n",
    )

    result = module.scan_published_artifacts(
        repo_root,
        config_path=repo_root / ".gitleaks.toml",
        gitleaks_binary="definitely-missing-gitleaks",
    )

    assert result.mode == "builtin"
    assert len(result.findings) == 1
    assert result.findings[0].path == "receipts/live-applies/2026-03-24-test.json"


def test_builtin_scan_honors_allowlisted_placeholder(tmp_path: Path) -> None:
    module = load_module("published_artifact_secret_scan_allowlist", "scripts/published_artifact_secret_scan.py")
    repo_root = make_repo(tmp_path)
    write(
        repo_root / "receipts" / "live-applies" / "2026-03-24-placeholder.json",
        json.dumps({"summary": "placeholder", "token": "example-token-here"}, indent=2) + "\n",
    )

    result = module.scan_published_artifacts(
        repo_root,
        config_path=repo_root / ".gitleaks.toml",
        gitleaks_binary="definitely-missing-gitleaks",
    )

    assert result.mode == "builtin"
    assert result.findings == []


def test_gitleaks_mode_detects_dummy_secret(tmp_path: Path) -> None:
    module = load_module("published_artifact_secret_scan_gitleaks", "scripts/published_artifact_secret_scan.py")
    repo_root = make_repo(tmp_path)
    write(
        repo_root / "build" / "search-index" / "documents.json",
        json.dumps({"documents": [{"body": "TESTSECRET_DUMMYTOKEN12345678901234567890"}]}, indent=2) + "\n",
    )
    fake_gitleaks = tmp_path / "gitleaks"
    fake_gitleaks.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import pathlib",
                "import sys",
                "",
                "args = sys.argv[1:]",
                "source = pathlib.Path(args[args.index('--source') + 1])",
                "report_path = pathlib.Path(args[args.index('--report-path') + 1])",
                "findings = []",
                "for path in source.rglob('*'):",
                "    if not path.is_file():",
                "        continue",
                "    text = path.read_text(encoding='utf-8')",
                "    if 'TESTSECRET_' in text:",
                "        findings.append({",
                "            'RuleID': 'openbao-token',",
                "            'Description': 'OpenBao token',",
                "            'File': str(path),",
                "            'StartLine': 1,",
                "        })",
                "report_path.write_text(json.dumps(findings), encoding='utf-8')",
                "raise SystemExit(1 if findings else 0)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_gitleaks.chmod(0o755)

    result = module.scan_published_artifacts(
        repo_root,
        config_path=repo_root / ".gitleaks.toml",
        paths=["build/search-index"],
        gitleaks_binary=str(fake_gitleaks),
        enforce_gitleaks=True,
    )

    assert result.mode == "gitleaks"
    assert len(result.findings) == 1
    assert result.findings[0].path == "build/search-index/documents.json"


def test_makefile_runs_published_artifact_secret_scan_via_uv_python() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert (
        "search-index-rebuild:\n"
        "\tpython3 $(REPO_ROOT)/config/windmill/scripts/rebuild-search-index.py --repo-path $(REPO_ROOT)\n"
        "\tuv run python $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT) --path build/search-index\n"
    ) in makefile
    assert (
        "generate-changelog-portal:\n"
        "\tuv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_changelog_portal.py --write\n"
        "\tuv run python $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT) --path build/changelog-portal\n"
    ) in makefile
    assert "scan-published-artifacts:\n\tuv run python $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT)\n" in makefile
