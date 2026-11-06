#!/bin/bash
# Weekly PROMOTION DRILL of the vault/keystore warm standby on infer-tier0. Proves the standby copy can actually serve:
# starts the standby (bound to 127.0.0.1 only), issues a one-use key from the standby keystore, lists secrets through the standby vault,
# sanity-checks the record count against the previous drill, then stops everything again. Prints and writes no secrets.
# GUARD: if the standby is already running (that would be a REAL promotion) it does nothing at all.
set -uo pipefail
D=/opt/tier0/vault-standby; M=/var/lib/prometheus/node-exporter; STATE=$D/data/.drill-state; OUT=$M/vault_standby_drill.prom
exec 9>/run/vault-standby-drill.lock; flock -n 9 || { echo "another drill is running"; exit 0; }
cd "$D"
START=$(date +%s); STATUS=0; MSG="ok"; COUNT=0; SKIPPED=0
fail() { STATUS=1; MSG="$1"; echo "DRILL FAIL: $1" >&2; }
metrics() {
  local now; now=$(date +%s)
  { echo "# TYPE vault_standby_drill_last_run_timestamp_seconds gauge"
    echo "vault_standby_drill_last_run_timestamp_seconds $now"
    echo "vault_standby_drill_skipped $SKIPPED"
    if [ "$SKIPPED" = 0 ]; then
      echo "vault_standby_drill_last_success $((1-STATUS))"
      echo "vault_standby_drill_records $COUNT"
      echo "vault_standby_drill_duration_seconds $((now-START))"
      if [ "$STATUS" = 0 ]; then echo "vault_standby_drill_last_success_timestamp_seconds $now"; fi
    fi
  } > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
}
cleanup() {
  if [ "$SKIPPED" = 0 ]; then docker-compose stop >/dev/null 2>&1; fi
  # stop can return a moment before ps stops listing the containers as running (false FAIL on 2026-10-16 23:15Z: both had
  # exited about a second later), so poll for up to ~20 s before calling it a failure.
  for n in $(seq 1 20); do
    RUNNING=$(docker-compose ps --status running -q 2>/dev/null | wc -l)
    if [ "$SKIPPED" = 1 ] || [ "$RUNNING" -eq 0 ] || [ "$n" -eq 20 ]; then break; fi
    sleep 1
  done
  [ "$SKIPPED" = 0 ] && [ "$RUNNING" -gt 0 ] && { STATUS=1; MSG="$MSG; standby containers still running after the drill"; }
  metrics
  echo "vault standby drill: $([ $SKIPPED = 1 ] && echo SKIPPED || ([ $STATUS = 0 ] && echo PASS || echo FAIL)) ($MSG) records=$COUNT in $(( $(date +%s)-START ))s"
}
trap cleanup EXIT

if [ "$(docker-compose ps --status running -q 2>/dev/null | wc -l)" -gt 0 ]; then
  SKIPPED=1; MSG="standby is already running (real promotion?), drill refuses to touch it"; exit 0
fi
NOW=$(date +%s)
for d in vault keystore; do
  f=data/$d/.last_sync; [ -f "$f" ] || { fail "$d: no synced copy"; exit 1; }
  AGE=$(( NOW - $(cat "$f") )); [ "$AGE" -le 900 ] || { fail "$d copy is ${AGE}s old (limit 900s)"; exit 1; }
done
docker-compose up -d keystore >/dev/null 2>&1 || { fail "keystore failed to start"; exit 1; }; sleep 6
docker-compose up -d vault >/dev/null 2>&1 || { fail "vault failed to start"; exit 1; }
for i in $(seq 1 15); do curl -fsS -m 3 http://127.0.0.1:18140/health 2>/dev/null | grep -q '"status":"ok"' && break; sleep 2; done
curl -fsS -m 3 http://127.0.0.1:18140/health 2>/dev/null | grep -q '"status":"ok"' || { fail "standby vault /health not ok"; exit 1; }
RES=$(python3 "$D/drill_check.py" 2>&1) || { fail "functional check failed: $(echo "$RES" | tail -1 | cut -c1-120)"; exit 1; }
COUNT=$(echo "$RES" | sed -n 's/^records=//p' | head -1)
[ -n "$COUNT" ] && [ "$COUNT" -ge 100 ] || { fail "record count implausible ($COUNT)"; exit 1; }
if [ -f "$STATE" ]; then PREV=$(cat "$STATE"); [ "$COUNT" -ge $(( PREV * 85 / 100 )) ] || { fail "record count dropped from $PREV to $COUNT (>15%)"; exit 1; }; fi
echo "$COUNT" > "$STATE"
MSG="standby served $COUNT records through its own keystore-issued key"
