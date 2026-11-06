#!/usr/bin/env bash
# Activate a GitHub repository in a Woodpecker CI plane, optionally run one pipeline and wait for it (docs/runbooks/configure-woodpecker.md, "Activate a repository").
#
#   woodpecker_activate_repo.sh PLANE OWNER/REPO [--run BRANCH]
#
#   PLANE   ci.0mcp | ci.0exec   (both planes use a GitHub forge; verified 2026-10-30)
#
# Run it from the operator's Mac. Every Woodpecker API call is made by curl inside CT108 (ssh to the bastion, `pct exec`), where the admin token is read
# from fleet-vault by the remote shell and handed to curl on stdin (`curl -K -`): the token is never on this Mac, in a command line, in a file or in output.
# What it does, in order: GET /api/user (prints the forge it found and whether the token is admin; refuses unless the forge is GitHub), looks the repo up
# (GET /api/repos/lookup/OWNER/REPO), activates it only when the lookup says 404 (POST /api/repos?forge_remote_id=<GitHub repo id from `gh api`>), and with
# --run triggers a pipeline on BRANCH, waits for it and prints the status of every step. Already activated is a no-op with exit 0.
# Activation makes Woodpecker create a GitHub webhook whose URL carries a hook token: this script never prints the activation response or any hook field.
#
# Exit status: 0 repo is activated (and the --run pipeline succeeded); 1 anything else (refused forge, API error, pipeline not successful, timeout); 2 usage.
# Settings for tests and unusual setups: WOODPECKER_BASTION (ssh alias, default 0docker_bastion), WOODPECKER_CT (default 108), WOODPECKER_REMOTE_FV
# (default /root/bin/fv.sh), WOODPECKER_POLL_SECONDS (default 5), WOODPECKER_RUN_TIMEOUT (seconds, default 900).
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/woodpecker_activate_repo.sh PLANE OWNER/REPO [--run BRANCH]

  PLANE   ci.0mcp or ci.0exec
  --run   after activation, trigger a pipeline on BRANCH, wait for it, print each step's status

Example:
  scripts/woodpecker_activate_repo.sh ci.0mcp baditaflorin/0pipe --run main
EOF
}

