#!/bin/bash
# The daily host-local configuration check, run on the operator's machine by a macOS LaunchAgent (docs/runbooks/host-local-config.md, "The scheduled check").
#
#   hostconf-scheduled.sh run         fetch main, run `scripts/hostconf.py drift --all` (read-only: every host, every hypervisor's guest list), ship the metrics
#                                     to the monitoring VM as /var/lib/prometheus/node-exporter/fleet_hostconf.prom (alerts: config/prometheus/rules/fleet-hostconf.yml)
#   hostconf-scheduled.sh status      the agent, the last log lines, the age of the file on the monitoring VM
#   hostconf-scheduled.sh install     copy this script to ~/.local/share/hostconf-drift/, write and load the LaunchAgent (daily 12:20 local), make the first checkout
#   hostconf-scheduled.sh uninstall   unload and remove the LaunchAgent and the copy (the log and the checkout stay)
#   hostconf-scheduled.sh plist       print the LaunchAgent
#
# Why here: the operator's machine is the one place with ssh to every host (the builder has no keys to most of them), and why a file on the monitoring VM:
# the alerts then also cover this job dying (HostconfCheckStale: no completed run for 36 hours), which a log on a laptop never could.
# What it never does: apply, adopt or change anything on a host (`drift` is the read-only verb; a test greps this script for the other two), keep a
# credential, or ask a question. The tool and the manifest come from main on every run (a fresh depth-1 sparse checkout of two paths), so a reviewed
# change to either is picked up the next day; this script itself is copied by `install` and changes only when `install` is run again.
#
# Exit status of `run`: 0 when a result reached the monitoring VM (whatever it says about the hosts: findings are alerts, not failures), 1 otherwise.
# Settings for tests and unusual machines: HOSTCONF_REPO_DIR (use this checkout, no git), HOSTCONF_STATE, HOSTCONF_INSTALL_DIR, HOSTCONF_LOG,
# HOSTCONF_PLIST, HOSTCONF_MONITORING_SSH, HOSTCONF_REPO_URL, HOSTCONF_MAX_SECONDS, HOSTCONF_REMOTE_FILE, HOSTCONF_PYTHON.
set -u -o pipefail

LABEL=org.baditaflorin.hostconf-drift
REPO_URL=${HOSTCONF_REPO_URL:-https://github.com/baditaflorin/platform_server.git}
STATE=${HOSTCONF_STATE:-$HOME/.local/state/hostconf-drift}
INSTALL_DIR=${HOSTCONF_INSTALL_DIR:-$HOME/.local/share/hostconf-drift}
LOG=${HOSTCONF_LOG:-$HOME/Library/Logs/hostconf-drift.log}
PLIST=${HOSTCONF_PLIST:-$HOME/Library/LaunchAgents/$LABEL.plist}
MON=${HOSTCONF_MONITORING_SSH:-0mcp_monitoring}
REMOTE_FILE=${HOSTCONF_REMOTE_FILE:-/var/lib/prometheus/node-exporter/fleet_hostconf.prom}
MAX_SECONDS=${HOSTCONF_MAX_SECONDS:-2400}
PYTHON=${HOSTCONF_PYTHON:-python3}
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=5 -o ServerAliveCountMax=3"
SELF=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")

say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
tmo() { perl -e 'alarm shift; exec @ARGV' "$@"; }   # macOS has no timeout(1); an alarm kills the command (exit 142)

plist() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$INSTALL_DIR/hostconf-scheduled.sh</string><string>run</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>20</integer></dict>
  <key>RunAtLoad</key><false/>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
  <key>Nice</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF
}

# The tool and the manifest: a depth-1 blobless sparse checkout of main, two paths. HOSTCONF_REPO_DIR (tests, a branch under review) skips git.
checkout() {
  if [ -n "${HOSTCONF_REPO_DIR:-}" ]; then REPO=$HOSTCONF_REPO_DIR; return 0; fi
  REPO=$STATE/repo
  if [ ! -d "$REPO/.git" ]; then
    mkdir -p "$STATE" || return 1
    git clone --quiet --filter=blob:none --no-checkout --depth 1 "$REPO_URL" "$REPO" || return 1
    git -C "$REPO" sparse-checkout set --no-cone /scripts/hostconf.py /config/hostconf/ || return 1
  fi
  git -C "$REPO" fetch --quiet --depth 1 origin main || return 1
  git -C "$REPO" reset --quiet --hard FETCH_HEAD || return 1
}

# One ssh to the monitoring VM: write beside the target and rename over it (node_exporter reads only *.prom, so a half-written file is never seen).
ship() {
  local tmp="$(dirname "$REMOTE_FILE")/.$(basename "$REMOTE_FILE").tmp"
  # shellcheck disable=SC2086
  ssh $SSH_OPTS "$MON" "sudo -n tee '$tmp' >/dev/null && sudo -n chmod 0644 '$tmp' && sudo -n mv -f '$tmp' '$REMOTE_FILE' || { sudo -n rm -f '$tmp'; exit 1; }" < "$1"
}

