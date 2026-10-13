#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 10 ]]; then
  echo "usage: build_remote.sh IMAGE REGISTRY PROJECT USERNAME TAG SOURCE_REF SOURCE_COMMIT SOURCE_REPOSITORY PATCH DOCKERFILE" >&2
  exit 2
fi

image_id="$1"
registry="$2"
project="$3"
username="$4"
tag="$5"
source_ref="$6"
source_commit="$7"
source_repository="$8"
source_patch="$9"
dockerfile="${10}"
workspace="${LV3_REMOTE_WORKSPACE_ROOT:-$PWD}"

case "$image_id" in
  outline|glitchtip|minio) ;;
  *) echo "unsupported patched runtime image: $image_id" >&2; exit 2 ;;
esac
[[ "$registry" =~ ^[A-Za-z0-9.-]+(:[0-9]+)?$ ]] || { echo "invalid registry host" >&2; exit 2; }
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid source commit" >&2; exit 2; }

umask 077
docker_config="$(mktemp -d "${TMPDIR:-/tmp}/patched-image-auth.XXXXXX")"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/patched-image-build.XXXXXX")"
cleanup() {
  docker --config "$docker_config" logout "$registry" >/dev/null 2>&1 || true
  rm -rf -- "$docker_config" "$work_dir"
}
trap cleanup EXIT

docker --config "$docker_config" login --username "$username" --password-stdin "$registry"
git clone --quiet --depth 1 --branch "$source_ref" "$source_repository" "$work_dir/source"
actual_commit="$(git -C "$work_dir/source" rev-parse HEAD)"
if [[ "$actual_commit" != "$source_commit" ]]; then
  echo "pinned source ref moved: expected $source_commit, received $actual_commit" >&2
  exit 3
fi

if [[ -n "$source_patch" ]]; then
  git -C "$work_dir/source" apply --unidiff-zero --check "$workspace/$source_patch"
  git -C "$work_dir/source" apply --unidiff-zero "$workspace/$source_patch"
fi

image_ref="$registry/$project/$image_id:$tag"
metadata_file="$work_dir/build-metadata.json"
dockerfile_path="$workspace/$dockerfile"

case "$image_id" in
  outline)
    docker buildx build \
      --platform linux/amd64 \
      --file "$dockerfile_path" \
      --build-arg "SOURCE_REVISION=$source_commit" \
      --tag "$image_ref" \
      --metadata-file "$metadata_file" \
      --push \
      "$work_dir/source"
    ;;
  glitchtip)
    docker buildx build \
      --platform linux/amd64 \
      --file "$work_dir/source/Dockerfile" \
      --build-arg IS_CI=True \
      --build-arg "GLITCHTIP_VERSION=${source_ref#v}" \
      --build-arg COLLECT_STATIC=1 \
      --tag "$image_ref" \
      --metadata-file "$metadata_file" \
      --push \
      "$work_dir/source"
    ;;
  minio)
    docker buildx build \
      --platform linux/amd64 \
      --file "$dockerfile_path" \
      --build-arg MINIO_VERSION=2025-10-15T17-29-55Z \
      --build-arg "MINIO_COMMIT=$source_commit" \
      --tag "$image_ref" \
      --metadata-file "$metadata_file" \
      --push \
      "$work_dir/source"
    ;;
esac

digest="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["containerimage.digest"])' "$metadata_file")"
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "build did not return an immutable image digest" >&2; exit 4; }
printf 'PATCHED_IMAGE_RESULT image=%s digest=%s\n' "$image_id" "$digest"
