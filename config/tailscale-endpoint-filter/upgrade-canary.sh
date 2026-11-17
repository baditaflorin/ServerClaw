#!/bin/sh
# Upgrade an existing filter with a timed fallback to the vendor daemon.
# Confirm with install-canary.sh commit only after independent service checks.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'must run as root' >&2; exit 1; }
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
state=/etc/tailscale-endpoint-filter
candidate=/opt/tailscale-endpoint-filter/tailscaled-filtered
dropin=/etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf
unit=tailscale-endpoint-filter-canary-rollback
artifact=${1:?artifact path required}
wanted=${2:?artifact SHA-256 required}
release=${3:?installed release required}
exec 9>/run/lock/tailscale-endpoint-filter.lock
flock -n 9 || { echo 'endpoint filter operation already active' >&2; exit 1; }
metadata=$(python3 - "$here/release-manifest.json" "$release" <<'PY'
import json,re,sys
with open(sys.argv[1]) as f: d=json.load(f)
r=d['releases'].get(sys.argv[2]); assert r
values=[r['static_binary_sha256'],r['previous_static_binary_sha256']]
assert all(re.fullmatch(r'[0-9a-f]{64}',x) for x in values)
print(*values)
PY
) || { echo 'unsupported reviewed release' >&2; exit 1; }
set -f
# The parser emits exactly two validated hashes.
# shellcheck disable=SC2086
set -- $metadata
approved=$1; previous=$2
[ "$wanted" = "$approved" ] || { echo 'candidate is not the reviewed build' >&2; exit 1; }
[ -f "$artifact" ] && [ ! -L "$artifact" ] && [ "$(sha256sum "$artifact" | awk '{print $1}')" = "$wanted" ] || { echo 'candidate checksum mismatch' >&2; exit 1; }
[ "$("$artifact" --version | sed -n '1p')" = "$release" ] && [ "$(/usr/sbin/tailscaled --version | sed -n '1p')" = "$release" ] || { echo 'candidate or package version mismatch' >&2; exit 1; }
[ ! -e "$state/pending" ] && [ ! -e "$state/pending-upgrade" ] && [ -f "$dropin" ] && [ -f "$state/dropin.sha256" ] || { echo 'no stable managed filter to upgrade' >&2; exit 1; }
[ "$(sha256sum "$dropin" | awk '{print $1}')" = "$(cat "$state/dropin.sha256")" ] || { echo 'managed unit changed' >&2; exit 1; }
[ "$(cat "$state/version")" = "$release" ] && [ "$(cat "$state/sha256")" = "$previous" ] && [ "$(sha256sum "$candidate" | awk '{print $1}')" = "$previous" ] || { echo 'installed filter is not the reviewed previous build' >&2; exit 1; }
systemctl is-active --quiet tailscaled || { echo 'tailscaled is not active' >&2; exit 1; }
pid=$(systemctl show tailscaled -p MainPID --value)
[ "$(readlink "/proc/$pid/exe")" = "$candidate" ] || { echo 'existing patched daemon is not active' >&2; exit 1; }
python3 - "$here/release-manifest.json" <<'PYVERIFY'
import hashlib,json,sys
with open(sys.argv[1]) as f: d=json.load(f)
for name,path in [('wrapper','/usr/local/libexec/tailscaled-endpoint-filter-wrapper'),('health','/usr/local/libexec/tailscale-endpoint-filter-health')]:
    with open(path,'rb') as f: actual=hashlib.sha256(f.read()).hexdigest()
    if actual not in d['previous_installed_hashes'][name]:
        raise SystemExit('existing managed '+name+' differs from reviewed versions')