run() {
  mkdir -p "$STATE" "$(dirname "$LOG")" || return 1
  if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 2000000 ]; then tail -c 1000000 "$LOG" > "$LOG.tmp" && mv -f "$LOG.tmp" "$LOG"; fi
  # LOCK and WORK are globals on purpose: the EXIT trap runs after this function has returned, when a local would be gone (set -u then aborts the trap and the lock stays)
  LOCK="$STATE/run.lock"; WORK=""
  local pid
  if ! mkdir "$LOCK" 2>/dev/null; then
    pid=$(cat "$LOCK/pid" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then say "another run is active (pid $pid), nothing to do"; return 0; fi
    rm -rf "$LOCK"; mkdir "$LOCK" || return 1
  fi
  echo $$ > "$LOCK/pid"
  trap 'rm -rf "$LOCK"; if [ -n "$WORK" ]; then rm -rf "$WORK"; fi' EXIT
  WORK=$(mktemp -d "${TMPDIR:-/tmp}/hostconf-drift.XXXXXX") || return 1

  say "start: checkout, drift --all, ship to $MON"
  checkout || { say "FAILED: could not get the tool and the manifest from main ($REPO_URL)"; return 1; }
  say "using $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo 'a plain directory') in $REPO"
  tmo "$MAX_SECONDS" "$PYTHON" "$REPO/scripts/hostconf.py" drift --all --textfile-dir "$WORK"
  local rc=$?
  case $rc in
    0|2|3) ;;   # 0 in sync, 2 drift, 3 something could not be looked at: all three are results
    *) say "FAILED: hostconf.py exited $rc (1 = the manifest is invalid or the tool crashed, 142 = no answer in ${MAX_SECONDS}s); nothing shipped"; return 1 ;;
  esac
  if ! grep -q '^fleet_hostconf_last_run_timestamp_seconds ' "$WORK/fleet_hostconf.prom" 2>/dev/null; then
    say "FAILED: the tool wrote no metrics file; nothing shipped"; return 1
  fi
  ship "$WORK/fleet_hostconf.prom" || { say "FAILED: could not write $REMOTE_FILE on $MON"; return 1; }
  say "shipped $(wc -l < "$WORK/fleet_hostconf.prom" | tr -d ' ') metric lines (hostconf.py exit $rc: 0 in sync, 2 drift, 3 not everything reachable)"
}

status() {
  echo "log:       $LOG"
  [ -f "$LOG" ] && tail -n 4 "$LOG" | sed 's/^/           /'
  if command -v launchctl >/dev/null 2>&1 && launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
    echo "agent:     loaded ($LABEL)"
    launchctl print "gui/$(id -u)/$LABEL" | grep -E "^\s+(state|runs|last exit code) =" | sed 's/^\s*/           /'
  else
    echo "agent:     not loaded (run: $SELF install)"
  fi
  # shellcheck disable=SC2086
  ssh $SSH_OPTS "$MON" "sudo -n stat -c '%y' '$REMOTE_FILE'" 2>/dev/null | sed 's/^/remote file written: /' || true
}

install() {
  command -v launchctl >/dev/null 2>&1 || { echo "install needs macOS (launchctl)"; return 1; }
  mkdir -p "$STATE" || return 1
  # the checkout first: an install that cannot fetch main must not leave an agent file that launchd would load at the next login
  checkout || { echo "could not make the first checkout of $REPO_URL (is git logged in?)"; return 1; }
  mkdir -p "$INSTALL_DIR" "$(dirname "$PLIST")" "$(dirname "$LOG")" || return 1
  cp -f "$SELF" "$INSTALL_DIR/hostconf-scheduled.sh" && chmod 0755 "$INSTALL_DIR/hostconf-scheduled.sh" || return 1
  plist > "$PLIST" || return 1
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST" || return 1
  echo "installed: runs daily at 12:20 local; now: launchctl kickstart gui/$(id -u)/$LABEL ; check: $INSTALL_DIR/hostconf-scheduled.sh status"
}

uninstall() {
  command -v launchctl >/dev/null 2>&1 && launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1
  rm -f "$PLIST"; rm -rf "$INSTALL_DIR"
  echo "removed the LaunchAgent and $INSTALL_DIR (log $LOG and checkout $STATE kept)"
}

case "${1:-run}" in
  run) run ;;
  status) status ;;
  install) install ;;
  uninstall) uninstall ;;
  plist) plist ;;
  *) echo "usage: $0 run|status|install|uninstall|plist" >&2; exit 2 ;;
esac
