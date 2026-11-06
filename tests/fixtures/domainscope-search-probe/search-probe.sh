#!/usr/bin/env bash
# scripts/search-probe.sh — checks that production search answers, with real results.
#
# Runs the golden queries of scripts/search-golden-queries.tsv against a base URL and fails when a query errors, answers fewer
# rows than its minimum, or answers a smart search with no_results_reason=catalog_matches_not_searchable. With an uncached
# semantic query first (a fresh nonce each run), so the embedding path is exercised, not search_cache. Written after the
# 2026-10-20 outage, which every route-level smoke check passed: semantic search answered 500/503 to every uncached query and
# country-scoped smart search answered 0 rows.
#
# Usage:
#   scripts/search-probe.sh [--all] [--markets N] [--metrics-file PATH] [base-url]
#     (default)     the queries gated "deploy": what scripts/smoke-check.sh runs after every deploy; a few cached queries
#     --all         every golden query (the scheduled probe); rows gated "known-failing" run and are reported, never fail it
#     --markets N   also N published /markets/:country/:sector cells, picked at random: the brief their "full list" link
#                   runs on the niche map must answer at least min(SEARCH_PROBE_MARKET_MIN, the cell's company count) rows
#     --metrics-file PATH
#                   also write the result as Prometheus textfile metrics (node exporter textfile collector), atomically
#                   (a temp file in the same directory, then rename), on every exit, errors included:
#                     domainscope_search_probe_success                     1 all gating checks passed, 0 otherwise
#                     domainscope_search_probe_failed_checks               gating checks that failed (an error counts as one)
#                     domainscope_search_probe_checks_total                gating checks run
#                     domainscope_search_probe_known_failing_checks        "known-failing" checks run (informational)
#                     domainscope_search_probe_known_failing_failed_checks those of them that failed
#                     domainscope_search_probe_duration_seconds            wall time of the run
#                     domainscope_search_probe_last_run_timestamp_seconds  end of the run, Unix time
#                   every series carries target="<base-url>"
#
# Environment (arguments win):
#   SEARCH_PROBE_BASE_URL        default https://domainscope.scrapetheworld.org
#   SEARCH_PROBE_FILE            default scripts/search-golden-queries.tsv
#   SEARCH_PROBE_MIN_OVERRIDE    one minimum for every golden query (e.g. 1 to check only that search answers)
#   SEARCH_PROBE_UNCACHED        1 (default) runs the uncached semantic probe, 0 skips it
#   SEARCH_PROBE_UNCACHED_MIN    rows the uncached semantic probe must return, default 1
#   SEARCH_PROBE_MARKET_MIN      default 5
#   SEARCH_PROBE_TIMEOUT         seconds per request, default 60 (a first smart search parses the brief with the LLM)
#   SEARCH_PROBE_ATTEMPTS        tries per query before it fails, default 2
#   SEARCH_PROBE_SLEEP           seconds between requests, default 1 (anonymous search is rate limited per address)
#   SEARCH_PROBE_METRICS_FILE    same as --metrics-file
#
# Exit status: 0 all green, 1 at least one check failed or the probe itself broke (a missing market catalog, a helper that
# crashed: never "passed"), 64 bad usage.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE=deploy
MARKETS=0
METRICS_FILE="${SEARCH_PROBE_METRICS_FILE:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) GATE=all; shift ;;
    --markets|--metrics-file)
      [[ $# -ge 2 && -n "$2" ]] || { echo "search-probe: $1 needs a value" >&2; exit 64; }
      if [[ "$1" == --markets ]]; then MARKETS="$2"; else METRICS_FILE="$2"; fi
      shift 2 ;;
    -h|--help) sed -n '2,46p' "$0"; exit 0 ;;
    --*) echo "search-probe: unknown option $1" >&2; exit 64 ;;
    *) break ;;
  esac
done
BASE_URL="${1:-${SEARCH_PROBE_BASE_URL:-https://domainscope.scrapetheworld.org}}"
BASE_URL="${BASE_URL%/}"

START_EPOCH="$(date +%s)"
failures=0          # gating checks that failed
checks=0            # gating checks run
known_checks=0      # "known-failing" checks run (informational)
known_failures=0    # those of them that failed

