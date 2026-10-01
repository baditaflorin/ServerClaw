from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from seed_dify_runtime_secrets import SeedError, main, seed_runtime_secrets  # noqa: E402


SECRET_ENV = {
    "INIT_PASSWORD": "test-init-value",
    "SECRET_KEY": "test-secret-key-value",
    "REDIS_PASSWORD": "test-redis-value",
    "QDRANT_API_KEY": "test-qdrant-value",
    "SANDBOX_API_KEY": "test-sandbox-value",
    "PLUGIN_DAEMON_KEY": "test-plugin-daemon-value",
    "PLUGIN_DIFY_INNER_API_KEY": "test-plugin-inner-value",
}
TOOL_API_KEY = "test-gateway-tool-value"


def write_runtime_env(path: Path, *, overrides: dict[str, str] | None = None) -> dict[str, str]:
    values = {
        **SECRET_ENV,
        "SERVER_KEY": SECRET_ENV["PLUGIN_DAEMON_KEY"],
        "DIFY_INNER_API_KEY": SECRET_ENV["PLUGIN_DIFY_INNER_API_KEY"],
        "INNER_API_KEY_FOR_PLUGIN": SECRET_ENV["PLUGIN_DIFY_INNER_API_KEY"],
    }
    values.update(overrides or {})
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return values


def write_tool_api_key(secret_dir: Path) -> Path:
    path = secret_dir / "tools-api-key.txt"
    path.write_text(TOOL_API_KEY + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def test_seeds_missing_secret_files_as_private_files_without_printing_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = tmp_path / "runtime.env"
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    write_runtime_env(env_file)
    tool_api_key = write_tool_api_key(secret_dir)

    assert main(["--env-file", str(env_file), "--secret-dir", str(secret_dir)]) == 0
    first_output = capsys.readouterr().out
    assert "created=7 existing=1" in first_output
    assert all(value not in first_output for value in (*SECRET_ENV.values(), TOOL_API_KEY))

    for env_key, filename in (
        ("INIT_PASSWORD", "init-password.txt"),
        ("SECRET_KEY", "secret-key.txt"),
        ("REDIS_PASSWORD", "redis-password.txt"),
        ("QDRANT_API_KEY", "qdrant-api-key.txt"),
        ("SANDBOX_API_KEY", "sandbox-api-key.txt"),
        ("PLUGIN_DAEMON_KEY", "plugin-daemon-key.txt"),
        ("PLUGIN_DIFY_INNER_API_KEY", "plugin-inner-api-key.txt"),
    ):
        target = secret_dir / filename
        assert target.read_text(encoding="utf-8").strip() == SECRET_ENV[env_key]
        assert target.stat().st_mode & 0o777 == 0o600
    assert tool_api_key.read_text(encoding="utf-8").strip() == TOOL_API_KEY

    assert seed_runtime_secrets(env_file, secret_dir) == (0, 8, True)


def test_existing_matching_secrets_are_preserved_and_drift_fails_closed(tmp_path: Path) -> None:
    env_file = tmp_path / "runtime.env"
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    write_runtime_env(env_file)
    write_tool_api_key(secret_dir)
    seed_runtime_secrets(env_file, secret_dir)

    secret_path = secret_dir / "redis-password.txt"
    before = secret_path.read_bytes()
    secret_path.write_bytes(b"different-test-value\n")

    with pytest.raises(SeedError, match="existing secret does not match runtime env: redis-password.txt"):
        seed_runtime_secrets(env_file, secret_dir)
    assert secret_path.read_bytes() == b"different-test-value\n"
    assert before != secret_path.read_bytes()


def test_absent_runtime_env_is_a_noop_for_first_install(tmp_path: Path) -> None:
    secret_dir = tmp_path / "secrets"
    assert seed_runtime_secrets(tmp_path / "missing.env", secret_dir) == (0, 0, False)
    assert not secret_dir.exists()


def test_incomplete_or_inconsistent_runtime_env_fails_without_writing_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / "runtime.env"
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    write_runtime_env(env_file, overrides={"SERVER_KEY": "not-the-plugin-key"})

    with pytest.raises(SeedError, match="inconsistent SERVER_KEY"):
        seed_runtime_secrets(env_file, secret_dir)
    assert list(secret_dir.iterdir()) == []

    write_runtime_env(env_file)
    env_file.write_text("INIT_PASSWORD=test-only\n", encoding="utf-8")
    with pytest.raises(SeedError, match="missing required Dify secret entries"):
        seed_runtime_secrets(env_file, secret_dir)
    assert list(secret_dir.iterdir()) == []


def test_empty_existing_secret_fails_instead_of_triggering_secret_regeneration(tmp_path: Path) -> None:
    env_file = tmp_path / "runtime.env"
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    write_runtime_env(env_file)
    write_tool_api_key(secret_dir)
    empty_secret = secret_dir / "secret-key.txt"
    empty_secret.write_bytes(b"")
    empty_secret.chmod(0o600)

    with pytest.raises(SeedError, match="existing secret target is empty: secret-key.txt"):
        seed_runtime_secrets(env_file, secret_dir)
    assert empty_secret.read_bytes() == b""


def test_missing_non_runtime_gateway_key_fails_before_creating_any_runtime_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / "runtime.env"
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    write_runtime_env(env_file)

    with pytest.raises(SeedError, match="runtime env does not carry this secret and host source is missing"):
        seed_runtime_secrets(env_file, secret_dir)
    assert list(secret_dir.iterdir()) == []
