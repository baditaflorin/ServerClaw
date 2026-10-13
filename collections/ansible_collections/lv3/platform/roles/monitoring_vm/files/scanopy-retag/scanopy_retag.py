#!/usr/bin/env python3
"""scanopy_retag - keep every Docker bridge subnet in Scanopy tagged `docker-bridge`.

Why: Scanopy's topology hides subnets by tag (options.local.tag_filter.hidden_subnet_tag_ids).
Discovery creates new Docker networks untagged, so without this they reappear in the view.

Safety properties
  * additive only: it adds one tag to subnets of type DockerBridge; it never removes tags,
    never touches other entity types, never deletes anything
  * refuses to run if the tag does not exist (it will not create it) or if more than
    MAX_PER_RUN subnets would be tagged in one run (runaway guard); that run is a failure
  * stdlib only; the API key is read from a root-only file and never logged
  * writes node_exporter textfile metrics scanopy_retag_*

Usage
  scanopy_retag.py            # tag untagged DockerBridge subnets
  scanopy_retag.py --dry-run  # report only, no writes
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

CONF = {
    "url": os.environ.get("SCANOPY_URL", "http://10.10.10.1:60072"),
    "key_file": os.environ.get("SCANOPY_KEY_FILE", "/etc/scanopy-retag/api-key"),
    "tag_name": os.environ.get("RETAG_TAG_NAME", "docker-bridge"),
    "textfile": os.environ.get("RETAG_TEXTFILE", "/var/lib/prometheus/node-exporter/scanopy_retag.prom"),
    "max_per_run": int(os.environ.get("RETAG_MAX_PER_RUN", "500")),
}
BATCH = 100


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def call(key, method, path, body=None):
    req = urllib.request.Request(
        CONF["url"] + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read(16 << 20))
    if not out.get("success"):
        raise RuntimeError(f"{method} {path}: success=false")
    return out


def get_all(key, path):
    rows, offset = [], 0
    while True:
        page = call(key, "GET", f"{path}?limit=1000&offset={offset}")
        rows += page.get("data") or []
        if not page.get("meta", {}).get("pagination", {}).get("has_more"):
            return rows
        if not page.get("data"):
            raise RuntimeError(f"{path}: empty page with has_more")
        offset += 1000
        if offset > 100000:
            raise RuntimeError(f"{path}: safety cap")


def write_metrics(ok, tagged_now, untagged_found, total_docker, dry_run):
    if dry_run:
        return
    now = int(time.time())
    lines = [
        "# HELP scanopy_retag_last_attempt_success 1 if the last run completed without error",
        "# TYPE scanopy_retag_last_attempt_success gauge",
        f"scanopy_retag_last_attempt_success {1 if ok else 0}",
        f"scanopy_retag_last_attempt_timestamp_seconds {now}",
    ]
    if ok:
        lines += [
            f"scanopy_retag_last_success_timestamp_seconds {now}",
            f"scanopy_retag_docker_bridge_subnets {total_docker}",
            f"scanopy_retag_untagged_found {untagged_found}",
            f"scanopy_retag_tagged_this_run {tagged_now}",
        ]
    tmp = CONF["textfile"] + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, CONF["textfile"])
    except OSError as e:
        log(f"warning: could not write metrics: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ok, tagged_now, untagged, total = False, 0, 0, 0
    try:
        try:
            key = open(CONF["key_file"]).read().strip()
        except OSError as e:
            raise RuntimeError(f"no API key file ({CONF['key_file']}): {e.strerror}")
        if not key:
            raise RuntimeError("API key file is empty")
        tags = [t for t in get_all(key, "/api/v1/tags") if t["name"] == CONF["tag_name"]]
        if len(tags) != 1:
            raise RuntimeError(f"expected exactly one tag named {CONF['tag_name']!r}, found {len(tags)}")
        tag_id = tags[0]["id"]
        docker = [s for s in get_all(key, "/api/v1/subnets") if s.get("subnet_type") == "DockerBridge"]
        total = len(docker)
        todo = [s for s in docker if tag_id not in (s.get("tags") or [])]
        untagged = len(todo)
        log(f"docker bridge subnets: {total}, untagged: {untagged}" + (" (dry run)" if args.dry_run else ""))
        if untagged > CONF["max_per_run"]:
            raise RuntimeError(f"{untagged} untagged subnets exceeds guard ({CONF['max_per_run']}); refusing")
        if todo and not args.dry_run:
            ids = [s["id"] for s in todo]
            for i in range(0, len(ids), BATCH):
                call(key, "POST", "/api/v1/tags/assign/bulk-add",
                     {"entity_type": "Subnet", "entity_ids": ids[i:i + BATCH], "tag_id": tag_id})
                tagged_now += len(ids[i:i + BATCH])
            for s in todo[:20]:
                log(f"tagged {s['cidr']} ({s['name']})")
        ok = True
    except (RuntimeError, urllib.error.URLError, OSError, ValueError, KeyError) as e:
        log(f"FAILED: {e}")
    write_metrics(ok, tagged_now, untagged, total, args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
