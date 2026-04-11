# Proxmox API Automation Runbook

## Purpose

This runbook captures the durable, non-human API identity used for Proxmox object management.

Under [ADR 0046](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0046-identity-classes-for-humans-services-and-agents.md), `lv3-automation@pve` is classified as an `agent` identity rather than a human or break-glass path.

## Result

- creates the dedicated Proxmox API user `lv3-automation@pve`
- creates or updates the custom Proxmox role `LV3Automation`
- grants `LV3Automation` on `/`
- creates the privilege-separated token `lv3-automation@pve!primary`
- stores the returned token secret outside git in:
  - `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/proxmox-api/lv3-automation-primary.json`
- verifies the token against `https://proxmox.example.com:8006/api2/json/version`

The managed `LV3Automation` role intentionally preserves the current `PVEAdmin` VM and datastore surface while adding `Sys.Modify`, which the live OpenTofu VM apply path needs on Proxmox VE 9.

## Command

```bash
make provision-api-access
```

## Verification

Inspect the non-secret remote identity state:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@203.0.113.1 'sudo pveum user list --full && echo --- && sudo pveum user token list lv3-automation@pve --output-format json && echo --- && sudo pveum acl list --output-format json'
```

Verify the local token works:

```bash
python3 - <<'PY'
import json
import pathlib
import subprocess

payload = json.loads(pathlib.Path("/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/proxmox-api/lv3-automation-primary.json").read_text())
subprocess.run(
    [
        "curl",
        "-fsS",
        "-H",
        payload["authorization_header"],
        "https://proxmox.example.com:8006/api2/json/version",
    ],
    check=True,
)
PY
```

## Rotation Notes

The token secret is only returned by Proxmox once, at creation time. If the local secret file is lost:

1. revoke the existing token on the Proxmox host
2. rerun `make provision-api-access`
3. commit and push the repo updates if the live platform changed as part of the rotation
