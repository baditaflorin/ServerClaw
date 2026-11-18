#!/bin/sh
# Build the reviewed endpoint-discovery patch on an approved Linux builder.
# Usage: build.sh /absolute/new-build-directory [1.104.7|1.104.5|1.102.4]
set -eu
build_dir=${1:?supply a new absolute build directory}
release=${2:-1.104.7}
case "$build_dir" in /*) ;; *) echo 'build directory must be absolute' >&2; exit 2;; esac
[ ! -e "$build_dir" ] || { echo 'build directory already exists; refusing to modify it' >&2; exit 2; }
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
metadata=$(python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=d["releases"].get(sys.argv[2]); assert r; hook=r.get("sender_hook","sender-hook.patch"); hook_sha=r.get("sender_hook_sha256",d["sender_hook_sha256"]); assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.patch",hook) and re.fullmatch(r"[0-9a-f]{40}",r["source_commit"]) and all(re.fullmatch(r"[0-9a-f]{64}",x) for x in (r["static_binary_sha256"],d["patch_sha256"],hook_sha,d["sender_source_sha256"])) and re.fullmatch(r"golang@sha256:[0-9a-f]{64}",d["go_image"]); print(r["source_commit"],r["static_binary_sha256"],d["patch_sha256"],d["go_image"],hook_sha,d["sender_source_sha256"],hook)' "$here/release-manifest.json" "$release") || { echo 'invalid release manifest' >&2; exit 1; }
set -f
# The manifest parser emits exactly seven space-separated, validated tokens.
# shellcheck disable=SC2086
set -- $metadata
commit=$1; expected=$2; patch_sha=$3; image=$4; sender_hook_sha=$5; sender_source_sha=$6; sender_hook=$7
[ "$(sha256sum "$here/upstream-17762.patch" | awk '{print $1}')" = "$patch_sha" ] || { echo 'upstream patch checksum mismatch' >&2; exit 1; }
[ "$(sha256sum "$here/$sender_hook" | awk '{print $1}')" = "$sender_hook_sha" ] || { echo 'sender hook checksum mismatch' >&2; exit 1; }
[ "$(sha256sum "$here/private_discovery_filter.go" | awk '{print $1}')" = "$sender_source_sha" ] || { echo 'sender filter checksum mismatch' >&2; exit 1; }
mkdir -p "$build_dir/cache/build" "$build_dir/cache/mod" "$build_dir/out"
git clone --depth 1 --branch "v$release" https://github.com/tailscale/tailscale.git "$build_dir/upstream"
[ "$(git -C "$build_dir/upstream" rev-parse HEAD)" = "$commit" ] || { echo 'upstream commit mismatch' >&2; exit 1; }
git -C "$build_dir/upstream" apply --unidiff-zero --check "$here/upstream-17762.patch"
git -C "$build_dir/upstream" apply --unidiff-zero "$here/upstream-17762.patch"
git -C "$build_dir/upstream" apply --unidiff-zero --check "$here/$sender_hook"
git -C "$build_dir/upstream" apply --unidiff-zero "$here/$sender_hook"
cp "$here/private_discovery_filter.go" "$here/private_discovery_filter_test.go" "$build_dir/upstream/wgengine/magicsock/"
cp "$here/endpoint_filter_test.go" "$build_dir/upstream/net/netmon/endpoint_filter_local_test.go"
docker run --rm --cpus 4 --memory 6g --user "$(id -u):$(id -g)" \
  -v "$build_dir:/work" -w /work/upstream -e CGO_ENABLED=0 -e GOCACHE=/work/cache/build -e GOMODCACHE=/work/cache/mod \
  "$image" sh -c 'set -eu; [ "$(go version)" = "go version go1.27.4 linux/amd64" ]; go test ./net/netmon; go test ./wgengine/magicsock -run "Test(SuppressOffLinkPrivateDisco|OffLinkDiscoveryStopsBeforeSocketWrite)$" -count=1; ./build_dist.sh -o /work/out/tailscaled-filtered ./cmd/tailscaled; if ldd /work/out/tailscaled-filtered >/dev/null 2>&1; then echo "expected a static binary" >&2; exit 1; fi; /work/out/tailscaled-filtered --version; sha256sum /work/out/tailscaled-filtered'
[ "$(sha256sum "$build_dir/out/tailscaled-filtered" | awk '{print $1}')" = "$expected" ] || { echo 'built artifact checksum differs from the reviewed build' >&2; exit 1; }
