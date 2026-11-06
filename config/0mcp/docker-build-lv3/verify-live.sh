#!/bin/bash
# Compare the live files of docker-build-lv3 (VM 130, ssh alias 0mcp_docker_build) with this directory. Read-only. Prints DIFF/MISSING per file and a summary; exit 1 when anything differs.
set -uo pipefail
cd "$(dirname "$0")"
bad=0
while read -r sum path; do
  live=$(ssh -n -o ConnectTimeout=15 0mcp_docker_build "sudo sha256sum /$path 2>/dev/null" | cut -d' ' -f1)
  if [ -z "$live" ]; then echo "MISSING /$path"; bad=$((bad+1))
  elif [ "$live" = "$sum" ]; then :
  else echo "DIFF /$path"; bad=$((bad+1)); fi
done < files.sha256
echo "$bad file(s) differ or are missing"
[ "$bad" = 0 ]
