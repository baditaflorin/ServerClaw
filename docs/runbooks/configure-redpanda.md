# Configure Redpanda

## Purpose

This runbook converges the private Redpanda runtime from ADR 0290 and verifies
the Kafka API, Admin API, HTTP Proxy, and Schema Registry contract end to end.

## Result

- `docker-runtime-lv3` runs Redpanda from `/opt/redpanda`
- Redpanda listens privately on `10.10.10.20:9092` for the Kafka API
- the Admin API listens privately on `10.10.10.20:9644`
- the HTTP Proxy and Schema Registry listeners are published privately on
  `10.10.10.20:8097` and `10.10.10.20:8099`
- controller-local admin and platform passwords are mirrored under `.local/redpanda/`
- OpenBao renders the runtime env at `/run/lv3-secrets/redpanda/runtime.env`
- the repo-managed smoke topic family and schema subject are reconciled on every converge

## Commands

Syntax-check the Redpanda workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-redpanda
```

Converge the Redpanda runtime directly:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-redpanda env=production
```

Run the governed live-apply wrapper:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=redpanda env=production
```

## Verification

Verify the private Redpanda Admin API readiness endpoint on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'
from pathlib import Path
import base64
import urllib.request

env = {}
for line in Path("/run/lv3-secrets/redpanda/runtime.env").read_text(encoding="utf-8").splitlines():
    if "=" in line:
        key, value = line.split("=", 1)
        env[key] = value

token = base64.b64encode(
    f"{env['REDPANDA_ADMIN_USER']}:{env['REDPANDA_ADMIN_PASSWORD']}".encode("utf-8")
).decode("ascii")
request = urllib.request.Request(
    "http://127.0.0.1:9644/v1/status/ready",
    headers={"Authorization": f"Basic {token}"},
)
with urllib.request.urlopen(request, timeout=30) as response:
    print(response.status)
PY'
```

Verify HTTP Proxy produce/read and Schema Registry access with the platform principal:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'
from pathlib import Path
import base64
import json
import time
import urllib.request

env = {}
for line in Path("/run/lv3-secrets/redpanda/runtime.env").read_text(encoding="utf-8").splitlines():
    if "=" in line:
        key, value = line.split("=", 1)
        env[key] = value

def auth(user_key: str, password_key: str) -> str:
    return base64.b64encode(
        f"{env[user_key]}:{env[password_key]}".encode("utf-8")
    ).decode("ascii")

marker = f"runbook-redpanda-{int(time.time())}"
payload = json.dumps(
    {
        "records": [
            {
                "value": {
                    "marker": marker,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "producer": "runbook",
                }
            }
        ]
    }
).encode("utf-8")
produce_request = urllib.request.Request(
    "http://127.0.0.1:8097/topics/platform.redpanda.smoke",
    data=payload,
    headers={
        "Authorization": f"Basic {auth('REDPANDA_PLATFORM_USER', 'REDPANDA_PLATFORM_PASSWORD')}",
        "Content-Type": "application/vnd.kafka.json.v2+json",
        "Accept": "application/vnd.kafka.v2+json",
    },
    method="POST",
)
urllib.request.urlopen(produce_request, timeout=30).read()

records_request = urllib.request.Request(
    "http://127.0.0.1:8097/topics/platform.redpanda.smoke/partitions/0/records?offset=0&timeout=3000&max_bytes=1048576",
    headers={
        "Authorization": f"Basic {auth('REDPANDA_PLATFORM_USER', 'REDPANDA_PLATFORM_PASSWORD')}",
        "Accept": "application/vnd.kafka.json.v2+json",
    },
)
records = json.loads(urllib.request.urlopen(records_request, timeout=30).read().decode("utf-8"))
assert any(item.get("value", {}).get("marker") == marker for item in records)

schema_request = urllib.request.Request(
    "http://127.0.0.1:8099/subjects/platform.redpanda.smoke-value/versions/latest",
    headers={
        "Authorization": f"Basic {auth('REDPANDA_PLATFORM_USER', 'REDPANDA_PLATFORM_PASSWORD')}",
        "Accept": "application/vnd.schemaregistry.v1+json",
    },
)
schema_payload = json.loads(urllib.request.urlopen(schema_request, timeout=30).read().decode("utf-8"))
assert schema_payload["subject"] == "platform.redpanda.smoke-value"
print("verified")
PY'
```

## Operating Notes

- Redpanda is intentionally private-only. Do not publish it on the public NGINX edge.
- The repo-managed deployment uses `8097` and `8099` for the HTTP Proxy and
  Schema Registry listeners because `8081` and `8082` are already assigned to
  the mail platform gateway and NetBox on `docker-runtime-lv3`.
- The role reconciles topics programmatically with `rpk` from the declared topic
  list. Manual `rpk topic create` operations outside the role are treated as drift.
- The baseline keeps Schema Registry access authenticated over the private
  runtime path, but it does not reconcile per-subject Schema Registry ACLs.
  Redpanda documents Schema Registry authorization as an enterprise feature, so
  this workstream avoids baking unmanaged license state into the default runtime.
- The durable log volume is the named Docker volume `lv3-redpanda-data`. Today
  it inherits the governed VM-level backup coverage of `docker-runtime-lv3`;
  if Redpanda-specific snapshot automation is added later, record that evidence
  in the live-apply receipt and related backup runbooks.