# write_metrics <exit status>: the textfile metrics of this run, written to a temp file next to METRICS_FILE and renamed
# over it, so the node exporter never reads half a file. The temp name does not end in .prom: the collector skips it.
write_metrics() {
  local status="$1" success=0 failed="${failures}" end target tmp
  [[ -n "${METRICS_FILE}" ]] || return 0
  # An error that ended the run early (status != 0 with no failed check) still counts as a failed check.
  if [[ "${status}" -ne 0 && "${failed}" -eq 0 ]]; then failed=1; fi
  [[ "${status}" -eq 0 && "${failed}" -eq 0 ]] && success=1
  end="$(date +%s)"
  target="${BASE_URL//\\/\\\\}"; target="${target//\"/\\\"}"
  tmp="$(dirname "${METRICS_FILE}")/.$(basename "${METRICS_FILE}").tmp.$$"
  {
    printf '# HELP domainscope_search_probe_success 1 when the last DomainScope search probe ran to the end and every gating check passed.\n'
    printf '# TYPE domainscope_search_probe_success gauge\n'
    printf 'domainscope_search_probe_success{target="%s"} %d\n' "${target}" "${success}"
    printf '# HELP domainscope_search_probe_failed_checks Gating checks of the last search probe that failed (a probe error counts as one).\n'
    printf '# TYPE domainscope_search_probe_failed_checks gauge\n'
    printf 'domainscope_search_probe_failed_checks{target="%s"} %d\n' "${target}" "${failed}"
    printf '# HELP domainscope_search_probe_checks_total Gating checks the last search probe ran.\n'
    printf '# TYPE domainscope_search_probe_checks_total gauge\n'
    printf 'domainscope_search_probe_checks_total{target="%s"} %d\n' "${target}" "${checks}"
    printf '# HELP domainscope_search_probe_known_failing_checks Golden queries gated known-failing the last search probe ran (never fail it).\n'
    printf '# TYPE domainscope_search_probe_known_failing_checks gauge\n'
    printf 'domainscope_search_probe_known_failing_checks{target="%s"} %d\n' "${target}" "${known_checks}"
    printf '# HELP domainscope_search_probe_known_failing_failed_checks Known-failing golden queries that still failed in the last search probe.\n'
    printf '# TYPE domainscope_search_probe_known_failing_failed_checks gauge\n'
    printf 'domainscope_search_probe_known_failing_failed_checks{target="%s"} %d\n' "${target}" "${known_failures}"
    printf '# HELP domainscope_search_probe_duration_seconds Wall time of the last search probe.\n'
    printf '# TYPE domainscope_search_probe_duration_seconds gauge\n'
    printf 'domainscope_search_probe_duration_seconds{target="%s"} %d\n' "${target}" "$((end - START_EPOCH))"
    printf '# HELP domainscope_search_probe_last_run_timestamp_seconds Unix time the last search probe ended.\n'
    printf '# TYPE domainscope_search_probe_last_run_timestamp_seconds gauge\n'
    printf 'domainscope_search_probe_last_run_timestamp_seconds{target="%s"} %d\n' "${target}" "${end}"
  } > "${tmp}" && chmod 0644 "${tmp}" && mv -f "${tmp}" "${METRICS_FILE}"
}

# on_exit: every way out of the script ends here. A run that stopped on an error (set -e, a crashed helper) is a failure,
# never "passed", and the metrics say so.
on_exit() {
  local status=$?
  trap - EXIT
  if [[ "${status}" -ne 0 && "${status}" -ne 64 && "${failures}" -eq 0 ]]; then
    echo "Search probe FAILED: the probe itself stopped with exit status ${status}" >&2
  fi
  if ! write_metrics "${status}"; then
    echo "search-probe: could not write metrics to ${METRICS_FILE}" >&2
    rm -f "$(dirname "${METRICS_FILE}")/.$(basename "${METRICS_FILE}").tmp.$$"
    [[ "${status}" -eq 0 ]] && status=1
  fi
  exit "${status}"
}
trap on_exit EXIT

