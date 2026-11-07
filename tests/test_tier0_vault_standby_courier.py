"""Tier-0 vault standby courier (config/0infer/tier0-vault-standby/ct108-courier/vault-standby-send), run against a stub ssh.

The courier only runs on the Builder (CT108). Here its host paths point into tmp_path and `ssh` is a stub on PATH that tells the
two hops apart (the destination is the one with `-p 2240`), so the pinned ssh options, the order of the pushes, the exit code and the
textfile metric are exercised without a network.
"""

from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COURIER = REPO_ROOT / "config" / "0infer" / "tier0-vault-standby" / "ct108-courier"
KEY, KNOWN_HOSTS, TEXTFILE = "/root/.ssh/tier0_sync", "/root/.ssh/known_hosts_tier0", "/var/lib/prometheus-node-exporter/textfile"

# Destination hop: swallow stdin, record the call, refuse `put $FAIL_LABEL`. Source hop: record the call, optionally fail,
# otherwise emit bytes that name the database path found in the remote command.
SSH = r"""#!/bin/bash
S="$FAKE_STATE"
case " $* " in
  *" -p 2240 "*)
    n=$(( $(ls "$S"/dest.* 2>/dev/null | wc -l) ))
    cat > "$S/dest.$n"
    printf '%s\n' "$*" >> "$S/dest_calls"
    if [ -n "${FAIL_LABEL:-}" ] && [ "${*: -1}" = "put $FAIL_LABEL" ]; then echo "stub: refused" >&2; exit 1; fi
    exit 0 ;;
  *)
    n=$(( $(ls "$S"/src_script.* 2>/dev/null | wc -l) ))
    cat > "$S/src_script.$n"
    printf '%s\n' "$*" >> "$S/src_calls"
    [ -n "${SRC_FAIL:-}" ] && exit 1
    case "${*: -1}" in
      *"-- 'secrets'") printf 'VAULT_STANDBY_SOURCE_BYTES=%s:469762048\n' "${SECRETS_BYTES:-120000000}" >&2; [ -z "${OVER_LIMIT:-}" ] || exit 1; printf 'gz-bytes-of-secrets.db\n' ;;
      *"-- 'keystore'") printf 'VAULT_STANDBY_SOURCE_BYTES=%s:469762048\n' "${KEYSTORE_BYTES:-219000000}" >&2; printf 'gz-bytes-of-keys.db\n' ;;
      *) exit 1 ;;
    esac
    [ -z "${DUPLICATE_SIZE:-}" ] || echo 'VAULT_STANDBY_SOURCE_BYTES=42:469762048' >&2
    exit 0 ;;
esac
"""


