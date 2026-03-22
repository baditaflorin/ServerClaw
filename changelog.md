# Changelog

This file records repository-level releases and the platform changes they introduced.

The repo uses semantic versioning for repository maturity and operating contract. The live platform version is tracked separately in [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml).

Historical entries before `0.10.0` are reconstructed from repository history, ADR metadata, and observed platform evolution.

## Unreleased

## 0.55.0 - 2026-03-22

- completed the ADR 0053 repository rollout by enabling Prometheus native histograms for Tempo's metrics generator, which unblocks persisted span-metrics and service-graph writes into the managed Prometheus receiver
- corrected the first traced producer so the mail gateway now honors `OTEL_RESOURCE_ATTRIBUTES` in addition to `OTEL_SERVICE_NAME`, keeping `service.namespace` and `deployment.environment` aligned with the shared observability contract
- refreshed the tracing ADR and runbooks to document the corrected Prometheus and resource-tag expectations before the live apply from `main`

Platform impact:

- no direct live platform change in this release commit; the corrected tracing stack still needs to be applied from `main`

## 0.54.0 - 2026-03-22

- applied ADR 0060 live by converging a private Open WebUI runtime on `docker-runtime-lv3` and publishing it through the Proxmox host Tailscale proxy on port `8008`
- added repo-managed Open WebUI automation, workflow and command contracts, controller-local bootstrap secret handling, and an operator runbook for the workbench
- locked the initial workbench posture down to local bootstrap auth with future OIDC support, disabled public signup and community sharing, and disabled web search, image generation, code interpreter, and direct tool servers by policy
- updated ADR 0060, workstream state, generated status docs, and live-apply evidence to reflect the new private operator workbench

Platform impact:

- Open WebUI is now live privately at `http://100.118.189.95:8008`
- controller-local bootstrap artifacts now exist under `.local/open-webui/`
- the first operator-and-agent workbench now exists, but governed tools and repo-grounded RAG remain follow-up work under ADR 0069 and ADR 0070

## 0.53.0 - 2026-03-22

- implemented ADR 0059 live by installing `ntopng` on `proxmox_florin`, capturing the private guest bridge directly from `vmbr10`, and adding edge-adjacent context from `vmbr0`
- added a dedicated `playbooks/ntopng.yml` converge path, the new `roles/proxmox_ntopng` automation, a private-access runbook, and workflow or command catalog entries for operator-driven flow visibility
- exposed the ntopng UI only through the Proxmox host Tailscale proxy on port `3001`, kept it off the public edge, and updated ADR or workstream metadata to mark the network-visibility rollout as live

Platform impact:

- ntopng is now running on `proxmox_florin` and is reachable privately at `http://100.118.189.95:3001`
- operators now have a repo-managed flow-visibility surface for `vmbr10` private-network traffic and `vmbr0` edge context without introducing nProbe or public publication
- the Proxmox host firewall now explicitly allows the ntopng proxy port only from declared management sources

## 0.52.0 - 2026-03-22

- applied ADR 0050 live by provisioning distinct operator, platform, and agent sender profiles on the managed mail platform instead of reusing one global outbound credential
- added scoped notification-profile mailbox passwords and mail-gateway API keys, plus gateway-side profile enforcement and per-profile delivery counters
- documented the new sender-profile operating model, added controller-local secret inventory entries, and added a focused profile verification playbook for live delivery checks

Platform impact:

- `alerts@lv3.org`, `platform@lv3.org`, and `agents@lv3.org` now exist as managed sender identities on `docker-runtime-lv3`
- each sender profile now has its own scoped mail-gateway API key and mailbox password mirrored under `.local/mail-platform/profiles/`
- the mail gateway now enforces profile-bound send identity and records per-profile request and delivery counters

## 0.51.0 - 2026-03-22

- implemented ADR 0053 in repository automation by adding pinned Tempo and `otelcol-contrib` packages plus a managed Prometheus service to the monitoring VM role
- provisioned Grafana Prometheus and Tempo datasources, documented the shared OTLP collector contract, and instrumented the private mail-gateway service as the first traced internal API surface
- updated the ADR, workstream, monitoring runbook, mail-platform runbook, and workflow catalog to describe the new tracing and service-map operating model

