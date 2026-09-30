#!/usr/bin/env bash

set -euo pipefail

TRIVY_IMAGE="${TRIVY_IMAGE:-docker.io/aquasec/trivy:0.63.0}"
TRIVY_CACHE_DIR="${TRIVY_CACHE_DIR:-/var/tmp/lv3-trivy-cache}"
TRIVY_SKIP_DB_UPDATE="${TRIVY_SKIP_DB_UPDATE:-false}"

mkdir -p "$TRIVY_CACHE_DIR"

running_containers=()
while IFS= read -r container_id; do
  [[ -n "$container_id" ]] && running_containers+=("$container_id")
done < <(docker ps -q | awk 'NF' | sort -u)
if [[ ${#running_containers[@]} -eq 0 ]]; then
  echo "[]"
  exit 0
fi

# A running container may still use an image after its original tag has been
# removed. Resolve and scan Docker's immutable local image ID so Trivy does not
# mistake that case for a remote image pull (which can fail on registry limits).
scan_image_ids=()
display_images=()
for container_id in "${running_containers[@]}"; do
  metadata="$(docker inspect --format '{{.Config.Image}}|{{.Image}}' "$container_id")"
  display_image="${metadata%%|*}"
  image_id="${metadata#*|}"
  if [[ -z "$display_image" || -z "$image_id" || "$metadata" == "$image_id" ]]; then
    echo "unable to resolve a local image ID for a running container" >&2
    exit 1
  fi

  already_seen=false
  for existing_image_id in "${scan_image_ids[@]}"; do
    if [[ "$existing_image_id" == "$image_id" ]]; then
      already_seen=true
      break
    fi
  done
  if [[ "$already_seen" == false ]]; then
    if ! docker image inspect "$image_id" >/dev/null 2>&1; then
      echo "running container image is unavailable locally; refusing an implicit registry pull" >&2
      exit 1
    fi
    scan_image_ids+=("$image_id")
    display_images+=("$display_image")
  fi
done

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

extra_flags=()
if [[ "$TRIVY_SKIP_DB_UPDATE" == "true" ]]; then
  extra_flags+=(--skip-db-update)
fi

for image_id in "${scan_image_ids[@]}"; do
  safe_name="$(printf '%s' "$image_id" | tr '/:@' '___')"
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
    "$image_id" >"$tmpdir/$safe_name.json"
done

python3 - "$tmpdir" "${#scan_image_ids[@]}" "${scan_image_ids[@]}" "${display_images[@]}" <<'PY'
import json
import sys
from pathlib import Path

tmpdir = Path(sys.argv[1])
count = int(sys.argv[2])
image_ids = sys.argv[3 : 3 + count]
images = sys.argv[3 + count :]
payload = []
for image_id, image in zip(image_ids, images):
    safe_name = image_id.translate(str.maketrans({"/": "_", ":": "_", "@": "_"}))
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
            "image_id": image_id,
            "artifact_name": result.get("ArtifactName", image),
            "severity_counts": severity_counts,
            "vulnerabilities": vulnerabilities,
        }
    )
print(json.dumps(payload, indent=2, sort_keys=True))
PY
