# Changelog

This file records repository-level releases and the platform changes they introduced.

The repo uses semantic versioning for repository maturity and operating contract. The live platform version is tracked separately in [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml).

Historical entries before `0.10.0` are reconstructed from repository history, ADR metadata, and observed platform evolution.

## Unreleased

- use this section on `main` for merged notes that have not yet been cut into a numbered release

## 0.30.0 - 2026-03-22

- merged and renumbered the local PBS backup workstream as ADR 0029 because ADR 0028 was already assigned on `main`
- added a dedicated `backup-lv3` VM rollout with deterministic guest networking, Proxmox Backup Server bootstrap, and datastore automation
- added Proxmox-host PBS storage and nightly backup-job automation for protected VMIDs `110`, `120`, `130`, `140`, and `150`
- added a backup VM runbook, restore-oriented verification steps, and agent-facing lessons learned for cloud-init MAC drift and reboot behavior

Platform impact:

- VM `160` `backup-lv3` now runs on `10.10.10.60`
- Proxmox storage `lv3-backup-pbs` now targets PBS datastore `proxmox` on `10.10.10.60:8007`
- nightly job `backup-lv3-nightly` now protects VMIDs `110`, `120`, `130`, `140`, and `150` at `02:30`
- an ad hoc PBS backup for VM `110` was verified and is listed in the live datastore

## 0.29.0 - 2026-03-22

- merged ADR 0028 into `main` to add Docker build count and duration telemetry for `docker-build-lv3`
- added a managed Docker CLI wrapper plus Telegraf shipping for `docker build`, `docker buildx build`, `docker buildx bake`, and `docker compose build`
- extended the managed Grafana dashboards with build-count and build-duration panels for the build VM
- updated ADR 0028, the monitoring runbook, and the workstream docs to describe the live telemetry contract

Platform impact:

- `docker-build-lv3` now writes `docker_builds` telemetry into InfluxDB for build count, exit code, start time, end time, and duration
- `LV3 docker-build-lv3 Detail` now has `14` panels including build timing views
- `LV3 Platform Overview` now has `32` panels including build timing summaries for the build VM

## 0.28.0 - 2026-03-22

- merged the Uptime Kuma workstream into `main` and renumbered its decision to ADR 0027 because ADR 0022 was already assigned on `main`
- added Docker-runtime automation to run Uptime Kuma under `/opt/uptime-kuma`
- added Hetzner DNS automation and NGINX edge publication for `uptime.lv3.org`
- added a repo-local Uptime Kuma management client, seed monitor definitions, and a deployment runbook
- documented the live guest-network repair procedure for stale netplan MAC matches discovered during rollout

Platform impact:

- `uptime.lv3.org` now serves Uptime Kuma through the NGINX edge
- `docker-runtime-lv3` now runs the Uptime Kuma container from `/opt/uptime-kuma`
- the shared edge certificate now covers `uptime.lv3.org`
- the control machine now keeps durable Uptime Kuma auth under `.local/uptime-kuma/`
- the initial repo-managed Uptime Kuma monitor set contains `6` checks

## 0.27.0 - 2026-03-22

- merged and renumbered the PostgreSQL workstream as ADR 0026 during integration because ADR 0025 was already assigned on `main`
- added a dedicated PostgreSQL VM baseline with guest provisioning, guest-local hardening, and a dedicated convergence playbook
- added a Proxmox-host Tailscale TCP proxy for PostgreSQL instead of exposing the database on the public edge
- added Hetzner DNS automation for a tailnet-only `database.lv3.org` record
- added a PostgreSQL runbook and workstream documentation for Tailscale-only access

Platform impact:

- VM `150` `postgres-lv3` now runs on `10.10.10.50`
- PostgreSQL is now reachable only through `database.lv3.org:5432` on the Proxmox host Tailscale IP `100.118.189.95`
- direct public access to `65.108.75.123:5432` remains closed
- the Proxmox host now runs a Tailscale-bound TCP proxy for PostgreSQL
- `database.lv3.org` now resolves to the Proxmox host Tailscale IPv4

## 0.26.0 - 2026-03-22

- added Grafana folder-aware dashboard provisioning for a stable LV3 monitoring namespace
- added per-VM Grafana dashboards for `nginx-lv3`, `docker-runtime-lv3`, `docker-build-lv3`, and `monitoring-lv3`
- refactored the monitoring dashboard templates into shared macros plus a generated VM-detail template
- updated the monitoring runbook, ADR 0011, repository map, and platform state to reflect the multi-dashboard layout