Platform impact:

- no direct live platform change in this release commit; the tracing stack still needs to be applied from `main`

## 0.50.0 - 2026-03-22

- implemented ADR 0049 as a canonical API publication contract instead of leaving publication policy only in prose
- added `config/api-publication.json` plus `scripts/api_publication.py` so publication tiers are machine-readable, inspectable, and validation-backed
- extended the governed API lane inventory to include the live OpenBao and Windmill APIs, and classified every current API or webhook surface as internal-only, operator-only, or public-edge
- rendered the publication-tier summary into the generated README and documented the operating procedure in a dedicated API publication runbook

Platform impact:

- no direct live platform change; this release makes the existing private-first API and webhook exposure model explicit, reviewable, and enforced from `main`

## 0.49.0 - 2026-03-22

- applied ADR 0047 live from `main` by proving short-lived `step-ca` SSH certificates for routine operator access and by enforcing internal mTLS on the private OpenBao API
- corrected the OpenBao runtime so the `step` CLI invocation, TLS file paths, listener layout, inventory overrides, and end-to-end delegated verification all rerun cleanly from the integration worktree
- updated the step-ca and OpenBao runbooks, ADR metadata, workstream state, and live-apply evidence to reflect the now-live short-lived credential and mTLS operating model

Platform impact:

- short-lived `step-ca` SSH certificates are now verified from the controller for `ops` access to both the Proxmox host and managed guests
- the private OpenBao API is now published at `https://100.118.189.95:8200` with a `step-ca`-issued server certificate and required client-certificate authentication
- OpenBao AppRole artifacts continue to be refreshed as short-lived controller-local credentials with one-use secret IDs and a 15-minute TTL


## 0.48.0 - 2026-03-22

- applied ADR 0043 live from `main` by converging OpenBao on `docker-runtime-lv3`, provisioning its PostgreSQL backend inputs on `postgres-lv3`, and seeding scoped controller and mail secrets into the managed secret authority
- hardened the OpenBao workflow so managed init and unseal, AppRole artifact refresh, active-node waiting, and PostgreSQL dynamic credential verification rerun cleanly from the integration worktree
- recorded controller-local OpenBao bootstrap and AppRole artifact handling, a live-apply receipt, and updated ADR/workstream metadata to mark the secret authority as live

Platform impact:

- OpenBao is now live on `docker-runtime-lv3` with integrated Raft storage, managed init and unseal, scoped `userpass` and `AppRole` identities, verified Transit operations, and a verified PostgreSQL dynamic credential path to `postgres-lv3`
- controller-local recovery material now includes the OpenBao init payload plus refreshed short-lived AppRole artifacts under `.local/openbao/`
- the platform now has a private secret authority for controller automation, mail runtime secrets, and short-lived database access instead of relying only on repo-local secret files

## 0.47.0 - 2026-03-22

- applied ADR 0044 live from `main` by provisioning the Windmill PostgreSQL backend on `postgres-lv3`, converging the private Windmill runtime on `docker-runtime-lv3`, and exposing operator access through the Proxmox host Tailscale proxy on port `8005`
- hardened the Windmill automation so workspace bootstrap, database ownership, and repo-managed seed-script sync rerun cleanly against Windmill's actual API behavior and prior partial state
- recorded controller-local Windmill bootstrap artifacts and a live-apply receipt, and updated ADR/workstream metadata to mark the workflow runtime as live

Platform impact:

- Windmill is now live on `docker-runtime-lv3` and reachable privately at `http://100.118.189.95:8005`
- `postgres-lv3` now serves the managed `windmill` database with the `windmill_admin` and `windmill_user` roles required by the runtime
- the repo-managed `lv3` workspace and `f/lv3/windmill_healthcheck` script now provide a verified bootstrap workflow surface for agents and operators

## 0.46.0 - 2026-03-22

