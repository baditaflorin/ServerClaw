#!/bin/sh
# Run inside a disposable Linux container. No host systemd or network is touched.
set -eu
source_dir=${1:-/src}
src=$(mktemp -d)
cp -R "$source_dir"/. "$src"/
bin=$(mktemp -d)
export PATH="$bin:$PATH"
mkdir -p /usr/sbin /var/lib/prometheus/node-exporter
cat > /usr/sbin/tailscaled <<'STOCK'
#!/bin/sh
if [ "${1:-}" = --version ]; then echo 1.104.7; exit 0; fi
exec /bin/sleep 300
STOCK
chmod 755 /usr/sbin/tailscaled
cat > "$bin/systemd-run" <<'STUB'
#!/bin/sh
if [ -e /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf ]; then
  [ -e /etc/tailscale-endpoint-filter/version ] && [ ! -e /etc/tailscale-endpoint-filter/pending ] || exit 1
fi
echo armed >> /tmp/filter-events
STUB
cat > "$bin/logger" <<'STUB'
#!/bin/sh
exit 0
STUB
cat > "$bin/systemctl" <<'STUB'
#!/bin/sh
case "$1" in
  restart)
    if [ -e /tmp/fail-next-restart ]; then rm /tmp/fail-next-restart; exit 1; fi
    if [ -s /tmp/filter-pid ]; then kill "$(cat /tmp/filter-pid)" 2>/dev/null || true; fi
    if [ -f /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf ]; then
      /usr/local/libexec/tailscaled-endpoint-filter-wrapper 300 </dev/null >/dev/null 2>&1 9>&- &
    else
      /usr/sbin/tailscaled 300 </dev/null >/dev/null 2>&1 9>&- &
    fi
    echo "$!" > /tmp/filter-pid
    sleep 0.2
    ;;
  show) if [ "${2:-}" = prometheus-node-exporter ]; then cat /tmp/node-pid 2>/dev/null || echo 0; else cat /tmp/filter-pid; fi ;;
  is-active) test -s /tmp/filter-pid && kill -0 "$(cat /tmp/filter-pid)" ;;
  daemon-reload|enable|stop) : ;;
  *) exit 1 ;;
esac
STUB
chmod 755 "$bin/systemd-run" "$bin/systemctl" "$bin/logger"
cp "$bin/logger" "$bin/systemd-analyze"
cat > /tmp/filter-fake.go <<'GO'
package main
import ("fmt"; "os"; "time")
var buildMarker = "original"
func main() {
  if buildMarker == "impossible" { fmt.Println(buildMarker) }
  if len(os.Args) > 1 && os.Args[1] == "--version" { fmt.Println("1.104.7"); return }
  time.Sleep(5 * time.Minute)
}
GO
CGO_ENABLED=0 go build -o /tmp/tailscaled-candidate /tmp/filter-fake.go
sha=$(sha256sum /tmp/tailscaled-candidate | awk '{print $1}')
python3 - "$src/release-manifest.json" "$sha" <<'PY'
import json,sys
p=sys.argv[1]
with open(p) as f: d=json.load(f)
d['releases']['1.104.7']['static_binary_sha256']=sys.argv[2]
with open(p,'w') as f: json.dump(d,f)
PY
/usr/sbin/tailscaled 300 </dev/null >/dev/null 2>&1 &
echo "$!" >/tmp/filter-pid
"$src/install-canary.sh" apply /tmp/tailscaled-candidate "$sha"
grep -q '^armed$' /tmp/filter-events
grep -q '^fleet_tailscale_endpoint_filter_healthy 1$' /var/lib/prometheus/node-exporter/tailscale-endpoint-filter.prom
grep -q '^fleet_tailscale_endpoint_filter_sender_guard_active 1$' /var/lib/prometheus/node-exporter/tailscale-endpoint-filter.prom
"$src/install-canary.sh" rollback
[ ! -e /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf ]
[ ! -e /etc/tailscale-endpoint-filter/pending ]
printf '%s\n' 'unrelated unit' > /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf
if "$src/install-canary.sh" apply /tmp/tailscaled-candidate "$sha"; then
  echo 'installer overwrote an existing unit' >&2
  exit 1
fi
grep -qx 'unrelated unit' /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf
rm /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf
"$src/install-canary.sh" apply /tmp/tailscaled-candidate "$sha"
"$src/install-canary.sh" commit
[ -e /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf ]
[ ! -e /etc/tailscale-endpoint-filter/pending ]
# Upgrade an existing confirmed candidate, then exercise the independent rollback.
CGO_ENABLED=0 go build -ldflags '-X main.buildMarker=upgraded' -o /tmp/tailscaled-upgraded /tmp/filter-fake.go
newsha=$(sha256sum /tmp/tailscaled-upgraded | awk '{print $1}')
[ "$newsha" != "$sha" ]
python3 - "$src/release-manifest.json" "$sha" "$newsha" <<'PYMANIFEST'
import hashlib,json,sys
p,old,new=sys.argv[1:]
with open(p) as f: d=json.load(f)
d['releases']['1.104.7']['previous_static_binary_sha256']=old
d['releases']['1.104.7']['static_binary_sha256']=new
d['previous_installed_hashes']={}
for key,path in [('wrapper','/usr/local/libexec/tailscaled-endpoint-filter-wrapper'),('health','/usr/local/libexec/tailscale-endpoint-filter-health')]:
    with open(path,'rb') as f: d['previous_installed_hashes'][key]=[hashlib.sha256(f.read()).hexdigest()]