Platform impact:

- Grafana now contains the folder `LV3` with one high-level overview dashboard and four VM detail dashboards
- the live dashboard inventory is:
  - `LV3 Platform Overview` with `24` panels
  - `LV3 nginx-lv3 Detail` with `12` panels
  - `LV3 docker-runtime-lv3 Detail` with `8` panels
  - `LV3 docker-build-lv3 Detail` with `8` panels
  - `LV3 monitoring-lv3 Detail` with `8` panels
- `make converge-monitoring` was re-verified live and reran idempotently with `changed=0`

## 0.25.0 - 2026-03-22

- added ADR 0022 to codify the NGINX guest observability model as infrastructure architecture rather than implementation only
- linked the new ADR into the main repository docs and maps
- added ADR 0023, ADR 0024, and ADR 0025 to split Docker runtime, Docker security, and Compose stack work into parallel-safe tracks
- added Docker runtime automation for `docker-runtime-lv3` with Docker's official Debian repository, Compose v2, `live-restore`, and bounded JSON log rotation
- added a dedicated Docker runtime runbook and make targets for syntax check and convergence
- fixed the Docker runtime rollout after live verification exposed an unhandled distro `docker-buildx` package conflict
- documented the manual guest-network recovery that was required when VM `120` was found with a stale netplan MAC match

Platform impact:

- `docker-runtime-lv3` now runs Docker Engine `29.3.0`
- `docker-runtime-lv3` now has Docker Compose plugin `v5.1.1`
- Docker daemon on `10.10.10.20` now has `live-restore` enabled with `json-file` log rotation at `10m` and `5` files
- `ops` is now present in the local `docker` group on the runtime VM
- VM `120` guest networking was recovered live by correcting the stale MAC match in `/etc/netplan/50-cloud-init.yaml`

## 0.24.0 - 2026-03-22

- added guest-side nginx observability with Telegraf into the existing InfluxDB and Grafana path
- added a dedicated guest-writer token flow on the monitoring VM and mirrored it locally for managed guest telemetry
- extended the Grafana platform dashboard with nginx-specific service panels sourced from `stub_status`
- updated the monitoring runbook, ADR 0011, and repository map to reflect nginx service monitoring

Platform impact:

- `nginx-lv3` now exposes `stub_status` on loopback-only `127.0.0.1:8080/basic_status`
- Telegraf now runs on `nginx-lv3` and writes guest metrics into InfluxDB
- the dashboard `LV3 Platform Overview` now includes nginx service panels and has `24` panels total
- nginx measurement flow to InfluxDB was verified live

## 0.23.0 - 2026-03-22

- added Grafana dashboard-as-code for the LV3 platform monitoring view
- fixed `make converge-monitoring` so the monitoring VM converges through the Proxmox jump path instead of trying a direct private-IP SSH path
- switched dashboard rollout from fragile boot-time file-provider provisioning to an API import flow after Grafana health, while still keeping the dashboard JSON in repo
- updated ADR 0011 and the monitoring runbook to reflect the fully provisioned Grafana dashboard

Platform impact:

- Grafana now contains the provisioned dashboard `LV3 Platform Overview`
- the dashboard monitors the Proxmox host and each managed VM individually
- the live dashboard currently has `20` panels
- Grafana health was re-verified after the dashboard import

## 0.22.0 - 2026-03-22

- added IaC for public hostname publication at the NGINX edge
- added ADR 0021 for truthful subdomain publication rules
- added edge publication runbook, playbook, and NGINX role with host-based routing and certificate issuance support
- fixed the Proxmox host nftables policy so private guests on `vmbr10` can reach each other

Platform impact:

- `grafana.lv3.org` now serves the Grafana login page through the NGINX edge
- `nginx.lv3.org` now serves an explicit edge landing page
- `proxmox.lv3.org`, `docker.lv3.org`, and `build.lv3.org` now serve explicit informational pages instead of the default Debian NGINX page
- the NGINX edge now presents a Let's Encrypt certificate for the published subdomains

## 0.21.0 - 2026-03-22

- verified that the Tailscale-first host administration path is now working from the laptop
- confirmed that Proxmox API access on `100.118.189.95:8006` is reachable
- confirmed that public SSH to `65.108.75.123:22` is no longer the active routine management path