FILE="${SEARCH_PROBE_FILE:-${ROOT_DIR}/scripts/search-golden-queries.tsv}"
MIN_OVERRIDE="${SEARCH_PROBE_MIN_OVERRIDE:-}"
UNCACHED="${SEARCH_PROBE_UNCACHED:-1}"
UNCACHED_MIN="${SEARCH_PROBE_UNCACHED_MIN:-1}"
MARKET_MIN="${SEARCH_PROBE_MARKET_MIN:-5}"
TIMEOUT="${SEARCH_PROBE_TIMEOUT:-60}"
ATTEMPTS="${SEARCH_PROBE_ATTEMPTS:-2}"
SLEEP="${SEARCH_PROBE_SLEEP:-1}"
for n in "${MARKETS}" "${UNCACHED_MIN}" "${MARKET_MIN}" "${TIMEOUT}" "${ATTEMPTS}" "${SLEEP}" ${MIN_OVERRIDE:+"${MIN_OVERRIDE}"}; do
  [[ "${n}" =~ ^[0-9]+$ ]] || { echo "search-probe: counts, seconds and tries must be whole numbers (got '${n}')" >&2; exit 64; }
done
[[ -f "${FILE}" ]] || { echo "search-probe: ${FILE} does not exist" >&2; exit 64; }
[[ "${ATTEMPTS}" -ge 1 ]] || ATTEMPTS=1

pass() { printf '  [PASS] %s\n' "$*"; }
fail() { printf '  [FAIL] %s\n' "$*"; failures=$((failures + 1)); }
# broken: a check that could not even run (a bad row, a market picker that failed) is a failed gating check too.
broken() { checks=$((checks + 1)); fail "$@"; }

# summarize <route> <body-file> prints "<rows> <no_results_reason or ->" for a search answer, "invalid -" when it is not one.
summarize() {
  python3 - "$1" "$2" <<'PY'
import json, sys
route, path = sys.argv[1], sys.argv[2]
try:
    body = json.load(open(path, encoding="utf-8"))
    data = body.get("data", body) if isinstance(body, dict) else body
    if route == "smart":
        rows = data.get("results") or []
        reason = data.get("no_results_reason") or "-"
    else:
        rows = data if isinstance(data, list) else (data.get("results") or [])
        reason = "-"
    print(len(rows), reason)
except Exception:
    print("invalid -")
PY
}

urlencode() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1"; }

# probe <route> <min> <query> [known-failing]: one golden check, with retries. A known-failing check is reported, and counted
# apart, but never fails the probe.
probe() {
  local route="$1" min="$2" query="$3" known="${4:-}" url limit body code summary rows reason try
  if [[ -n "${known}" ]]; then known_checks=$((known_checks + 1)); else checks=$((checks + 1)); fi
  limit=40; [[ "${route}" == semantic ]] && limit=20
  url="${BASE_URL}/api/v1/search/${route}?q=$(urlencode "${query}")&limit=${limit}"
  body="$(mktemp)"
  for ((try = 1; try <= ATTEMPTS; try++)); do
    code="$(curl -sS -o "${body}" -w '%{http_code}' --max-time "${TIMEOUT}" "${url}" 2>/dev/null || true)"
    code="${code:-000}"
    summary="$(summarize "${route}" "${body}")"
    rows="${summary%% *}"; reason="${summary#* }"
    if [[ "${code}" == 200 && "${rows}" =~ ^[0-9]+$ && "${rows}" -ge "${min}" && "${reason}" != catalog_matches_not_searchable ]]; then
      rm -f "${body}"
      if [[ -n "${known}" ]]; then
        pass "${route} \"${query}\" -> ${rows} rows (min ${min}) [known-failing passes now: gate it scheduled again]"
      else
        pass "${route} \"${query}\" -> ${rows} rows (min ${min})"
      fi
      return 0
    fi
    [[ "${try}" -lt "${ATTEMPTS}" ]] && sleep "$((SLEEP > 0 ? SLEEP * 5 : 0))"
  done
  rm -f "${body}"
  [[ "${reason}" == - ]] && reason=""
  if [[ -n "${known}" ]]; then
    printf '  [KNOWN-FAILING] %s\n' "${route} \"${query}\" -> HTTP ${code}, ${rows} rows (min ${min})${reason:+, no_results_reason ${reason}}"
    known_failures=$((known_failures + 1))
    return 0
  fi
  fail "${route} \"${query}\" -> HTTP ${code}, ${rows} rows (min ${min})${reason:+, no_results_reason ${reason}}"
}