- applied ADR 0042 live from `main` by converging the private `step-ca` runtime on `docker-runtime-lv3`, publishing it through the Proxmox host Tailscale address, and installing CA-backed SSH host trust on the Proxmox host and managed guests
- fixed the `step-ca` runtime so the container honors the initialized absolute path layout and validates issued service certificates against the intermediate chain during convergence
- recorded controller-local bootstrap artifacts and a live-apply receipt for the step-ca rollout, including verified operator-side health, SSH certificate login, and proxied X.509 issuance

Platform impact:

- `step-ca` is now live on `docker-runtime-lv3` and reachable privately at `https://100.118.189.95:9443`
- the Proxmox host and managed guests now trust the internal SSH CA and carry `step-ca`-issued SSH host certificates
- internal certificate issuance for services and operators is now available through the private CA path

## 0.45.0 - 2026-03-22

- implemented ADR 0042, ADR 0043, ADR 0044, ADR 0045, ADR 0046, and ADR 0048 as concrete repository control-plane contracts instead of planning-only documents
- added repo-managed `step-ca`, OpenBao, and Windmill playbooks, roles, workflow-catalog entries, runbooks, and controller-local bootstrap artifact contracts so those control-plane components can be converged from `main`
- added a canonical control-plane lane catalog, CLI inspector, generated README summary, and validation wiring for the command, API, message, and event lanes
- added a canonical identity taxonomy and managed-principal inventory to `versions/stack.yaml` covering the current human, service, agent, and break-glass identities
- added a canonical command catalog plus approval-gate CLI for mutating workflows, with explicit requester classes, input contracts, evidence expectations, and rollback guidance
- extended the repository data-model validator so identity classes, required metadata, and principal cross-references fail fast during `make validate`
- added lane, identity, command-catalog, `step-ca`, OpenBao, and Windmill runbooks and updated the assistant/operator discovery docs so future control-plane surfaces and credentials extend one documented model instead of inventing ad hoc paths
- added ADRs 0052 through 0061 plus a visual operations roadmap runbook to capture the next planned observability, identity, ChatOps, eventing, and operator-workbench workstreams
- tightened the validation script so YAML, Ansible lint, shell, and JSON stages operate on tracked repository files instead of unrelated local work-in-progress
- fixed the monitoring role's Grafana handler notifications so `make converge-monitoring` can rerun cleanly while importing repo-managed dashboards

Platform impact:

- no direct live platform change; this release hardens repository truth and reviewability around control-plane lanes, managed identities, command approval gates, and the next control-plane automation backlog

## 0.44.0 - 2026-03-22

- added ADRs 0042 through 0051 to define the proposed agentic control-plane model for internal CA, secrets, workflows, communication lanes, identity classes, short-lived credentials, command contracts, private API publication, notification profiles, and recovery
- added a control-plane roadmap runbook that ties those decisions into a recommended rollout order and initial placement across `docker-runtime-lv3`, `postgres-lv3`, and the existing mail platform
- registered the new workstreams in `workstreams.yaml` so future implementation threads can proceed with explicit dependencies and shared surfaces

Platform impact:

- no direct live platform change; this release integrates planning ADRs and workstream metadata only

## 0.43.0 - 2026-03-22

- implemented the live Dockerized mail platform on `docker-runtime-lv3` with Stalwart, a private mail gateway API, and repo-managed Brevo fallback resend
- added CRUD-capable domain and mailbox automation endpoints for server-side and agent use, plus dedicated mail observability collection and the `LV3 Mail Platform` Grafana dashboard
- extended Hetzner DNS automation and host ingress policy for the mail stack, including support for multiple managed TXT records at the same name and explicit Proxmox firewall allows for published mail ports
- authenticated `lv3.org` in Brevo, activated `server@lv3.org` as the sender identity, and documented the operational runbook and live rollout workstream

Platform impact:

- live mail platform is now running on `docker-runtime-lv3`
- `server@lv3.org` now receives external mail and can send mail through the managed fallback path
- Grafana now exposes a dedicated `LV3 Mail Platform` dashboard with live mail flow metrics

## 0.42.0 - 2026-03-22

