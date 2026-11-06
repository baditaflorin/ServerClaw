"""Tier-0 vault standby promotion drill (config/0infer/tier0-vault-standby/drill.sh), run against stub commands.

The drill only runs on infer-tier0. Here its host paths point into tmp_path and the commands it calls (docker-compose, curl,
sleep, flock) are stubs on PATH, so the cleanup race (stop returns before ps stops listing the containers), the real-promotion
guard and the metrics are exercised without Docker.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STANDBY = REPO_ROOT / "config" / "0infer" / "tier0-vault-standby"
HOST_PATHS = ("/opt/tier0/vault-standby", "/var/lib/prometheus/node-exporter", "/run/vault-standby-drill.lock")

# `up -d <svc>` marks a container running. `stop` arms STOP_LAG: that many later `ps` calls still list the containers
# (STOP_LAG=never: they never stop). `ps --status running -q` prints one id per running container.
DOCKER_COMPOSE = r"""#!/bin/bash
S="$FAKE_STATE"; echo "$*" >> "$S/calls"
case "$1" in
  up) touch "$S/running.${*: -1}" ;;
  stop) echo "${STOP_LAG:-0}" > "$S/lag" ;;
  ps)
    if [ -f "$S/lag" ]; then
      lag=$(cat "$S/lag")
      if [ "$lag" = never ]; then :
      elif [ "$lag" -gt 0 ]; then echo $((lag - 1)) > "$S/lag"
      else rm -f "$S"/running.*; fi
    fi
    for f in "$S"/running.*; do [ -e "$f" ] && echo "id-${f##*.}"; done ;;
