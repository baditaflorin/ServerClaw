# Configure Apache Tika

## Purpose

This runbook converges the private Apache Tika runtime from ADR 0275 and
verifies that document text and metadata extraction work on `docker-runtime-lv3`.

## Result

- `docker-runtime-lv3` runs Apache Tika from `/opt/tika`
- the service listens privately on `10.10.10.20:9998`
- `PUT /tika` returns clean plaintext when the caller requests `Accept: text/plain`
- `PUT /meta` returns metadata JSON when the caller requests `Accept: application/json`
- no public hostname or NGINX publication exists for the service

## Commands

Syntax-check the Apache Tika workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-tika
```

Converge the private runtime on `docker-runtime-lv3`:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-tika
```

Replay the guarded production live-apply path:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=tika env=production EXTRA_ARGS='-e bypass_promotion=true'
```

## Verification

Verify the version endpoint on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:9998/version", timeout=10).read().decode().strip())
PY'
```

Verify plaintext extraction:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'
import urllib.request
payload = b"<html><body><h1>Hello Tika</h1><p>Example extraction fixture.</p></body></html>"
request = urllib.request.Request(
    "http://127.0.0.1:9998/tika",
    data=payload,
    method="PUT",
    headers={"Content-Type": "text/html", "Accept": "text/plain"},
)
print(urllib.request.urlopen(request, timeout=10).read().decode().strip())
PY'
```

Verify metadata extraction:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'
import json
import urllib.request
payload = b"<html><body><h1>Hello Tika</h1><p>Example extraction fixture.</p></body></html>"
request = urllib.request.Request(
    "http://127.0.0.1:9998/meta",
    data=payload,
    method="PUT",
    headers={"Content-Type": "text/html", "Accept": "application/json"},
)
metadata = json.loads(urllib.request.urlopen(request, timeout=10).read().decode())
print(metadata["Content-Type"])
print(metadata["X-TIKA:Parsed-By"])
PY'
```

## Operating Notes

- Keep Apache Tika private to the docker-runtime VM and the approved internal
  guest network; do not publish it through the public edge or the API gateway.
- The repo-managed runtime intentionally uses the standard Apache Tika image,
  not the `-full` image, so OCR remains outside the live contract from ADR 0275.
- Future callers must request `Accept: text/plain` on `/tika` if they want clean
  extracted text rather than the XHTML serialization.