PYVERIFY
/usr/local/libexec/tailscale-endpoint-filter-health
for pair in 'rollback.sh:/usr/local/libexec/tailscale-endpoint-filter-rollback' \
            'health.service:/etc/systemd/system/tailscale-endpoint-filter-health.service' \
            'health.timer:/etc/systemd/system/tailscale-endpoint-filter-health.timer' \
            'tailscaled.service.conf:/etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf'; do
  source_name=${pair%%:*}; target=${pair#*:}
  cmp -s "$here/$source_name" "$target" || { echo 'existing managed file differs from reviewed source' >&2; exit 1; }
done
# Preserve the previous immutable candidate for operator rollback.
backup=/var/lib/tailscale-endpoint-filter/backups/$previous
if [ -e "$backup" ]; then
  [ -f "$backup/tailscaled-filtered" ] && [ "$(sha256sum "$backup/tailscaled-filtered" | awk '{print $1}')" = "$previous" ] || { echo 'existing backup conflicts' >&2; exit 1; }
else
  install -d -m 700 "$backup"
  install -m 755 "$candidate" "$backup/tailscaled-filtered"
  install -m 755 /usr/local/libexec/tailscaled-endpoint-filter-wrapper "$backup/tailscaled-wrapper.sh"
  install -m 755 /usr/local/libexec/tailscale-endpoint-filter-health "$backup/health.sh"
  sha256sum "$backup/tailscaled-wrapper.sh" | awk '{print $1}' > "$backup/tailscaled-wrapper.sh.sha256"
  sha256sum "$backup/health.sh" | awk '{print $1}' > "$backup/health.sh.sha256"
  [ "$(sha256sum "$backup/tailscaled-filtered" | awk '{print $1}')" = "$previous" ] || { echo 'backup checksum mismatch' >&2; exit 1; }
fi
for name in tailscaled-wrapper.sh health.sh; do
  [ -f "$backup/$name" ] && [ -f "$backup/$name.sha256" ] && [ "$(sha256sum "$backup/$name" | awk '{print $1}')" = "$(cat "$backup/$name.sha256")" ] || { echo 'backup scripts are invalid' >&2; exit 1; }
done
rollback=/usr/local/libexec/tailscale-endpoint-filter-upgrade-rollback
[ ! -e "$rollback" ] || cmp -s "$here/upgrade-rollback.sh" "$rollback" || { echo 'upgrade rollback script conflicts' >&2; exit 1; }
install -m 755 "$here/upgrade-rollback.sh" "$rollback"
newbin="$candidate.stage.$$"
newwrapper="/usr/local/libexec/.tailscaled-endpoint-filter-wrapper.$$"
newhealth="/usr/local/libexec/.tailscale-endpoint-filter-health.$$"
newsha="$state/.sha256.$$"
armed=0
cleanup() {
  rc=$?
  rm -f "$newbin" "$newwrapper" "$newhealth" "$newsha"
  if [ "$rc" -ne 0 ] && [ "$armed" -eq 1 ]; then
    if TS_FILTER_LOCK_HELD=1 "$rollback"; then
      systemctl stop "$unit.timer" || true
    else
      logger -p daemon.err -t tailscale-endpoint-filter 'Upgrade rollback failed; leaving the independent timer armed'
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
install -m 755 "$artifact" "$newbin"
install -m 755 "$here/tailscaled-wrapper.sh" "$newwrapper"
install -m 755 "$here/health.sh" "$newhealth"
printf '%s\n' "$wanted" > "$newsha"
systemd-run --unit="$unit" --on-active=5m --collect --setenv=TS_FILTER_LOCK_HELD=0 "$rollback" >/dev/null
printf '%s\n' "$previous" > "$state/pending-upgrade"
: > "$state/pending"
armed=1
mv -f "$newbin" "$candidate"
mv -f "$newwrapper" /usr/local/libexec/tailscaled-endpoint-filter-wrapper
mv -f "$newhealth" /usr/local/libexec/tailscale-endpoint-filter-health
mv -f "$newsha" "$state/sha256"
systemctl restart tailscaled
systemctl is-active --quiet tailscaled
pid=$(systemctl show tailscaled -p MainPID --value)
[ "$(readlink "/proc/$pid/exe")" = "$candidate" ] || { echo 'new filtered daemon is not active' >&2; exit 1; }
systemctl enable --now tailscale-endpoint-filter-health.timer
/usr/local/libexec/tailscale-endpoint-filter-health
armed=0
echo 'upgrade active; automatic rollback remains armed until explicit verification and commit'