esac
exit 0
"""
STUBS = {
    "docker-compose": DOCKER_COMPOSE,
    "curl": '#!/bin/bash\necho \'{"status":"ok"}\'\n',
    "sleep": '#!/bin/bash\necho "$*" >> "$FAKE_STATE/sleeps"\n',
    "flock": "#!/bin/bash\nexit 0\n",
}


def _run(
    tmp_path: Path,
    stop_lag: str = "0",
    records: int = 1240,
    copy_age: int = 60,
    already_running: bool = False,
    previous_records: int | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    standby, textfile, state, bin_dir = (tmp_path / name for name in ("standby", "textfile", "state", "bin"))
    for directory in (textfile, state, bin_dir):
        directory.mkdir()
    for name in ("vault", "keystore"):
        (standby / "data" / name).mkdir(parents=True)
        (standby / "data" / name / ".last_sync").write_text(f"{int(time.time()) - copy_age}\n", encoding="utf-8")
    if previous_records is not None:
        (standby / "data" / ".drill-state").write_text(f"{previous_records}\n", encoding="utf-8")
    (standby / "drill_check.py").write_text(f'print("records={records}")\n', encoding="utf-8")
    for name, body in STUBS.items():
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    (state / "calls").touch()
    (state / "sleeps").touch()
    if already_running:
        (state / "running.keystore").touch()
        (state / "running.vault").touch()

    script = (STANDBY / "drill.sh").read_text(encoding="utf-8")
    for host_path in HOST_PATHS:
        assert host_path in script, host_path
    script = (
        script.replace(HOST_PATHS[0], str(standby))
        .replace(HOST_PATHS[1], str(textfile))
        .replace(HOST_PATHS[2], str(tmp_path / "drill.lock"))
    )
    path = tmp_path / "drill.sh"
    path.write_text(script, encoding="utf-8")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_STATE": str(state), "STOP_LAG": stop_lag}
    result = subprocess.run(["bash", str(path)], capture_output=True, text=True, env=env, timeout=60, check=False)
    return result, state, textfile / "vault_standby_drill.prom"


def _calls(state: Path) -> list[str]:
    return (state / "calls").read_text(encoding="utf-8").splitlines()


def _one_second_sleeps(state: Path) -> int:
    return (state / "sleeps").read_text(encoding="utf-8").splitlines().count("1")


def test_a_clean_drill_passes_without_waiting(tmp_path: Path) -> None:
    result, state, prom = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "vault standby drill: PASS (standby served 1240 records" in result.stdout
    metrics = prom.read_text(encoding="utf-8")
    assert "vault_standby_drill_last_success 1" in metrics and "vault_standby_drill_records 1240" in metrics
    assert "vault_standby_drill_skipped 0" in metrics and "vault_standby_drill_last_success_timestamp_seconds" in metrics
    assert _one_second_sleeps(state) == 0
    assert (tmp_path / "standby" / "data" / ".drill-state").read_text(encoding="utf-8").strip() == "1240"


def test_containers_that_exit_just_after_stop_returns_still_pass(tmp_path: Path) -> None:
    # 2026-10-16 23:15Z: stop returned, ps still listed both containers, they had exited about a second later.
    result, state, prom = _run(tmp_path, stop_lag="3")
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout and "still running" not in result.stdout
    assert "vault_standby_drill_last_success 1" in prom.read_text(encoding="utf-8")
    assert _one_second_sleeps(state) == 3
    calls = _calls(state)
    assert calls.count("stop") == 1
    assert len(calls[calls.index("stop") + 1 :]) == 4  # three polls see them running, the fourth sees none


def test_containers_still_running_after_20_s_fail_the_drill(tmp_path: Path) -> None:
    result, state, prom = _run(tmp_path, stop_lag="never")
    assert "vault standby drill: FAIL" in result.stdout
    assert "standby containers still running after the drill" in result.stdout
    metrics = prom.read_text(encoding="utf-8")
    assert "vault_standby_drill_last_success 0" in metrics
    assert "vault_standby_drill_last_success_timestamp_seconds" not in metrics
    calls = _calls(state)
    assert calls[calls.index("stop") + 1 :] == ["ps --status running -q"] * 20
    assert _one_second_sleeps(state) == 19


def test_a_running_standby_is_a_real_promotion_and_is_never_touched(tmp_path: Path) -> None:
    result, state, prom = _run(tmp_path, already_running=True)
    assert result.returncode == 0, result.stderr
    assert "vault standby drill: SKIPPED (standby is already running" in result.stdout
    assert all(call.startswith("ps ") for call in _calls(state))  # never up, never stop
    assert (state / "running.keystore").exists() and (state / "running.vault").exists()
    assert _one_second_sleeps(state) == 0
    metrics = prom.read_text(encoding="utf-8")
    assert "vault_standby_drill_skipped 1" in metrics and "vault_standby_drill_last_success" not in metrics


def test_a_stale_copy_fails_before_anything_starts(tmp_path: Path) -> None:
    result, state, prom = _run(tmp_path, copy_age=1000)
    assert result.returncode == 1
    assert "copy is" in result.stdout and "old (limit 900s)" in result.stdout
    assert not any(call.startswith("up ") for call in _calls(state))
    assert "vault_standby_drill_last_success 0" in prom.read_text(encoding="utf-8")


def test_a_record_count_drop_of_more_than_15_percent_fails(tmp_path: Path) -> None:
    result, state, prom = _run(tmp_path, previous_records=2000)
    assert result.returncode == 1
    assert "record count dropped from 2000 to 1240" in result.stdout
    assert "vault_standby_drill_last_success 0" in prom.read_text(encoding="utf-8")
    assert "stop" in _calls(state)


def test_the_shell_scripts_parse_and_no_secrets_file_is_committed() -> None:
    for name in ("drill.sh", "promote.sh", "vault-standby-receive"):
        subprocess.run(["bash", "-n", str(STANDBY / name)], check=True)
    assert not (STANDBY / ".env").exists()
    assert 'open("/opt/tier0/vault-standby/.env")' in (STANDBY / "drill_check.py").read_text(encoding="utf-8")
