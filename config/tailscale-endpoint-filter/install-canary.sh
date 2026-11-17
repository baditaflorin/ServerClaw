#!/bin/sh
# Install one canary with a timed local rollback; confirm only after peer and service checks.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'must run as root' >&2; exit 1; }
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
state=/etc/tailscale-endpoint-filter
unit=tailscale-endpoint-filter-canary-rollback
exec 9>/run/lock/tailscale-endpoint-filter.lock
flock -n 9 || { echo 'endpoint filter operation already active' >&2; exit 1; }
case "${1:-}" in
  apply)
    artifact=${2:?artifact path required}
    wanted=${3:?artifact SHA-256 required}
    release=${4:-1.104.7}
    approved=$(python3 -c 'import json,re,sys; r=json.load(open(sys.argv[1]))["releases"].get(sys.argv[2]); assert r and re.fullmatch(r"[0-9a-f]{64}",r["static_binary_sha256"]); print(r["static_binary_sha256"])' "$here/release-manifest.json" "$release") || { echo 'unsupported tested release' >&2; exit 2; }
    case "$wanted" in *[!0-9a-f]*|'') echo 'invalid SHA-256' >&2; exit 2;; esac
    [ "${#wanted}" -eq 64 ] || { echo 'invalid SHA-256 length' >&2; exit 2; }
    [ "$wanted" = "$approved" ] || { echo 'artifact is not the reviewed release build' >&2; exit 1; }
    [ -f "$artifact" ] && [ ! -L "$artifact" ] || { echo 'artifact must be a regular file' >&2; exit 1; }
    [ "$(sha256sum "$artifact" | awk '{print $1}')" = "$wanted" ] || { echo 'artifact checksum mismatch' >&2; exit 1; }
    [ "$("$artifact" --version | sed -n '1p')" = "$release" ] || { echo 'candidate version differs from target release' >&2; exit 1; }
    [ "$(/usr/sbin/tailscaled --version | sed -n '1p')" = "$release" ] || { echo 'installed Tailscale version differs from tested build' >&2; exit 1; }
    systemctl is-active --quiet tailscaled || { echo 'tailscaled is not active' >&2; exit 1; }
    dropin=/etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf
    [ ! -e "$dropin" ] && [ ! -e "$state/pending" ] || { echo 'endpoint filter already present; refusing to overwrite' >&2; exit 1; }
    for pair in 'tailscaled-wrapper.sh:/usr/local/libexec/tailscaled-endpoint-filter-wrapper' \
                'rollback.sh:/usr/local/libexec/tailscale-endpoint-filter-rollback' \
                'health.sh:/usr/local/libexec/tailscale-endpoint-filter-health' \
                'health.service:/etc/systemd/system/tailscale-endpoint-filter-health.service' \
                'health.timer:/etc/systemd/system/tailscale-endpoint-filter-health.timer'; do
      source_name=${pair%%:*}; target=${pair#*:}
      [ ! -e "$target" ] || cmp -s "$here/$source_name" "$target" || { echo 'conflicting filter file already exists' >&2; exit 1; }
    done
    existing=/opt/tailscale-endpoint-filter/tailscaled-filtered
    [ ! -e "$existing" ] || [ "$(sha256sum "$existing" | awk '{print $1}')" = "$wanted" ] || { echo 'conflicting candidate already exists' >&2; exit 1; }
    [ ! -e "$state/version" ] || [ "$(cat "$state/version")" = "$release" ] || { echo 'conflicting filter configuration' >&2; exit 1; }
    [ ! -e "$state/sha256" ] || [ "$(cat "$state/sha256")" = "$wanted" ] || { echo 'conflicting filter checksum' >&2; exit 1; }
    [ ! -e "$state/interfaces" ] || [ "$(cat "$state/interfaces")" = 'br-*,docker*,veth*' ] || { echo 'conflicting interface filter' >&2; exit 1; }
    install -d -m 755 "$state" /opt/tailscale-endpoint-filter /usr/local/libexec /etc/systemd/system/tailscaled.service.d
    install -m 755 "$artifact" /opt/tailscale-endpoint-filter/tailscaled-filtered
    [ "$(sha256sum /opt/tailscale-endpoint-filter/tailscaled-filtered | awk '{print $1}')" = "$wanted" ] || { echo 'installed artifact checksum mismatch' >&2; exit 1; }
    install -m 755 "$here/tailscaled-wrapper.sh" /usr/local/libexec/tailscaled-endpoint-filter-wrapper
    install -m 755 "$here/rollback.sh" /usr/local/libexec/tailscale-endpoint-filter-rollback
    install -m 755 "$here/health.sh" /usr/local/libexec/tailscale-endpoint-filter-health
    install -m 644 "$here/health.service" /etc/systemd/system/tailscale-endpoint-filter-health.service
    install -m 644 "$here/health.timer" /etc/systemd/system/tailscale-endpoint-filter-health.timer
    printf '%s\n' "$release" > "$state/version"
    printf '%s\n' "$wanted" > "$state/sha256"
    printf '%s\n' 'br-*,docker*,veth*' > "$state/interfaces"
    sha256sum "$here/tailscaled.service.conf" | awk '{print $1}' > "$state/dropin.sha256"
    # Arm the independent local rollback BEFORE writing the active unit.
    systemd-run --unit="$unit" --on-active=5m --collect /usr/local/libexec/tailscale-endpoint-filter-rollback >/dev/null
    : > "$state/pending"
    staged="$dropin.stage.$$"
    install -m 644 "$here/tailscaled.service.conf" "$staged"
    if ! ln "$staged" "$dropin"; then
      rm "$staged" "$state/pending"
      systemctl stop "$unit.timer" || true
      echo 'unit appeared concurrently; no daemon change was made' >&2
      exit 1
    fi
    rm "$staged"
    if ! systemctl daemon-reload || ! systemd-analyze verify tailscaled.service tailscale-endpoint-filter-health.service tailscale-endpoint-filter-health.timer || ! systemctl restart tailscaled || ! systemctl is-active --quiet tailscaled; then
      /usr/local/libexec/tailscale-endpoint-filter-rollback
      exit 1
    fi
    pid=$(systemctl show tailscaled -p MainPID --value)
    [ "$(readlink "/proc/$pid/exe")" = /opt/tailscale-endpoint-filter/tailscaled-filtered ] || { /usr/local/libexec/tailscale-endpoint-filter-rollback; exit 1; }
    systemctl enable --now tailscale-endpoint-filter-health.timer
    /usr/local/libexec/tailscale-endpoint-filter-health
    echo 'canary active; automatic rollback remains armed until explicit verification and commit'
    ;;
  commit)
    [ -f "$state/pending" ] || { echo 'no active canary' >&2; exit 1; }
    /usr/local/libexec/tailscale-endpoint-filter-health
    systemctl stop "$unit.timer"
    rm -f "$state/pending-upgrade"
    rm "$state/pending"
    echo 'canary committed after external verification'
    ;;
  rollback)
    if [ -f "$state/pending-upgrade" ]; then
      TS_FILTER_LOCK_HELD=1 /usr/local/libexec/tailscale-endpoint-filter-upgrade-rollback
    else
      /usr/local/libexec/tailscale-endpoint-filter-rollback
    fi
    systemctl stop "$unit.timer" || true
    ;;
  *) echo 'usage: install-canary.sh apply ARTIFACT SHA256 [VERSION] | commit | rollback' >&2; exit 2;;
esac