- implemented ADR 0039 to add a shared controller automation toolkit for repo-local Python scripts
- added `scripts/controller_automation_toolkit.py` for repo path resolution, JSON and YAML loading, JSON writing, Make target parsing, subprocess success checks, and consistent CLI error formatting
- refactored the workflow catalog, preflight, live-apply receipts, repository data-model validation, generated-status-docs, Uptime Kuma, and TOTP scripts to consume the shared toolkit instead of repeating local helpers
- added a controller automation toolkit runbook and updated the repository map, assistant guide, and ADR metadata to make the shared boundary explicit
- updated workflow metadata so the validation and generated-status-doc workflows declare the shared toolkit as part of their implementation surface

Platform impact:

- no direct live platform change; this release refactors and hardens the controller-side automation contract only

## 0.41.0 - 2026-03-22

- implemented ADR 0038 to generate selected README status documents from canonical repository state
- added `scripts/generate_status_docs.py` plus managed README markers for platform status, version summary, document indexes, and merged workstream inventory
- added `make generate-status-docs` and `make validate-generated-docs`, and wired generated-doc verification into `make validate`
- added a dedicated runbook for generated status documents and updated the repository map, release process, validation runbook, and assistant guide to treat generated docs as part of the standard repo contract
- reduced README copy-maintenance by deriving repeated inventories from `versions/stack.yaml`, host vars, `workstreams.yaml`, and the document tree

Platform impact:

- no direct live platform change; this release makes selected documentation deterministic and validated from repo state only

## 0.40.0 - 2026-03-22

- implemented ADR 0037 to add schema validation for the repository's canonical machine-readable data models
- added `scripts/validate_repository_data_models.py` to validate `versions/stack.yaml`, canonical host vars, workflow and secret manifests, Uptime Kuma monitors, and live-apply receipts
- added `make validate-data-models` and integrated the new schema stage into `make validate`
- tightened `versions/stack.yaml` so the managed guest fleet and backup state now match the canonical host inventory and current repository truth
- updated the validation runbook, repository map, assistant guide, and ADR metadata to document the schema-backed contract

Platform impact:

- no direct live platform change; this release hardens the repository contract and canonical state validation only

## 0.39.0 - 2026-03-22

- merged the mail platform planning workstream and renumbered its decision to ADR 0041 during integration because ADR 0040 was already assigned on `main`
- added a fully descriptive ADR for a Dockerized mail platform covering server delivery, machine-facing CRUD automation, Grafana telemetry, and failover delivery behavior
- documented Stalwart as the recommended primary open-source mail server, with a Postfix relay sidecar for stable internal submission and backup resend policy
- added a rollout runbook that captures the implementation order, observability requirements, cutover gate, and prerequisite DNS and reputation inputs
- registered the mail platform workstream in `workstreams.yaml` so a later assistant can implement it without hidden chat context

Platform impact:

- no direct live platform change; this release records the mail platform decision and rollout plan in the repository only

## 0.38.0 - 2026-03-22

- implemented ADR 0040 to expose Docker runtime container detail through the existing monitoring stack
- added `roles/docker_runtime_observability` so `docker-runtime-lv3` ships Telegraf Docker input metrics into the shared InfluxDB path
- extended the managed `LV3 docker-runtime-lv3 Detail` dashboard with running-container counts, aggregate CPU and memory, per-container CPU and memory, network throughput, and a container snapshot table
- updated the monitoring runbook, repository map, and workstream registry to describe the runtime telemetry convergence path

Platform impact:

- no direct live platform change; this release adds repo-managed runtime container telemetry and dashboard definitions that still need live convergence from `main`

## 0.37.0 - 2026-03-22

- implemented ADR 0036 to add structured live-apply receipts and verification evidence to the repository
- added `receipts/live-applies` plus `scripts/live_apply_receipts.py` to capture and validate applied date, source commit, workflow id, targets, verification results, and evidence references
- added `make receipts` and `make receipt-info RECEIPT=<id>` for evidence discovery and integrated receipt validation into `make validate`
- backfilled receipts for the current known live applies covering monitoring, edge publication, Docker runtime, PostgreSQL, Uptime Kuma, Docker build telemetry, and the backup VM
- linked the latest receipt ids from `versions/stack.yaml` and documented the receipt lifecycle in the new runbook and release process