def _run(
    tmp_path: Path, fail_label: str = "", src_fail: bool = False, with_textfile: bool = True,
    with_runtime: bool = True, duplicate_size: bool = False, over_limit: bool = False
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    state, bin_dir, textfile, runtime = (tmp_path / name for name in ("state", "bin", "textfile", "runtime"))
    state.mkdir()
    bin_dir.mkdir()
    if with_textfile:
        textfile.mkdir()
    if with_runtime:
        runtime.mkdir(mode=0o700)
    (bin_dir / "ssh").write_text(SSH, encoding="utf-8")
    (bin_dir / "ssh").chmod(0o755)
    script = (COURIER / "vault-standby-send").read_text(encoding="utf-8")
    for host_path in (KEY, KNOWN_HOSTS, TEXTFILE):
        assert host_path in script, host_path
    script = script.replace(KEY, str(tmp_path / "key")).replace(KNOWN_HOSTS, str(tmp_path / "known_hosts")).replace(TEXTFILE, str(textfile))
    script = script.replace("R=/run/vault-standby-send", f"R={runtime}")
    path = tmp_path / "send.sh"
    path.write_text(script, encoding="utf-8")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_STATE": str(state), "FAIL_LABEL": fail_label}
    if src_fail:
        env["SRC_FAIL"] = "1"
    if duplicate_size:
        env["DUPLICATE_SIZE"] = "1"
    if over_limit:
        env["OVER_LIMIT"] = "1"
        env["SECRETS_BYTES"] = str(448 * 1024 * 1024 + 1)
    result = subprocess.run(["bash", str(path)], capture_output=True, text=True, env=env, timeout=60, check=False)
    return result, state, textfile


def _lines(state: Path, name: str) -> list[str]:
    return (state / name).read_text(encoding="utf-8").splitlines() if (state / name).exists() else []


def test_both_databases_are_pushed_in_order_with_the_pinned_options(tmp_path: Path) -> None:
    result, state, textfile = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    dest = _lines(state, "dest_calls")
    assert [call.rsplit(" ", 2)[-2:] for call in dest] == [["put", "secrets"], ["put", "keystore"]]
    for call in dest:
        for option in ("BatchMode=yes", "StrictHostKeyChecking=yes", "UserKnownHostsFile=" + str(tmp_path / "known_hosts"), "-p 2240", "-i " + str(tmp_path / "key"), "vsync@"):
            assert option in call, option
        assert "ProxyCommand=nc -X connect -x 127.0.0.1:1056 %h %p" in call
    src = _lines(state, "src_calls")
    assert len(src) == 2 and all("ubuntu_vm@" in call for call in src)
    assert src[0].endswith("-- 'secrets'") and src[1].endswith("-- 'keystore'")
    for call in src:
        for option in (
            "sudo -n /usr/bin/systemd-run --quiet --pipe --wait --collect",
            "TemporaryFileSystem=/tmp:rw,nodev,nosuid,noexec,noswap,size=512M,mode=0700",
            "MemoryMax=768M", "MemorySwapMax=0", "LimitCORE=0", "RuntimeMaxSec=140s",
            "ProtectSystem=strict", "PrivateNetwork=yes", "NoNewPrivileges=yes", "TasksMax=16",
        ):
            assert option in call
    source = (state / "src_script.0").read_text(encoding="utf-8")
    assert source == (state / "src_script.1").read_text(encoding="utf-8")
    assert "go-fleet-secrets_secrets-data/_data/secrets.db" in source and "go_apikey_service/data/keys.db" in source
    assert (state / "dest.0").read_text(encoding="utf-8").startswith("gz-bytes-of-") and "secrets.db" in (state / "dest.0").read_text(encoding="utf-8")
    assert "keys.db" in (state / "dest.1").read_text(encoding="utf-8")
    metrics = (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")
    assert "vault_standby_sync_last_success 1" in metrics and "vault_standby_sync_last_success_timestamp_seconds" in metrics
    for name, size in (("secrets", 120000000), ("keystore", 219000000)):
        assert f'vault_standby_source_database_size_bytes{{database="{name}"}} {size}' in metrics
        assert f'vault_standby_source_database_limit_bytes{{database="{name}"}} 469762048' in metrics
    assert list((tmp_path / "runtime").iterdir()) == []
    assert sorted(p.name for p in textfile.iterdir()) == ["vault_standby_sync.prom"]


def test_a_refused_push_exits_1_still_tries_the_other_and_publishes_the_failure(tmp_path: Path) -> None:
    result, state, textfile = _run(tmp_path, fail_label="secrets")
    assert result.returncode == 1
    assert "push secrets FAILED" in result.stderr and "push keystore FAILED" not in result.stderr
    assert len(_lines(state, "dest_calls")) == 2  # keystore was still attempted
    metrics = (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")
    assert "vault_standby_sync_last_success 0" in metrics and "vault_standby_sync_last_success_timestamp_seconds" not in metrics
    assert 'vault_standby_source_database_size_bytes{database="secrets"} 120000000' in metrics
    assert 'vault_standby_source_database_size_bytes{database="keystore"} 219000000' in metrics
    assert sorted(p.name for p in textfile.iterdir()) == ["vault_standby_sync.prom"]


def test_a_failed_snapshot_on_the_dockerhost_fails_the_run(tmp_path: Path) -> None:
    result, _, textfile = _run(tmp_path, src_fail=True)
    assert result.returncode == 1
    assert "push secrets FAILED" in result.stderr and "push keystore FAILED" in result.stderr
    assert "vault_standby_sync_last_success 0" in (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")
    assert 'vault_standby_source_database_size_bytes{database=' not in (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")


def test_unavailable_telemetry_does_not_prevent_backup(tmp_path: Path) -> None:
    result, state, textfile = _run(tmp_path, with_runtime=False)
    assert result.returncode == 0 and len(_lines(state, "dest_calls")) == 2
    assert "source-size telemetry unavailable" in result.stderr
    metrics = (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")
    assert "vault_standby_sync_last_success 1" in metrics
    assert 'vault_standby_source_database_size_bytes{database=' not in metrics


def test_duplicate_source_telemetry_is_rejected_without_breaking_backup(tmp_path: Path) -> None:
    result, _, textfile = _run(tmp_path, duplicate_size=True)
    assert result.returncode == 0 and "duplicate standby source-size telemetry" in result.stderr
    assert 'vault_standby_source_database_size_bytes{database=' not in (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")


def test_source_size_stays_visible_when_the_source_rejects_an_oversized_database(tmp_path: Path) -> None:
    result, state, textfile = _run(tmp_path, over_limit=True)
    assert result.returncode == 1 and len(_lines(state, "dest_calls")) == 2
    metrics = (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")
    assert 'vault_standby_source_database_size_bytes{database="secrets"} 469762049' in metrics
    assert 'vault_standby_source_database_limit_bytes{database="secrets"} 469762048' in metrics
    assert "vault_standby_sync_last_success 0" in metrics


def test_without_the_textfile_directory_the_metric_is_skipped_and_nothing_is_created(tmp_path: Path) -> None:
    result, _, textfile = _run(tmp_path, with_textfile=False)
    assert result.returncode == 0, result.stderr
    assert not textfile.exists()


def _remote_script() -> str:
    lines = (COURIER / "vault-standby-send").read_text(encoding="utf-8").splitlines()
    first = next(i for i, line in enumerate(lines) if "<<'REMOTE'" in line)
    return "\n".join(lines[first + 1 : lines.index("REMOTE", first)]) + "\n"


def _tool(directory: Path, name: str, source: str) -> None:
    path = directory / name
    path.write_text("#!/bin/bash\n" + source, encoding="utf-8")
    path.chmod(0o755)


def test_remote_snapshot_refuses_an_unverified_filesystem_before_creating_scratch(tmp_path: Path) -> None:
    _tool(tmp_path, "findmnt", "echo 'ext4 rw,nodev,nosuid,noexec'\n")
    for name in ("mktemp", "sqlite3", "gzip"):
        _tool(tmp_path, name, "touch \"$SENTINEL\"\n")
    sentinel = tmp_path / "unexpected"
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "SENTINEL": str(sentinel)}
    result = subprocess.run(["bash", "-s", "--", "secrets"], input=_remote_script(), capture_output=True,
                            text=True, env=env, timeout=5, check=False)
    assert result.returncode == 1 and result.stdout == ""
    assert "bounded no-swap RAM scratch" in result.stderr
    assert not sentinel.exists()


def test_remote_snapshot_stream_restores_and_cleans_its_unique_scratch(tmp_path: Path) -> None:
    if shutil.which("sqlite3") is None or shutil.which("gzip") is None:
        pytest.skip("needs native SQLite and gzip for the backup and restore")
    bin_dir, scratch, cgroup = (tmp_path / name for name in ("bin", "scratch", "cgroup"))
    for path in (bin_dir, scratch, cgroup):
        path.mkdir()
    (cgroup / "memory.max").write_text("805306368\n", encoding="utf-8")
    (cgroup / "memory.swap.max").write_text("0\n", encoding="utf-8")
    cgroup_file = tmp_path / "self-cgroup"
    cgroup_file.write_text("0::/cgroup\n", encoding="utf-8")
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemAvailable: 4194304 kB\n", encoding="utf-8")
    _tool(bin_dir, "findmnt", "echo 'tmpfs rw,nodev,nosuid,noexec,noswap'\n")
    _tool(bin_dir, "stat", "if [[ $1 == -f ]]; then echo '4096 131072'; elif [[ $2 == %s ]]; then echo \"$DB_BYTES\"; else echo 0:0:700; fi\n")
    source = tmp_path / "fixture.db"
    with sqlite3.connect(source) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE fixture (message TEXT)")
        live.execute("INSERT INTO fixture VALUES ('backup proof')")
        live.commit()
        script = (_remote_script().replace("/tmp", str(scratch))
                  .replace("/proc/self/cgroup", str(cgroup_file)).replace("/sys/fs/cgroup", str(tmp_path))
                  .replace("/proc/meminfo", str(meminfo))
                  .replace("/var/lib/docker/volumes/go-fleet-secrets_secrets-data/_data/secrets.db", str(source)))
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "DB_BYTES": str(source.stat().st_size)}
        result = subprocess.run(["bash", "-s", "--", "secrets"], input=script.encode(), capture_output=True,
                                env=env, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    assert b"VAULT_STANDBY_SOURCE_BYTES=" in result.stderr
    assert list(scratch.iterdir()) == []
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(result.stdout))
    with sqlite3.connect(restored) as copy:
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert copy.execute("SELECT message FROM fixture").fetchall() == [("backup proof",)]

    for available, db_bytes, error in (
        (2097151, source.stat().st_size, b"insufficient memory headroom"),
        (4194304, 448 * 1024 * 1024 + 1, b"exceeds scratch budget"),
    ):
        meminfo.write_text(f"MemAvailable: {available} kB\n", encoding="utf-8")
        refused = subprocess.run(["bash", "-s", "--", "secrets"], input=script.encode(), capture_output=True,
                                 env={**env, "DB_BYTES": str(db_bytes)}, timeout=5, check=False)
        assert refused.returncode == 1 and refused.stdout == b"" and error in refused.stderr
        assert f"VAULT_STANDBY_SOURCE_BYTES={db_bytes}:469762048".encode() in refused.stderr
        assert list(scratch.iterdir()) == []


def test_units_script_syntax_and_no_key_material() -> None:
    subprocess.run(["bash", "-n", str(COURIER / "vault-standby-send")], check=True)
    service = (COURIER / "vault-standby-send.service").read_text(encoding="utf-8")
    timer = (COURIER / "vault-standby-send.timer").read_text(encoding="utf-8")
    assert "Type=oneshot" in service and "TimeoutStartSec=300" in service
    assert "RuntimeDirectory=vault-standby-send" in service and "RuntimeDirectoryMode=0700" in service
    assert "ExecStart=/usr/bin/flock -n /run/lock/vault-standby-send.lock /usr/local/sbin/vault-standby-send" in service
    assert "OnUnitActiveSec=120s" in timer and "WantedBy=timers.target" in timer
    for name in ("vault-standby-send", "vault-standby-send.service", "vault-standby-send.timer"):
        assert "PRIVATE KEY" not in (COURIER / name).read_text(encoding="utf-8")
    assert not (COURIER / "tier0_sync").exists() and not (COURIER / "known_hosts_tier0").exists()