with open(p,'w') as f: json.dump(d,f)
PYMANIFEST
# Refuse to overwrite an independently changed wrapper.
cp /usr/local/libexec/tailscaled-endpoint-filter-wrapper /tmp/old-wrapper
printf '# independent edit\n' >> /usr/local/libexec/tailscaled-endpoint-filter-wrapper
if "$src/upgrade-canary.sh" /tmp/tailscaled-upgraded "$newsha" 1.104.7; then
  echo 'upgrade overwrote a changed wrapper' >&2
  exit 1
fi
[ ! -e /etc/tailscale-endpoint-filter/pending ]
cp /tmp/old-wrapper /usr/local/libexec/tailscaled-endpoint-filter-wrapper
# A failed restart must automatically restore the previous filtered daemon.
: > /tmp/fail-next-restart
if "$src/upgrade-canary.sh" /tmp/tailscaled-upgraded "$newsha" 1.104.7; then
  echo 'upgrade unexpectedly succeeded after injected restart failure' >&2
  exit 1
fi
[ -e /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf ]
[ ! -e /etc/tailscale-endpoint-filter/pending ]
[ ! -e /etc/tailscale-endpoint-filter/pending-upgrade ]
[ "$(cat /etc/tailscale-endpoint-filter/sha256)" = "$sha" ]
[ "$(readlink "/proc/$(cat /tmp/filter-pid)/exe")" = /opt/tailscale-endpoint-filter/tailscaled-filtered ]
/usr/local/libexec/tailscale-endpoint-filter-health
# An explicitly rolled-back upgrade also restores the same previous filter.
"$src/upgrade-canary.sh" /tmp/tailscaled-upgraded "$newsha" 1.104.7
[ "$(cat /etc/tailscale-endpoint-filter/sha256)" = "$newsha" ]
grep -q '^fleet_tailscale_endpoint_filter_healthy 1$' /var/lib/prometheus/node-exporter/tailscale-endpoint-filter.prom
grep -q '^fleet_tailscale_endpoint_filter_sender_guard_active 1$' /var/lib/prometheus/node-exporter/tailscale-endpoint-filter.prom
"$src/install-canary.sh" rollback
[ -e /etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf ]
[ "$(cat /etc/tailscale-endpoint-filter/sha256)" = "$sha" ]
[ "$(sha256sum "/var/lib/tailscale-endpoint-filter/backups/$sha/tailscaled-filtered" | awk '{print $1}')" = "$sha" ]
/usr/local/libexec/tailscale-endpoint-filter-health
"$src/upgrade-canary.sh" /tmp/tailscaled-upgraded "$newsha" 1.104.7
# A timer racing confirmation must wait for the installer lock and recheck
# the pending marker after confirmation has cleared it.
exec 8>/run/lock/tailscale-endpoint-filter.lock
flock 8
/usr/local/libexec/tailscale-endpoint-filter-upgrade-rollback 8>&- &
rollback_pid=$!
sleep 0.3
kill -0 "$rollback_pid"
rm /etc/tailscale-endpoint-filter/pending-upgrade
flock -u 8
wait "$rollback_pid"
[ "$(cat /etc/tailscale-endpoint-filter/sha256)" = "$newsha" ]
"$src/install-canary.sh" commit
[ ! -e /etc/tailscale-endpoint-filter/pending-upgrade ]
mkdir -p /var/lib/prometheus/node-exporter/textfile
python3 -c 'import time; time.sleep(300)' --collector.textfile.directory=/var/lib/prometheus/node-exporter/textfile </dev/null >/dev/null 2>&1 &
node_pid=$!
echo "$node_pid" > /tmp/node-pid
/usr/local/libexec/tailscale-endpoint-filter-health
grep -q '^fleet_tailscale_endpoint_filter_healthy 1$' /var/lib/prometheus/node-exporter/textfile/tailscale-endpoint-filter.prom
kill "$node_pid" 2>/dev/null || true
mkdir -p /var/lib/prometheus-node-exporter/textfile
python3 -c 'import time; time.sleep(300)' --collector.textfile.directory=/var/lib/prometheus-node-exporter/textfile </dev/null >/dev/null 2>&1 &
node_pid=$!
echo "$node_pid" > /tmp/node-pid
/usr/local/libexec/tailscale-endpoint-filter-health
grep -q '^fleet_tailscale_endpoint_filter_sender_guard_active 1$' /var/lib/prometheus-node-exporter/textfile/tailscale-endpoint-filter.prom
kill "$node_pid" 2>/dev/null || true
rm /tmp/node-pid
sed -i 's/echo 1.104.7/echo 1.104.8/' /usr/sbin/tailscaled
if /usr/local/libexec/tailscale-endpoint-filter-health; then
  echo 'health check missed upstream version drift' >&2
  exit 1
fi
grep -q '^fleet_tailscale_endpoint_filter_healthy 0$' /var/lib/prometheus/node-exporter/tailscale-endpoint-filter.prom
/usr/local/libexec/tailscaled-endpoint-filter-wrapper 300 </dev/null >/dev/null 2>&1 &
fallback=$!
sleep 0.2
[ "$(readlink "/proc/$fallback/exe")" != /opt/tailscale-endpoint-filter/tailscaled-filtered ]
kill "$fallback" 2>/dev/null || true
kill "$(cat /tmp/filter-pid)" 2>/dev/null || true
echo 'isolated canary install, upgrade, rollback, commit and version-drift fallback passed'
