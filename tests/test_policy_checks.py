from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fake_tool(path: Path, record_path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import pathlib",
                "import sys",
                "",
                f"record_path = pathlib.Path({record_path.as_posix()!r})",
                "records = json.loads(record_path.read_text()) if record_path.exists() else []",
                "records.append(sys.argv[1:])",
                "record_path.write_text(json.dumps(records))",
                "raise SystemExit(0)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def make_fake_tool_payload(name: str) -> bytes:
    return (
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                f"print('{name} ready')",
                "raise SystemExit(0)",
            ]
        )
        + "\n"
    ).encode("utf-8")


def test_build_repository_context_includes_policy_surfaces() -> None:
    module = load_module("policy_checks_module", "scripts/policy_checks.py")
    context = module.build_repository_context(REPO_ROOT)

    assert "build_server_config" in context
    assert "command_catalog" in context
    assert "workflow_catalog" in context
    assert "service_catalog" in context
    assert "validation_gate" in context
    assert "check_runner_manifest" in context
    assert "validation_runner_contracts" in context
    assert "promote-to-production" in context["command_catalog"]["commands"]


def test_validate_repository_policies_runs_opa_and_conftest(tmp_path: Path, monkeypatch) -> None:
    module = load_module("policy_checks_module_exec", "scripts/policy_checks.py")
    toolchain_module = load_module("policy_toolchain_module_exec", "platform/policy/toolchain.py")

    fake_opa = tmp_path / "opa"
    fake_conftest = tmp_path / "conftest"
    record_path = tmp_path / "records.json"
    write_fake_tool(fake_opa, record_path)
    write_fake_tool(fake_conftest, record_path)

    toolchain = toolchain_module.PolicyToolchain(
        install_root=tmp_path,
        opa=toolchain_module.ToolBinary(name="opa", version="test", path=fake_opa),
        conftest=toolchain_module.ToolBinary(name="conftest", version="test", path=fake_conftest),
    )

    module.validate_repository_policies(REPO_ROOT, toolchain=toolchain)

    records = json.loads(record_path.read_text())
    assert any(entry[0] == "test" for entry in records)
    assert any(entry[0] == "test" and "--policy" in entry for entry in records)


def test_run_decodes_non_utf8_subprocess_output(monkeypatch) -> None:
    module = load_module("policy_checks_module_decode", "scripts/policy_checks.py")

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=b"stdout ok",
            stderr=b"stderr byte \xa3",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    try:
        module._run(["fake-tool"], cwd=REPO_ROOT)
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("_run should raise when the subprocess fails")

    assert "stdout ok" in message
    assert "stderr byte" in message


def test_managed_tool_path_is_platform_scoped() -> None:
    module = load_module("policy_toolchain_module_paths", "platform/policy/toolchain.py")

    install_root = REPO_ROOT / ".local" / "policy-toolchain"
    path = module._managed_tool_path(
        install_root,
        "opa",
        module.OPA_VERSION,
        system="linux",
        machine="amd64",
    )

    assert path == install_root / "opa" / module.OPA_VERSION / "linux-amd64" / "opa"


def test_ensure_policy_toolchain_replaces_unusable_platform_binaries(
    tmp_path: Path, monkeypatch
) -> None:
    toolchain_module = load_module("policy_toolchain_module_refresh", "platform/policy/toolchain.py")
    install_root = tmp_path / "toolchain"
    stale_opa = toolchain_module._managed_tool_path(
        install_root,
        "opa",
        toolchain_module.OPA_VERSION,
        system="darwin",
        machine="arm64",
    )
    stale_conftest = toolchain_module._managed_tool_path(
        install_root,
        "conftest",
        toolchain_module.CONFTEST_VERSION,
        system="darwin",
        machine="arm64",
    )

    stale_opa.parent.mkdir(parents=True, exist_ok=True)
    stale_conftest.parent.mkdir(parents=True, exist_ok=True)
    for path in (stale_opa, stale_conftest):
        path.write_bytes(b"\x7fELF stale linux binary")
        path.chmod(0o755)

    monkeypatch.setenv("LV3_POLICY_TEST_PLATFORM", "darwin/arm64")

    downloads = {
        f"{toolchain_module.OPA_RELEASE_BASE}/{toolchain_module._opa_asset_name('darwin', 'arm64')}": make_fake_tool_payload(
            "opa"
        ),
        f"{toolchain_module.CONFTEST_RELEASE_BASE}/{toolchain_module._conftest_asset_name('darwin', 'arm64')}": b"fake conftest archive",
    }

    def fake_download_bytes(url: str) -> bytes:
        return downloads[url]

    def fake_opa_expected_sha(asset_name: str) -> str:
        return toolchain_module._sha256(downloads[f"{toolchain_module.OPA_RELEASE_BASE}/{asset_name}"])

    def fake_conftest_expected_sha(asset_name: str) -> str:
        return toolchain_module._sha256(downloads[f"{toolchain_module.CONFTEST_RELEASE_BASE}/{asset_name}"])

    def fake_extract_tar_binary(payload: bytes, member_name: str) -> bytes:
        assert member_name == "conftest"
        return make_fake_tool_payload("conftest")

    monkeypatch.setattr(toolchain_module, "_download_bytes", fake_download_bytes)
    monkeypatch.setattr(toolchain_module, "_opa_expected_sha256", fake_opa_expected_sha)
    monkeypatch.setattr(toolchain_module, "_conftest_expected_sha256", fake_conftest_expected_sha)
    monkeypatch.setattr(toolchain_module, "_extract_tar_binary", fake_extract_tar_binary)

    toolchain = toolchain_module.ensure_policy_toolchain(install_root=install_root)

    assert "ready" in subprocess.check_output([str(toolchain.opa.path), "version"], text=True)
    assert "ready" in subprocess.check_output([str(toolchain.conftest.path), "--version"], text=True)
