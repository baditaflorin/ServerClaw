# Agent Observation Loop

## Purpose

This runbook documents the ADR 0071 observation loop that checks live drift against repo intent and emits structured findings.

## Result

- six governed checks can be run from the controller with one command
- structured findings are written to `.local/platform-observation/latest/`
- a Markdown digest for Open WebUI review is written to `.local/open-webui/platform-findings-daily.md`
- optional NATS, Mattermost, and GlitchTip routing can be enabled with controller-local secrets
- ADR 0080 maintenance windows suppress only planned non-security noise, not the underlying checks

## Repo Surfaces

- `scripts/platform_observation_tool.py`
- `config/health-probe-catalog.json`
- `config/secret-catalog.json`
- `config/image-catalog.json`
- `docs/schema/platform-finding.json`

## Controller-Local Inputs

Required:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`

Optional routing hooks:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mattermost/platform-findings-webhook-url.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/glitchtip/platform-findings-event-url.txt`

## Commands

Run the full observation loop:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uvx --from pyyaml python scripts/platform_observation_tool.py
```

Run a subset while iterating:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uvx --from pyyaml python scripts/platform_observation_tool.py \
  --checks check-vm-state check-service-health check-backup-recency
```

Publish findings to NATS in addition to the local artifacts:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uvx --from pyyaml python scripts/platform_observation_tool.py --publish-nats
```

## What Each Check Does

1. `check-vm-state`
   compares the managed guest fleet in `inventory/host_vars/proxmox_florin.yml` with live Proxmox guest state through the governed host SSH path
2. `check-service-health`
   executes the machine-readable probe contract in `config/health-probe-catalog.json`
3. `check-image-freshness`
   compares running container image references on `docker-runtime-lv3` with `config/image-catalog.json` and flags unpinned images
4. `check-secret-ages`
   checks tracked controller-local secrets against `config/secret-catalog.json`
5. `check-certificate-expiry`
   inspects the Proxmox host certificate plus the private `step-ca`, OpenBao, and Portainer TLS endpoints
6. `check-backup-recency`
   reads the PBS target from the Proxmox host and verifies each managed guest has a recent recovery point

## Outputs

- `.local/platform-observation/latest/findings.json`
- `.local/platform-observation/latest/check-*.json`
- `.local/open-webui/platform-findings-daily.md`

Each finding follows `docs/schema/platform-finding.json`.

When ADR 0080 suppression is active, a finding may be emitted with:

- `severity: suppressed`
- `original_severity`
- `suppressed: true`
- `maintenance_windows`

## Routing Notes

- NATS publication uses the live `lv3-nats-jetstream` runtime on `docker-runtime-lv3` and emits one canonical event per finding on `platform.findings.observation`.
- Mattermost and GlitchTip routing stay local-secret-driven so the repo does not commit chat or issue-tracker credentials.
- Active maintenance windows are read from the private `maintenance-windows` NATS KV bucket unless `LV3_MAINTENANCE_WINDOWS_FILE` is set for test or offline use.
- The current Open WebUI integration is file-based: operators can review the digest artifact from the existing private workbench until a richer governed tool path lands.

## Dead-Man Switch

The repo-managed dead-man contract is five hours:

- if `.local/platform-observation/latest/findings.json` is older than five hours, treat the observation loop itself as stale
- if NATS publication is enabled, the lack of fresh `platform.findings.observation` events over the same window is the event-lane equivalent signal

## Verification

1. `uvx --from pyyaml python scripts/platform_observation_tool.py`
2. `test -f .local/platform-observation/latest/findings.json`
3. `test -f .local/open-webui/platform-findings-daily.md`
4. `jq 'length == 6' .local/platform-observation/latest/findings.json`

## Notes

- The controller command lane is the current execution surface because it already has the governed SSH and local-secret contracts needed for Proxmox, PBS, and guest-only probes.
- The observation data models are intentionally explicit even where the current platform still has drift. A warning or critical finding is expected until the dependent ADRs are fully converged.
