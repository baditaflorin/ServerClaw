#!/usr/bin/env bash
# app-drift.sh — are the side-project apps on the latest origin/main? (read-only)
#
# For each row of apps.tsv: running image tag/revision label vs the repo's main HEAD.
# Sha-tagged apps are compared exactly. Apps still on an untagged :latest cannot be
# compared exactly, so the image build time is compared with the last commit time
# ("likely current" / "STALE").
# A row's optional 'path filter' limits which commits count (e.g. a backend that only
# changes with api-server/).
# Needs: gh (authenticated), ssh access to 0docker_bastion.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
list=$(grep -vE '^\s*(#|$)' "$here/apps.tsv" | cut -f1 | paste -sd' ' -)
remote=$(ssh -o BatchMode=yes -o ConnectTimeout=20 0docker_bastion "ssh -o BatchMode=yes ubuntu_vm@10.10.10.20 'for c in $list; do i=\$(sudo docker inspect \$c --format \"{{.Config.Image}}|{{.Image}}\" 2>/dev/null) || continue; id=\${i#*|}; echo \"\$c|\${i%%|*}|\$(sudo docker image inspect \$id --format \"{{.Created}}|{{index .Config.Labels \\\"org.opencontainers.image.revision\\\"}}\" | cut -c1-19,20-)\"; done'")
printf '%-38s %-9s %-9s %s\n' CONTAINER RUNNING MAIN STATUS
while IFS=$'\t' read -r c repo br dir pathf note; do
  case "$c" in '#'*|'') continue;; esac
  line=$(grep "^$c|" <<<"$remote") || { printf '%-38s %-9s %-9s %s\n' "$c" - - "not running"; continue; }
  img=$(cut -d'|' -f2 <<<"$line"); created=$(cut -d'|' -f3 <<<"$line"); rev=$(cut -d'|' -f4 <<<"$line")
  tag=${img##*:}
  if [ "$pathf" != "-" ]; then head=$(gh api "repos/$repo/commits?sha=$br&path=$pathf&per_page=1" --jq '.[0]|.sha[0:7]+"|"+.commit.committer.date' 2>/dev/null </dev/null); else head=$(gh api "repos/$repo/commits/$br" --jq '.sha[0:7]+"|"+.commit.committer.date' 2>/dev/null </dev/null); fi || { printf '%-38s %-9s %-9s %s\n' "$c" "$tag" "?" "cannot read $repo"; continue; }
  hs=${head%%|*}; hd=${head#*|}
  if [[ "$img" == *@sha256:* ]]; then
    tag="digest"; st="digest-pinned: image time cannot be compared to commits (see note)"
  elif [[ "$tag" =~ ^[0-9a-f]{7}$ ]] || [[ -n "$rev" ]]; then
    r=${rev:-$tag}; r=${r:0:7}
    if [ "$r" = "$hs" ]; then st="current"; else st="BEHIND (running $r)"; fi
  else
    if [[ "$created" > "${hd%Z}" ]]; then st="likely current (image built after last commit)"; else st="STALE (image older than last commit $hd)"; fi
  fi
  printf '%-38s %-9s %-9s %s %s\n' "$c" "$tag" "$hs" "$st" "$([ "$note" != "-" ] && echo "[$note]")"
done < "$here/apps.tsv"
