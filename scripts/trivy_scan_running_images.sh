#!/usr/bin/env bash

set -euo pipefail

TRIVY_IMAGE="${TRIVY_IMAGE:-docker.io/aquasec/trivy:0.63.0}"
TRIVY_CACHE_DIR="${TRIVY_CACHE_DIR:-/var/tmp/lv3-trivy-cache}"
TRIVY_SKIP_DB_UPDATE="${TRIVY_SKIP_DB_UPDATE:-false}"

mkdir -p "$TRIVY_CACHE_DIR"

mapfile -t runtime_images < <(docker ps --format '{{.Image}}' | awk 'NF' | sort -u)
if [[ ${#runtime_images[@]} -eq 0 ]]; then
  echo "[]"
  exit 0
fi

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

extra_flags=()
if [[ "$TRIVY_SKIP_DB_UPDATE" == "true" ]]; then
  extra_flags+=(--skip-db-update)
fi

for image in "${runtime_images[@]}"; do
  safe_name="$(printf '%s' "$image" | tr '/:@' '___')"
  docker run \
    --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$TRIVY_CACHE_DIR:/root/.cache/trivy" \
    "$TRIVY_IMAGE" \
    image \
    --quiet \
    --format json \
    --scanners vuln \
    --severity HIGH,CRITICAL \
    "${extra_flags[@]}" \
    "$image" >"$tmpdir/$safe_name.json"
done

python3 - "$tmpdir" "${runtime_images[@]}" <<'PY'
import json
import sys
from pathlib import Path

tmpdir = Path(sys.argv[1])
images = sys.argv[2:]
payload = []
for image in images:
    safe_name = image.translate(str.maketrans({"/": "_", ":": "_", "@": "_"}))
    result = json.loads((tmpdir / f"{safe_name}.json").read_text(encoding="utf-8"))
    vulnerabilities = []
    severity_counts = {"HIGH": 0, "CRITICAL": 0}
    for record in result.get("Results", []):
        for vulnerability in record.get("Vulnerabilities") or []:
            severity = str(vulnerability.get("Severity", "")).upper()
            if severity not in severity_counts:
                continue
            severity_counts[severity] += 1
            vulnerabilities.append(
                {
                    "target": record.get("Target") or result.get("ArtifactName") or image,
                    "class": record.get("Class", ""),
                    "package": vulnerability.get("PkgName", ""),
                    "installed": vulnerability.get("InstalledVersion", ""),
                    "fixed_in": vulnerability.get("FixedVersion", ""),
                    "severity": severity,
                    "cve_id": vulnerability.get("VulnerabilityID", ""),
                    "title": vulnerability.get("Title", ""),
                }
            )
    payload.append(
        {
            "image": image,
            "artifact_name": result.get("ArtifactName", image),
            "severity_counts": severity_counts,
            "vulnerabilities": vulnerabilities,
        }
    )
print(json.dumps(payload, indent=2, sort_keys=True))
PY
