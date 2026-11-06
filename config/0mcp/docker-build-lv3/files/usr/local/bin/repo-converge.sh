#!/usr/bin/env bash
# repo-converge.sh — bring long-lived checkouts to their target branch at the tip of origin.
#
# Usage:
#   repo-converge.sh [--apply] [--root DIR] [--archive DIR] [--idle-min N] [--jobs N] [--only a,b]
#   repo-converge.sh --one <repo-dir> [same flags]     (internal; one repo)
#
# Default is a DRY RUN: it only reports what it would do.
#
# Policy
#   * Every checkout under --root tracks origin/<default branch> and must be clean.
#   * A checkout may be PINNED to another branch: write the branch name into
#     <repo>/.git/fleet-pin (inside .git, so never dirty, never committed).
#     Pinned checkouts converge to origin/<pin> instead.
#   * Extra branches belong in `git worktree add` directories OUTSIDE --root
#     (e.g. /root/wt/<repo>-<purpose>). Worktrees are never touched here.
#   * Uncommitted work is NEVER discarded: a patch (tracked changes, binary-safe)
#     and a tarball of untracked files go to --archive/<repo>/<timestamp>/ and
#     are verified before anything is reset.
#   * Skipped, with a reason, and left untouched: recently modified files
#     (--idle-min, default 30: someone is working there), local commits that
#     exist on no remote, detached HEAD, index.lock present, fetch failure,
#     untracked payload over 200 MB.
set -uo pipefail
command -v timeout >/dev/null || timeout() { shift; "$@"; }

apply=0 root=/root/workspace archive=/var/lib/fleet-runner/archived-dirty idle=30 jobs=8 only="" one=""
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) apply=1 ;;
    --root) root=$2; shift ;;
    --archive) archive=$2; shift ;;
    --idle-min) idle=$2; shift ;;
    --jobs) jobs=$2; shift ;;
    --only) only=$2; shift ;;
    --one) one=$2; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '%-9s %-42s %s\n' "$1" "$(basename "$2")" "${3:-}"; }