Platform impact:

- no direct live platform change; this release makes existing live evidence explicit and auditable in the repository only

## 0.36.0 - 2026-03-22

- implemented ADR 0035 to define a canonical machine-readable workflow catalog for repository execution paths
- added `config/workflow-catalog.json` plus `scripts/workflow_catalog.py` to declare and validate preferred entry points, preflight requirements, validation targets, live-impact classification, runbooks, and verification commands
- moved workflow ownership out of `config/controller-local-secrets.json` so the secret manifest remains a pure secret inventory while preflight reads workflow metadata from the catalog
- added `make workflows` and `make workflow-info WORKFLOW=<id>` for workflow discovery, plus new managed entry points for PostgreSQL convergence and repo-local Uptime Kuma management
- updated operator runbooks, the repository map, and ADR metadata to document the new execution contract surface

Platform impact:

- no direct live platform change; this release makes workflow discovery and execution metadata explicit in the repository only

## 0.35.0 - 2026-03-22

- implemented ADR 0034 to define a machine-readable controller-local secret manifest and standard workflow preflight
- added `config/controller-local-secrets.json` to declare required, generated, and blocked local secret material for repo workflows
- added `scripts/preflight_controller_local.py` plus `make preflight` so operators can check local prerequisites before long-running converges
- wired common Make targets to run preflight automatically and added `make database-dns` so PostgreSQL tailnet DNS uses the same contract
- updated the assistant guide, repository map, PostgreSQL runbook, and ADR metadata to document the new controller-local operating boundary

Platform impact:

- no direct live platform change; this release makes controller-local secret prerequisites explicit and fail-fast in the repository only

## 0.34.0 - 2026-03-22

- implemented ADR 0033 to add a canonical declarative service topology catalog for workload metadata
- added `lv3_service_topology` under host vars plus a topology filter plugin to derive public edge and DNS artifacts programmatically
- refactored edge publication, public DNS records, PostgreSQL tailnet DNS, and Uptime Kuma hostname defaults to consume the catalog instead of duplicating hostnames and exposure metadata
- updated the repository map and ADR metadata to describe the new topology source of truth

Platform impact:

- no direct live platform change; this release centralizes repository topology metadata only

## 0.33.0 - 2026-03-22

- implemented ADR 0032 to extract shared guest-local observability plumbing into a dedicated framework role
- added `roles/guest_observability` for common Telegraf installation, InfluxData repository setup, mirrored guest-writer token handling, and Telegraf verification
- refactored the nginx and docker-build guest observability roles into thin service-specific extensions on top of the shared framework
- updated the monitoring runbook, repository map, and ADR metadata to reflect the new shared observability boundary

Platform impact:

- no direct live platform change; this release refactors repository observability structure only

## 0.32.0 - 2026-03-22

- implemented ADR 0031 to define one repository validation contract for automation changes
- added `make validate` plus staged validation targets for Ansible syntax, YAML, Ansible lint, shell scripts, and JSON artifacts
- added repo-managed lint policy files, Ansible collection requirements, and a validation script that bootstraps tooling through `uvx`
- added a GitHub Actions workflow that runs the same `make validate` contract used locally
- documented the minimum merge gate in the validation runbook, release process, assistant guide, and workstream guidance
- fixed the monitoring role's INI module FQCN and cleaned up a small set of Ansible tasks so the new lint gate passes

Platform impact:

- no direct live platform change; this release adds repository validation and CI guardrails only

## 0.31.0 - 2026-03-22

- implemented ADR 0030 to make role interface contracts explicit across the reusable Ansible role set
- added `defaults/main.yml` and short role `README.md` files for the managed reusable roles
- added early input validation assertions near the top of each role so missing required inputs fail fast
- moved role-owned settings out of deleted role-local inventory files and out of shared inventory when they were not genuinely platform-global
- simplified playbooks and role call sites to rely on role defaults instead of extra imported variable files
- updated the repository map, PostgreSQL runbook, and workstream registry to reflect the new role-boundary model

Platform impact:

- no direct live platform change; this release hardens the repo contract and automation structure only

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