BASTION=${WOODPECKER_BASTION:-0docker_bastion}
CT=${WOODPECKER_CT:-108}
REMOTE_FV=${WOODPECKER_REMOTE_FV:-/root/bin/fv.sh}
POLL_SECONDS=${WOODPECKER_POLL_SECONDS:-5}
RUN_TIMEOUT=${WOODPECKER_RUN_TIMEOUT:-900}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then usage; exit 0; fi
if [[ $# -ne 2 && $# -ne 4 ]]; then usage >&2; exit 2; fi
PLANE=$1
REPO=$2
BRANCH=
if [[ $# -eq 4 ]]; then
  if [[ $3 != "--run" ]]; then usage >&2; exit 2; fi
  BRANCH=$4
  [[ $BRANCH =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "refused: branch name has characters outside A-Za-z0-9._/-" >&2; exit 2; }
fi
[[ $REPO =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || { echo "refused: repository must look like OWNER/REPO" >&2; exit 2; }

case "$PLANE" in
  ci.0mcp)  BASE=https://ci.example.org; VAULT_ENTRY=woodpecker-ci-0mcp-api-token; PROXY=0 ;;
  ci.0exec) BASE=https://ci.0exec.com; VAULT_ENTRY=woodpecker_ci_admin_pat_for_ci_0exec_com; PROXY=1 ;;  # CT108 reaches this plane through the tailnet proxy
  *) echo "refused: unknown plane '$PLANE' (expected ci.0mcp or ci.0exec)" >&2; usage >&2; exit 2 ;;
esac

# The program that runs in CT108. Arguments: base url, vault entry, proxy flag (0/1), method, path, body, path of fv.sh.
# It prints the response body, then a last line with the HTTP status. The token lives in a shell variable and reaches curl only on stdin.
read -r -d '' REMOTE_PROGRAM <<'REMOTE' || true
set -euo pipefail
base=$1; entry=$2; proxy=$3; method=$4; path=$5; body=$6; fv=$7
if ! token=$(bash "$fv" raw "$entry" 2>/dev/null </dev/null) || [ -z "$token" ]; then
  echo "could not read vault entry $entry" >&2
  exit 3
fi
[ "$proxy" = 1 ] && export https_proxy=http://127.0.0.1:1056
args=(-sS --max-time 60 -X "$method" -H 'Content-Type: application/json' -w '\n%{http_code}')
[ -n "$body" ] && args+=(-d "$body")
printf 'header = "Authorization: Bearer %s"\n' "$token" | curl -K - "${args[@]}" "$base$path"
REMOTE

# api METHOD PATH [BODY]: sets API_CODE and API_BODY; fails (exit 1) when the call could not be made at all.
API_CODE=
API_BODY=
api() {
  local out rc=0 remote_args
  remote_args=$(printf '%q ' "$BASE" "$VAULT_ENTRY" "$PROXY" "$1" "$2" "${3:-}" "$REMOTE_FV")
  out=$(printf '%s\n' "$REMOTE_PROGRAM" | ssh -o BatchMode=yes -o ConnectTimeout=20 "$BASTION" "pct exec $CT -- bash -s -- $remote_args") || rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "the call $1 ${2%%\?*} on $PLANE failed (ssh/curl exit $rc)" >&2
    exit 1
  fi
  API_CODE=${out##*$'\n'}
  API_BODY=${out%$'\n'*}
}

# json_field NAME: print one top-level scalar of the JSON on stdin (empty when absent or not JSON). Never prints anything else.
json_field() {
  python3 -c 'import json,sys
try:
    v = json.load(sys.stdin).get(sys.argv[1], "")
except Exception:
    v = ""
print("" if v is None else v)' "$1"
}

# 1. Ask the server which forge it uses.
api GET /api/user
if [[ $API_CODE != 200 ]]; then echo "GET /api/user on $PLANE answered HTTP $API_CODE; the token is not accepted" >&2; exit 1; fi
avatar=$(printf '%s' "$API_BODY" | json_field avatar_url)
admin=$(printf '%s' "$API_BODY" | json_field admin)
if [[ $avatar == https://avatars.githubusercontent.com/* ]]; then forge=github; else forge=unknown; fi
echo "$PLANE: forge=$forge admin=${admin:-unknown}"
if [[ $forge != github ]]; then
  echo "refused: $PLANE does not look like a GitHub forge (the user's avatar is not on avatars.githubusercontent.com); this script only handles GitHub" >&2
  exit 1
fi

# 2. Look the repository up; 404 means not activated.
api GET "/api/repos/lookup/$REPO"
case "$API_CODE" in
  200)
    forge_url=$(printf '%s' "$API_BODY" | json_field forge_url)
    if [[ -n $forge_url && $forge_url != https://github.com/* ]]; then
      echo "refused: $REPO on $PLANE belongs to a forge that is not GitHub" >&2
      exit 1
    fi
    echo "$REPO is already activated on $PLANE (Woodpecker repo id $(printf '%s' "$API_BODY" | json_field id)); nothing to do"
    ;;
  404)
    command -v gh >/dev/null || { echo "gh is needed to read the GitHub repository id" >&2; exit 1; }
    remote_id=$(gh api "repos/$REPO" --jq .id) || { echo "gh could not read repos/$REPO on GitHub" >&2; exit 1; }
    [[ $remote_id =~ ^[0-9]+$ ]] || { echo "gh did not return a numeric repository id for $REPO" >&2; exit 1; }
    api POST "/api/repos?forge_remote_id=$remote_id"
    if [[ $API_CODE != 200 ]]; then echo "activation of $REPO on $PLANE answered HTTP $API_CODE (response not shown: it carries hook fields)" >&2; exit 1; fi
    api GET "/api/repos/lookup/$REPO"
    [[ $API_CODE == 200 ]] || { echo "activated, but the follow-up lookup answered HTTP $API_CODE" >&2; exit 1; }
    echo "activated $REPO on $PLANE (Woodpecker repo id $(printf '%s' "$API_BODY" | json_field id)); the GitHub webhook was created by Woodpecker"
    ;;
  *)
    echo "lookup of $REPO on $PLANE answered HTTP $API_CODE" >&2
    exit 1
    ;;
esac
[[ -n $BRANCH ]] || exit 0

# 3. Optionally run a pipeline and wait for it.
repo_id=$(printf '%s' "$API_BODY" | json_field id)
[[ $repo_id =~ ^[0-9]+$ ]] || { echo "no numeric Woodpecker repo id in the lookup answer" >&2; exit 1; }
api POST "/api/repos/$repo_id/pipelines" "{\"branch\":\"$BRANCH\"}"
if [[ $API_CODE != 200 ]]; then echo "triggering a pipeline on $BRANCH answered HTTP $API_CODE (does the branch carry a Woodpecker file?)" >&2; exit 1; fi
number=$(printf '%s' "$API_BODY" | json_field number)
[[ $number =~ ^[0-9]+$ ]] || { echo "no pipeline number in the trigger answer" >&2; exit 1; }
echo "pipeline #$number started on $BRANCH; waiting (up to ${RUN_TIMEOUT}s)"

deadline=$((SECONDS + RUN_TIMEOUT))
status=
while :; do
  api GET "/api/repos/$repo_id/pipelines/$number"
  [[ $API_CODE == 200 ]] || { echo "reading pipeline #$number answered HTTP $API_CODE" >&2; exit 1; }
  status=$(printf '%s' "$API_BODY" | json_field status)
  case "$status" in
    success|failure|killed|error|declined|skipped) break ;;
  esac
  if (( SECONDS >= deadline )); then echo "pipeline #$number still '$status' after ${RUN_TIMEOUT}s; it keeps running on the server" >&2; exit 1; fi
  sleep "$POLL_SECONDS"
done

printf '%s' "$API_BODY" | python3 -c 'import json,sys
d = json.load(sys.stdin)
for w in d.get("workflows") or []:
    print("  workflow %s: %s" % (w.get("name", "?"), w.get("state", "?")))
    for s in w.get("children") or []:
        print("    step %s: %s" % (s.get("name", "?"), s.get("state", "?")))'
echo "pipeline #$number: $status"
[[ $status == success ]]