converge_one() {
  local d=${1%/} name; name=$(basename "$d")
  [ -d "$d/.git" ] || return 0
  [ ! -e "$d/.git/index.lock" ] || { say SKIP "$d" "index.lock present"; return 0; }
  timeout 90 git -C "$d" fetch origin --quiet 2>/dev/null || { say SKIP "$d" "fetch failed"; return 0; }

  local def target pin cur dirty behind unpushed
  def=$(git -C "$d" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
  if [ -z "$def" ]; then
    for b in main master; do git -C "$d" rev-parse --verify -q "refs/remotes/origin/$b" >/dev/null && { def=$b; break; }; done
  fi
  [ -n "$def" ] || { say SKIP "$d" "no origin default branch"; return 0; }
  pin=$(cat "$d/.git/fleet-pin" 2>/dev/null | tr -d '[:space:]')
  target=${pin:-$def}
  git -C "$d" rev-parse --verify -q "refs/remotes/origin/$target" >/dev/null \
    || { say SKIP "$d" "origin/$target does not exist"; return 0; }

  cur=$(git -C "$d" symbolic-ref --short -q HEAD || echo "")
  [ -n "$cur" ] || { say SKIP "$d" "detached HEAD at $(git -C "$d" rev-parse --short HEAD) (pin a branch or fix by hand)"; return 0; }
  dirty=$(git -C "$d" status --porcelain | wc -l | tr -d ' ')
  behind=$(git -C "$d" rev-list --count "$cur..origin/$target" 2>/dev/null || echo 0)
  if [ "$cur" = "$target" ] && [ "$dirty" -eq 0 ] && [ "$behind" -eq 0 ]; then
    say OK "$d" "${pin:+pinned:}$target"; return 0
  fi

  unpushed=$(git -C "$d" rev-list --count HEAD --not --remotes 2>/dev/null || echo 0)
  [ "$unpushed" -eq 0 ] || { say SKIP "$d" "$unpushed local commit(s) on '$cur' exist on no remote — push or branch them first"; return 0; }

  if [ "$dirty" -gt 0 ]; then
    local recent
    recent=$(git -C "$d" status --porcelain -z | tr '\0' '\n' | cut -c4- | while IFS= read -r f; do
      [ -n "$f" ] && [ -e "$d/$f" ] && find "$d/$f" -maxdepth 0 -mmin "-$idle" -print -quit
    done | head -1)
    [ -z "$recent" ] || { say SKIP "$d" "files modified in the last ${idle}m (active work): ${recent#$d/}"; return 0; }
  fi

  local plan="branch=$cur→$target dirty=$dirty behind=$behind"
  if [ "$apply" -eq 0 ]; then say WOULD "$d" "$plan"; return 0; fi

  if [ "$dirty" -gt 0 ]; then
    local ts dest; ts=$(date -u +%Y%m%dT%H%M%SZ); dest="$archive/$name/$ts"
    mkdir -p "$dest" || { say FAIL "$d" "cannot create $dest"; return 0; }
    printf 'repo=%s\nbranch=%s\nhead=%s\ntarget=%s\n' "$name" "$cur" "$(git -C "$d" rev-parse HEAD)" "$target" > "$dest/meta.txt"
    git -C "$d" status --porcelain > "$dest/status.txt"
    git -C "$d" diff HEAD --binary > "$dest/tracked.patch" 2>/dev/null
    local untracked; untracked=$(git -C "$d" ls-files --others --exclude-standard | wc -l | tr -d ' ')
    if [ "$untracked" -gt 0 ]; then
      local bytes; bytes=$(git -C "$d" ls-files --others --exclude-standard -z | (cd "$d" && xargs -0 wc -c 2>/dev/null) | tail -1 | awk '{print $1}')
      [ "${bytes:-0}" -le 209715200 ] || { say SKIP "$d" "untracked payload ${bytes}B too large to archive"; return 0; }
      git -C "$d" ls-files --others --exclude-standard -z | tar -C "$d" --null -T - -czf "$dest/untracked.tgz" 2>/dev/null
      [ "$(tar -tzf "$dest/untracked.tgz" 2>/dev/null | wc -l | tr -d ' ')" -ge "$untracked" ] \
        || { say FAIL "$d" "untracked archive verification failed — NOT reset ($dest)"; return 0; }
    fi
    # verify the patch is non-empty whenever tracked files changed, and re-applies to a clean HEAD
    if git -C "$d" diff HEAD --quiet 2>/dev/null; then :; else
      [ -s "$dest/tracked.patch" ] && git -C "$d" apply --check -R "$dest/tracked.patch" 2>/dev/null \
        || { say FAIL "$d" "tracked patch verification failed — NOT reset ($dest)"; return 0; }
    fi
    plan="$plan archived→$dest"
  fi

  git -C "$d" checkout -q -f -B "$target" "origin/$target" 2>/tmp/converge.$$.err \
    || { say FAIL "$d" "checkout failed: $(tr '\n' ' ' </tmp/converge.$$.err | cut -c1-120)"; rm -f /tmp/converge.$$.err; return 0; }
  rm -f /tmp/converge.$$.err
  git -C "$d" clean -fdq
  say DONE "$d" "$plan"
}

if [ -n "$one" ]; then converge_one "$one"; exit 0; fi

[ -d "$root" ] || { echo "no such root: $root" >&2; exit 2; }
echo "== repo-converge $( [ $apply -eq 1 ] && echo APPLY || echo 'DRY-RUN') root=$root idle=${idle}m $(date -u +%FT%TZ)"
out=$(mktemp)
{
  if [ -n "$only" ]; then
    tr ',' '\n' <<<"$only" | sed "s#^#$root/#"
  else
    find "$root" -mindepth 1 -maxdepth 1 -type d
  fi | sort | xargs -P "$jobs" -n 1 "$0" \
        $( [ $apply -eq 1 ] && echo --apply ) --root "$root" --archive "$archive" --idle-min "$idle" --one 2>&1
} | tee "$out"
awk '{c[$1]++} END{printf "\n== summary:"; for(k in c) printf " %s=%d", k, c[k]; print ""}' "$out"
# Exit non-zero only when something that should have converged did not (FAIL):
# SKIPs are deliberate (active work, unpushed commits, detached HEAD) and persist.
fails=$(grep -c '^FAIL' "$out" || true)
rm -f "$out"
[ "${fails:-0}" -eq 0 ]
