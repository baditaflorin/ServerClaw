# Workstream ADR 0041: Dockerized Mail Platform Live Rollout

- ADR: [ADR 0041](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0041-dockerized-mail-platform-for-server-delivery-api-and-observability.md)
- Title: Dockerized mail platform live rollout
- Status: in_progress
- Branch: `codex/adr-0041-email-platform-live`
- Worktree: `../proxmox_florin_server-email-platform-live`
- Owner: codex
- Depends On: `adr-0041-email-platform`, `adr-0011-monitoring`, `adr-0023-docker-runtime`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `monitoring-lv3`, `playbooks/mail-platform.yml`, `roles/proxmox_network`, `lv3.org` DNS, `mail.lv3.org`

## Scope

- implement the mail platform selected by ADR 0041
- provide a private automation API for send plus mailbox and domain CRUD
- expose a dedicated Grafana dashboard for mail operations
- verify live inbound and outbound mail flow

## Non-Goals

- direct outbound SMTP reputation work beyond the current Brevo-backed send path
- replacing unrelated notification paths outside the mail platform workflow
- retrofitting the planning-only ADR 0041 workstream document

## Expected Repo Surfaces

- `playbooks/mail-platform.yml`
- `roles/mail_platform_runtime/`
- `roles/mail_platform_observability/`
- `roles/proxmox_network/`
- `roles/monitoring_vm/`
- `docs/runbooks/configure-mail-platform.md`
- `docs/workstreams/adr-0041-email-platform-live.md`
- `workstreams.yaml`

## Expected Live Surfaces

- public MX and mail A record for `lv3.org`
- public host forwarding for TCP `25`, `587`, and `993`
- Stalwart mail runtime on `docker-runtime-lv3`
- private mail gateway API on `10.10.10.20:8081`
- Grafana dashboard `lv3-mail-platform`

## Verification

- `make validate`
- `make syntax-check-mail-platform`
- `HETZNER_DNS_API_TOKEN=... make converge-mail-platform`

## Merge Criteria

- the mail workflow is fully automated from the repo
- inbound and outbound mail have been tested live
- Grafana shows fresh mail metrics
- a live-apply receipt is recorded before final merge to `main`
