"""Tier-0 vault standby courier (config/0infer/tier0-vault-standby/ct108-courier/vault-standby-send), run against a stub ssh.

The courier only runs on the Builder (CT108). Here its host paths point into tmp_path and `ssh` is a stub on PATH that tells the
two hops apart (the destination is the one with `-p 2240`), so the pinned ssh options, the order of the pushes, the exit code and the
textfile metric are exercised without a network.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

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
    printf '%s\n' "$*" >> "$S/src_calls"
    [ -n "${SRC_FAIL:-}" ] && exit 1
    printf 'gz-bytes-of-%s\n' "$(echo "$*" | grep -oE '/[^ ]*\.db' | head -1)"
    exit 0 ;;
esac
"""


def _run(
    tmp_path: Path, fail_label: str = "", src_fail: bool = False, with_textfile: bool = True
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    state, bin_dir, textfile = tmp_path / "state", tmp_path / "bin", tmp_path / "textfile"
    state.mkdir()
    bin_dir.mkdir()
    if with_textfile:
        textfile.mkdir()
    (bin_dir / "ssh").write_text(SSH, encoding="utf-8")
    (bin_dir / "ssh").chmod(0o755)
    script = (COURIER / "vault-standby-send").read_text(encoding="utf-8")
    for host_path in (KEY, KNOWN_HOSTS, TEXTFILE):
        assert host_path in script, host_path
    script = script.replace(KEY, str(tmp_path / "key")).replace(KNOWN_HOSTS, str(tmp_path / "known_hosts")).replace(TEXTFILE, str(textfile))
    path = tmp_path / "send.sh"
    path.write_text(script, encoding="utf-8")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_STATE": str(state), "FAIL_LABEL": fail_label}
    if src_fail:
        env["SRC_FAIL"] = "1"
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
    assert "go-fleet-secrets_secrets-data/_data/secrets.db" in src[0] and "go_apikey_service/data/keys.db" in src[1]
    assert all(".backup" in call and "chmod 600" in call and "rm -f" in call for call in src)
    assert (state / "dest.0").read_text(encoding="utf-8").startswith("gz-bytes-of-") and "secrets.db" in (state / "dest.0").read_text(encoding="utf-8")
    assert "keys.db" in (state / "dest.1").read_text(encoding="utf-8")
    metrics = (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")
    assert "vault_standby_sync_last_success 1" in metrics and "vault_standby_sync_last_success_timestamp_seconds" in metrics
    assert sorted(p.name for p in textfile.iterdir()) == ["vault_standby_sync.prom"]


def test_a_refused_push_exits_1_still_tries_the_other_and_publishes_the_failure(tmp_path: Path) -> None:
    result, state, textfile = _run(tmp_path, fail_label="secrets")
    assert result.returncode == 1
    assert "push secrets FAILED" in result.stderr and "push keystore FAILED" not in result.stderr
    assert len(_lines(state, "dest_calls")) == 2  # keystore was still attempted
    metrics = (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")
    assert "vault_standby_sync_last_success 0" in metrics and "vault_standby_sync_last_success_timestamp_seconds" not in metrics
    assert sorted(p.name for p in textfile.iterdir()) == ["vault_standby_sync.prom"]


def test_a_failed_snapshot_on_the_dockerhost_fails_the_run(tmp_path: Path) -> None:
    result, _, textfile = _run(tmp_path, src_fail=True)
    assert result.returncode == 1
    assert "push secrets FAILED" in result.stderr and "push keystore FAILED" in result.stderr
    assert "vault_standby_sync_last_success 0" in (textfile / "vault_standby_sync.prom").read_text(encoding="utf-8")


def test_without_the_textfile_directory_the_metric_is_skipped_and_nothing_is_created(tmp_path: Path) -> None:
    result, _, textfile = _run(tmp_path, with_textfile=False)
    assert result.returncode == 0, result.stderr
    assert not textfile.exists()


def test_units_script_syntax_and_no_key_material() -> None:
    subprocess.run(["bash", "-n", str(COURIER / "vault-standby-send")], check=True)
    service = (COURIER / "vault-standby-send.service").read_text(encoding="utf-8")
    timer = (COURIER / "vault-standby-send.timer").read_text(encoding="utf-8")
    assert "Type=oneshot" in service and "TimeoutStartSec=300" in service
    assert "ExecStart=/usr/bin/flock -n /run/lock/vault-standby-send.lock /usr/local/sbin/vault-standby-send" in service
    assert "OnUnitActiveSec=120s" in timer and "WantedBy=timers.target" in timer
    for name in ("vault-standby-send", "vault-standby-send.service", "vault-standby-send.timer"):
        assert "PRIVATE KEY" not in (COURIER / name).read_text(encoding="utf-8")
    assert not (COURIER / "tier0_sync").exists() and not (COURIER / "known_hosts_tier0").exists()