Platform impact:

- `ssh ops@100.118.189.95` now succeeds from the operator laptop
- `https://100.118.189.95:8006` is reachable on the Tailscale path
- the public IPv4 management path remains blocked from this workstation, which is acceptable for the current Tailscale-first model

## 0.20.0 - 2026-03-22

- made the Proxmox host Tailscale IP the default routine SSH and Ansible endpoint
- changed the declared management-source policy from the home public IP to the Tailscale management range
- updated ADR 0006, ADR 0014, and the access/security runbooks to reflect Tailscale-first host administration
- recorded that the live cutover is still blocked because `tailscale ping` works but TCP `22` and `8006` to `100.118.189.95` still time out from this workstation

Platform impact:

- the intended routine host administration target is now `100.118.189.95`
- the public-IP home allowlist is no longer the intended steady-state management path from this repo
- current live verification is incomplete because both public-IP SSH and Tailscale TCP management access from this workstation are blocked
- guest subnet routing remains optional and still depends on tailnet route approval

## 0.19.0 - 2026-03-22

- verified the approved Tailscale host login on the Proxmox node
- corrected repository state to reflect that ADR 0014 is blocked on subnet-route acceptance, not host authentication
- prepared the finished workstream branches and worktrees for safe deletion after merge verification

Platform impact:

- the Proxmox host now has the Tailscale address `100.118.189.95`
- the host is advertising `10.10.10.0/24` to the tailnet
- operator clients still do not receive the private subnet route, so ADR 0014 is not fully live yet

## 0.18.0 - 2026-03-22

- fixed the InfluxData repository integration in the monitoring role for current Debian package verification
- applied ADR 0011 live and verified Grafana, InfluxDB, and Proxmox metric ingestion
- applied the installable portion of ADR 0014 and recorded the remaining tailnet-authentication blocker
- recorded the external-credential blocker that still prevents ADR 0020 live apply

Platform impact:

- monitoring VM `140` now runs Grafana and InfluxDB
- Proxmox external metrics now write to `10.10.10.40`
- Tailscale is installed on the Proxmox host but still needs login and route approval
- backups are not yet configured because the external CIFS target credentials are still missing

## 0.17.0 - 2026-03-22

- merged ADR 0011 monitoring automation into `main`
- merged ADR 0014 Tailscale private-access automation into `main`
- merged ADR 0020 storage and backup automation into `main`
- added `scripts/create-workstream.sh` and `make start-workstream` so each thread can create its own branch/worktree safely from the registry
- marked the three completed workstreams as merged in the registry and workstream documents

Platform impact:

- none yet
- these changes are merged to `main` but have not been applied live from `main`

## 0.16.0 - 2026-03-22

- clarified branch reconciliation rules for parallel workstreams
- marked `VERSION`, numbered changelog releases, canonical observed state, and top-level README summaries as protected integration files
- documented that only the merge/integration step should rewrite those shared files
- documented the option of a temporary `codex/integration` branch when several workstreams need to be combined before `main`

Platform impact:

- none

## 0.15.0 - 2026-03-22

- added a parallel workstream model so multiple ADRs can be implemented in separate branches and chats
- added `workstreams.yaml` as the machine-readable implementation registry
- added workstream docs, a template, and an explicit release process
- updated repository rules so `VERSION` is bumped on merge to `main`, while `platform_version` is bumped only after live apply from `main`

Platform impact:

- none

## 0.14.0 - 2026-03-21

- fully implemented ADR 0007 with a durable Proxmox API automation identity
- added a dedicated role to create and verify a privilege-separated Proxmox API token
- added a runbook for token use and rotation
- recorded the durable token path in assistant-facing repository docs

Platform impact:

- `lv3-automation@pve` now exists as the non-human Proxmox API identity
- the privilege-separated token `lv3-automation@pve!primary` is present and ACLed for automation use
- the token secret is stored only in the controller-local `.local/proxmox-api/` path

## 0.13.0 - 2026-03-21

- implemented the remaining host security baseline from ADR 0006
- added Proxmox host firewall policy with management source restrictions
- automated ACME issuance for `proxmox.lv3.org` through Hetzner DNS
- configured notification routing to the LV3 operations mailbox
- provisioned TOTP for `ops@pam`
- added a dedicated security-baseline runbook
- strengthened repository rules so live applied changes must also land as a pushed version bump