echo "Search probe ${BASE_URL} (gate: ${GATE}, markets: ${MARKETS})"
if [[ "${UNCACHED}" != 0 ]]; then
  # A query no one has asked before, so the API must embed it (search_cache cannot answer).
  probe semantic "${UNCACHED_MIN}" "logistics software companies probe $(date -u +%Y%m%d%H%M%S)$$"
  sleep "${SLEEP}"
fi
while IFS=$'\t' read -r route min gate query; do
  [[ -z "${route}" || "${route}" == \#* ]] && continue
  case "${gate}" in
    deploy|scheduled|known-failing) ;;
    *) broken "bad gate '${gate}' in ${FILE} (deploy, scheduled or known-failing)"; continue ;;
  esac
  [[ "${GATE}" == all || "${gate}" == "${GATE}" ]] || continue
  [[ "${route}" == smart || "${route}" == semantic ]] || { broken "bad route '${route}' in ${FILE}"; continue; }
  [[ "${min}" =~ ^[0-9]+$ && -n "${query}" ]] || { broken "bad row in ${FILE}: minimum '${min}', query '${query}'"; continue; }
  if [[ "${gate}" == known-failing ]]; then
    probe "${route}" "${MIN_OVERRIDE:-${min}}" "${query}" known-failing
  else
    probe "${route}" "${MIN_OVERRIDE:-${min}}" "${query}"
  fi
  sleep "${SLEEP}"
done < "${FILE}"

if [[ "${MARKETS}" -gt 0 ]]; then
  # The brief of a market cell's "full list" link, as the niche map sends it to smart search (frontend
  # features/market-cells/marketCellsModel.ts marketCellNicheBrief + features/niche-map/nicheMapBrief.ts nicheMapSearchText).
  # The cells are picked first, into a file: a picker that fails (a missing or changed catalog or snapshot) is a failed
  # check, not a traceback the loop never sees.
  cells="$(mktemp)"; pick_err="$(mktemp)"
  if python3 - "${ROOT_DIR}" "${MARKETS}" > "${cells}" 2> "${pick_err}" <<'PY'
import json, os, random, sys
root, n = sys.argv[1], int(sys.argv[2])
catalog = json.load(open(os.path.join(root, "src/internal/marketcell/catalog.json"), encoding="utf-8"))
snapshot = json.load(open(os.path.join(root, "frontend/src/features/market-cells/marketCells.snapshot.json"), encoding="utf-8"))
floor = catalog.get("min_private_companies", 0)
cells = []
for country in catalog["countries"]:
    for sector in catalog["sectors"]:
        count = snapshot["counts"].get(country["slug"], {}).get(sector["slug"], 0)
        if count >= floor:
            brief, place = sector["label"].strip(), country["name"].strip()
            text = brief if place.lower() in brief.lower() else f"{brief} in {place}"
            cells.append((count, text))
for count, text in random.sample(cells, min(n, len(cells))):
    print(f"{count}\t{text}")
PY
  then
    picked=0
    while IFS=$'\t' read -r count query; do
      if [[ ! "${count}" =~ ^[0-9]+$ || -z "${query}" ]]; then
        broken "market cells: bad picked cell '${count}' '${query}'"; continue
      fi
      picked=$((picked + 1))
      min="${MARKET_MIN}"; [[ "${count}" -lt "${min}" ]] && min="${count}"
      probe smart "${min}" "${query}"
      sleep "${SLEEP}"
    done < "${cells}"
    [[ "${picked}" -gt 0 ]] || broken "market cells: no published cell to probe (catalog or snapshot empty)"
  else
    broken "market cells: could not pick ${MARKETS} cells: $(tail -n 1 "${pick_err}")"
  fi
  rm -f "${cells}" "${pick_err}"
fi

[[ "${checks}" -gt 0 ]] || broken "no gating check ran (gate ${GATE}, ${FILE})"
if [[ "${known_checks}" -gt 0 ]]; then
  echo "Known-failing golden queries: ${known_failures} of ${known_checks} still fail (informational, never fail the probe)"
fi
if [[ "${failures}" -gt 0 ]]; then
  echo "Search probe FAILED: ${failures} of ${checks} check(s)"
  exit 1
fi
echo "Search probe passed: ${checks} check(s)"
