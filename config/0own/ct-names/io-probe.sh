#!/usr/bin/env bash
# A small, self-aborting throughput probe: one sequential write and one sequential read of a scratch file, and 30 tiny synced writes
# (the latency the keystore and the builder feel). Run it where the data will live: on the hypervisor with --dir /var/lib/vz (raw pool),
# and later inside the VM with --dir /srv/ct-names (it then measures the IO cap, not the disk). It DELETES its scratch file on exit.
# It refuses to start when the IO pressure is already high, and stops if the pressure climbs while it runs.
set -euo pipefail
DIR=""; MB=512; PSI_MAX="${PSI_MAX:-10}"
while [ $# -gt 0 ]; do case "$1" in --dir) DIR="$2"; shift 2 ;; --mb) MB="$2"; shift 2 ;; *) echo "usage: $0 --dir DIR [--mb N]" >&2; exit 2 ;; esac; done
[ -n "$DIR" ] && [ -d "$DIR" ] || { echo "need an existing --dir" >&2; exit 2; }
case "$MB" in ''|*[!0-9]*) echo "--mb must be a number" >&2; exit 2 ;; esac
[ "$MB" -le 2048 ] || { echo "REFUSING: more than 2048 MB is not a small test" >&2; exit 2; }

psi() { awk '/^full/ {for(i=1;i<=NF;i++) if ($i ~ /^avg10=/) {sub("avg10=","",$i); print int($i)}}' "${PSI_FILE:-/proc/pressure/io}"; }
echo "load: $(cat /proc/loadavg 2>/dev/null || uptime)"; echo "io pressure: $(grep '^full' "${PSI_FILE:-/proc/pressure/io}")"
now="$(psi)"
if [ "$now" -gt "$PSI_MAX" ]; then echo "ABORT: io full avg10 is ${now}% (limit ${PSI_MAX}%). Try a quieter hour; nothing was written." >&2; exit 3; fi

f="${DIR%/}/.ct-names-io-probe.$$"
trap 'rm -f -- "$f" "${f}.sync"' EXIT
t0=$(date +%s.%N)
dd if=/dev/urandom bs=1M count="$MB" 2>/dev/null | dd of="$f" bs=1M conv=fdatasync 2>/dev/null
t1=$(date +%s.%N)
echo "write ${MB} MB sequential (fdatasync at the end): $(awk -v m="$MB" -v a="$t0" -v b="$t1" 'BEGIN{printf "%.1f MB/s in %.1f s", m/(b-a), b-a}')"
[ "$(psi)" -le $((PSI_MAX * 4)) ] || { echo "ABORT: io pressure climbed to $(psi)% during the write; stopping" >&2; exit 4; }
sync; { echo 3 > /proc/sys/vm/drop_caches; } 2>/dev/null || echo "(could not drop the page cache; the read number may be cached)"
t2=$(date +%s.%N)
dd if="$f" of=/dev/null bs=1M 2>/dev/null
t3=$(date +%s.%N)
echo "read ${MB} MB sequential: $(awk -v m="$MB" -v a="$t2" -v b="$t3" 'BEGIN{printf "%.1f MB/s in %.1f s", m/(b-a), b-a}')"
t4=$(date +%s.%N)
for _ in $(seq 1 30); do dd if=/dev/zero of="${f}.sync" bs=4k count=1 oflag=dsync conv=notrunc 2>/dev/null; done
t5=$(date +%s.%N); rm -f -- "${f}.sync"
echo "30 x 4 KiB synced writes: $(awk -v a="$t4" -v b="$t5" 'BEGIN{printf "%.1f ms each on average", (b-a)/30*1000}')"
echo "io pressure after: $(grep '^full' "${PSI_FILE:-/proc/pressure/io}")"