Platform impact:

- Proxmox firewall is enabled and management access is source-restricted
- `proxmox.lv3.org:8006` now presents a Let's Encrypt certificate
- `ops@pam` now requires TOTP
- sendmail notifications are configured with a catch-all matcher

## 0.12.0 - 2026-03-21

- implemented the single-edge public ingress model from ADR 0013
- added host-side nftables DNAT for public TCP `80/443` to the NGINX VM
- added an explicit ingress runbook and make target
- updated ADR 0013 from partial to implemented

Platform impact:

- the public host IPv4 now forwards `80/443` to `10.10.10.10`
- `nginx.lv3.org` and direct HTTP to the host can terminate on the NGINX VM

## 0.11.0 - 2026-03-21

- added this changelog to make version history explicit
- added [docs/repository-map.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/repository-map.md) as a navigation index for humans and assistants
- added [docs/assistant-operator-guide.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/assistant-operator-guide.md) to document how to read, change, verify, and persist infrastructure work in this repo
- updated repo guidance so future meaningful changes also update the changelog

Platform impact:

- none

## 0.10.0 - 2026-03-21

- made `ops` the default non-root automation and SSH identity for the Proxmox host
- added a reusable Linux access baseline role
- added guest access hardening playbook and inventory wiring for private guests through the Proxmox jump path
- documented the operating model in ADR 0018 and the hardening runbook

Platform impact:

- host administration now defaults to `ops` plus `sudo`
- guest administration now defaults to `ops` plus `sudo`
- host SSH password auth is disabled
- guest SSH password auth is disabled
- direct guest root SSH is disabled

## 0.9.0 - 2026-03-21

- transitional repository release during the non-root access hardening rollout
- prepared the repository-wide move from root-first workflows to `ops`-first workflows

Platform impact:

- no distinct standalone platform milestone beyond the access-hardening work completed in `0.10.0`

## 0.8.0 - 2026-03-21

- changed the intended private-guest operator access model from WireGuard to Tailscale
- updated ADR 0014 and desired-state metadata to match the existing infrastructure direction

Platform impact:

- no live Tailscale deployment yet
- platform intent changed so future private access work targets Tailscale

## 0.7.0 - 2026-03-21

- added ADR lifecycle metadata to track implementation status, first repo version, first platform version, and implementation date
- backfilled existing ADRs with implementation metadata

Platform impact:

- none

## 0.6.0 - 2026-03-21

- defined the initial VM topology and monitoring model
- implemented provisioning from a Debian 13 cloud template
- added automation for guest creation and cloud-init bootstrap

Platform impact:

- template `9000` created
- guests `110`, `120`, `130`, and `140` provisioned and running
- internal guest SSH via the Proxmox jump path became usable

## 0.5.0 - 2026-03-21

- documented the `lv3.org` DNS and subdomain model
- created initial public DNS records for `proxmox`, `grafana`, `nginx`, `docker`, and `build`

Platform impact:

- the Hetzner DNS zone now points those subdomains at the Proxmox host IPv4

## 0.4.0 - 2026-03-21

- added ADRs to define the public ingress model and private operator access model for the `10.10.10.0/24` guest network
- clarified that the NGINX VM is the intended public edge and that non-edge guests remain private by default

Platform impact:

- no major live change beyond design clarification

## 0.3.0 - 2026-03-21

- implemented Proxmox host network convergence
- defined `vmbr0` as the public bridge and `vmbr10` as the internal guest bridge
- enabled IPv4 forwarding and outbound NAT for guest egress

Platform impact:

- the host became ready to support private guest networking on `10.10.10.0/24`

## 0.2.0 - 2026-03-21

- implemented the Debian-package Proxmox installation path
- added the first executable Ansible scaffold for host bootstrap
- documented the single-node-first platform direction and the initial security baseline

Platform impact:

- Proxmox VE was installed on the Hetzner host
- the host began operating on the Proxmox kernel and management stack

## 0.1.0 - 2026-03-21

- established the repository, initial README, runbooks, and early ADR set
- documented the Hetzner rescue-plus-installimage bootstrap path
- introduced separate repository and platform version tracking
- made DRY and solid engineering principles explicit

Platform impact:

- bootstrap and recovery process became documented and repeatable
