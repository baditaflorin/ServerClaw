from __future__ import annotations

import hashlib
import io
import os
import shutil
import stat
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Final


REPO_ROOT = Path(__file__).resolve().parents[2]
OPA_VERSION: Final[str] = "1.12.1"
CONFTEST_VERSION: Final[str] = "0.67.1"
DEFAULT_INSTALL_ROOT = REPO_ROOT / ".local" / "policy-toolchain"
OPA_RELEASE_BASE = f"https://github.com/open-policy-agent/opa/releases/download/v{OPA_VERSION}"
CONFTEST_RELEASE_BASE = (
    f"https://github.com/open-policy-agent/conftest/releases/download/v{CONFTEST_VERSION}"
)


@dataclass(frozen=True)
class ToolBinary:
    name: str
    version: str
    path: Path


@dataclass(frozen=True)
class PolicyToolchain:
    install_root: Path
    opa: ToolBinary
    conftest: ToolBinary


def _request(url: str):
    return urllib.request.Request(
        url,
        headers={"User-Agent": "lv3-policy-toolchain/1.0"},
    )


def _download_bytes(url: str) -> bytes:
    with urllib.request.urlopen(_request(url), timeout=120) as response:
        return response.read()


def _download_text(url: str) -> str:
    return _download_bytes(url).decode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _platform_key() -> tuple[str, str]:
    if sys_platform := os.environ.get("LV3_POLICY_TEST_PLATFORM"):
        system, machine = sys_platform.split("/", 1)
        return system, machine
    if os.name == "nt":
        raise RuntimeError("ADR 0230 policy tool bootstrap does not support Windows")

    raw_system = "darwin" if os.uname().sysname.lower() == "darwin" else "linux"
    raw_machine = os.uname().machine.lower()
    machine_aliases = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    resolved_machine = machine_aliases.get(raw_machine)
    if resolved_machine is None:
        raise RuntimeError(f"unsupported machine architecture for ADR 0230 policy tools: {raw_machine}")
    return raw_system, resolved_machine


def _opa_asset_name(system: str, machine: str) -> str:
    asset_system = "darwin" if system == "darwin" else "linux"
    return f"opa_{asset_system}_{machine}"


def _conftest_asset_name(system: str, machine: str) -> str:
    if system == "darwin":
        arch = "arm64" if machine == "arm64" else "x86_64"
        return f"conftest_{CONFTEST_VERSION}_Darwin_{arch}.tar.gz"
    if system == "linux":
        arch = "arm64" if machine == "arm64" else "x86_64"
        return f"conftest_{CONFTEST_VERSION}_Linux_{arch}.tar.gz"
    raise RuntimeError(f"unsupported operating system for ADR 0230 policy tools: {system}")


def _validate_override(path_value: str, name: str) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"{name} override points to a missing file: {path}")
    if not os.access(path, os.X_OK):
        raise RuntimeError(f"{name} override is not executable: {path}")
    return path


def _install_binary(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        handle.write(payload)
        tmp_path = Path(handle.name)
    tmp_path.chmod(tmp_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    tmp_path.replace(target)


def _extract_tar_binary(payload: bytes, member_name: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        member = archive.getmember(member_name)
        extracted = archive.extractfile(member)
        if extracted is None:
            raise RuntimeError(f"failed to extract {member_name} from Conftest archive")
        return extracted.read()


def _opa_expected_sha256(asset_name: str) -> str:
    payload = _download_text(f"{OPA_RELEASE_BASE}/{asset_name}.sha256").strip()
    return payload.split()[0]


def _conftest_expected_sha256(asset_name: str) -> str:
    checksums = _download_text(f"{CONFTEST_RELEASE_BASE}/checksums.txt").splitlines()
    for line in checksums:
        parts = line.split()
        if len(parts) == 2 and parts[1] == asset_name:
            return parts[0]
    raise RuntimeError(f"missing checksum entry for {asset_name} in Conftest release metadata")


def _platform_dirname(system: str, machine: str) -> str:
    return f"{system}-{machine}"


def _managed_tool_path(
    install_root: Path,
    tool_name: str,
    version: str,
    *,
    system: str,
    machine: str,
) -> Path:
    return install_root / tool_name / version / _platform_dirname(system, machine) / tool_name


def _ensure_opa(install_root: Path) -> ToolBinary:
    if override := os.environ.get("LV3_OPA_BIN"):
        return ToolBinary(name="opa", version=OPA_VERSION, path=_validate_override(override, "LV3_OPA_BIN"))

    system, machine = _platform_key()
    asset_name = _opa_asset_name(system, machine)
    target = _managed_tool_path(
        install_root,
        "opa",
        OPA_VERSION,
        system=system,
        machine=machine,
    )
    if not target.is_file():
        payload = _download_bytes(f"{OPA_RELEASE_BASE}/{asset_name}")
        expected_sha = _opa_expected_sha256(asset_name)
        observed_sha = _sha256(payload)
        if observed_sha != expected_sha:
            raise RuntimeError(
                f"OPA checksum mismatch for {asset_name}: expected {expected_sha}, observed {observed_sha}"
            )
        _install_binary(target, payload)
    return ToolBinary(name="opa", version=OPA_VERSION, path=target)


def _ensure_conftest(install_root: Path) -> ToolBinary:
    if override := os.environ.get("LV3_CONFTEST_BIN"):
        return ToolBinary(
            name="conftest",
            version=CONFTEST_VERSION,
            path=_validate_override(override, "LV3_CONFTEST_BIN"),
        )

    system, machine = _platform_key()
    asset_name = _conftest_asset_name(system, machine)
    target = _managed_tool_path(
        install_root,
        "conftest",
        CONFTEST_VERSION,
        system=system,
        machine=machine,
    )
    if not target.is_file():
        payload = _download_bytes(f"{CONFTEST_RELEASE_BASE}/{asset_name}")
        expected_sha = _conftest_expected_sha256(asset_name)
        observed_sha = _sha256(payload)
        if observed_sha != expected_sha:
            raise RuntimeError(
                f"Conftest checksum mismatch for {asset_name}: expected {expected_sha}, observed {observed_sha}"
            )
        binary = _extract_tar_binary(payload, "conftest")
        _install_binary(target, binary)
    return ToolBinary(name="conftest", version=CONFTEST_VERSION, path=target)


def default_install_root(repo_root: Path | None = None) -> Path:
    if override := os.environ.get("LV3_POLICY_TOOLCHAIN_ROOT"):
        return Path(override).expanduser().resolve()
    base = repo_root.resolve() if repo_root is not None else REPO_ROOT
    return (base / ".local" / "policy-toolchain").resolve()


def ensure_policy_toolchain(
    *,
    repo_root: Path | None = None,
    install_root: Path | None = None,
) -> PolicyToolchain:
    effective_root = (install_root or default_install_root(repo_root)).resolve()
    effective_root.mkdir(parents=True, exist_ok=True)
    opa = _ensure_opa(effective_root)
    conftest = _ensure_conftest(effective_root)
    return PolicyToolchain(install_root=effective_root, opa=opa, conftest=conftest)


def clear_policy_toolchain(install_root: Path | None = None) -> None:
    root = (install_root or default_install_root()).resolve()
    if root.exists():
        shutil.rmtree(root)
