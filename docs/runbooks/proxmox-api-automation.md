# Proxmox API Automation Runbook

## Purpose

This runbook captures the durable, non-human API identity used for Proxmox object management.

## Result

- creates the dedicated Proxmox API user `lv3-automation@pve`
- grants `PVEAdmin` on `/`
- creates the privilege-separated token `lv3-automation@pve!primary`
- stores the returned token secret outside git in:
  - `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json`
- verifies the token against `https://proxmox.lv3.org:8006/api2/json/version`

## Command

```bash
make provision-api-access
```

## Verification

Inspect the non-secret remote identity state:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123 'sudo pveum user list --full && echo --- && sudo pveum user token list lv3-automation@pve --output-format json && echo --- && sudo pveum acl list --output-format json'
```

Verify the local token works:

```bash
python3 - <<'PY'
import json
import pathlib
import subprocess

payload = json.loads(pathlib.Path("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json").read_text())
subprocess.run(
    [
        "curl",
        "-fsS",
        "-H",
        payload["authorization_header"],
        "https://proxmox.lv3.org:8006/api2/json/version",
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
