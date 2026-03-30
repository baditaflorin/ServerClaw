# proxmox_florin_server

Infrastructure-as-code workspace for building a dedicated Hetzner host into a Proxmox VE node.

The preferred bootstrap path is now Hetzner Rescue System plus `installimage`, not the automatic installer and not the VNC installer.

## Current status

Debian 13 is installed on the host, Proxmox VE is installed from the Debian package path, and routine SSH/Ansible access now works over the Headscale-managed mesh IP `100.64.0.1` instead of `root` on the public IPv4.

Verified on 2026-03-25:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1
```

Observed remote kernel:

```text
Linux Debian-trixie-latest-amd64-base 6.17.13-2-pve
```

Bootstrap key in use:

```text
SHA256:+wOwI8QKECFX9y2hlFMfBLP1m67PC0y9PYlO8+s0isQ
```

Installed Proxmox versions observed on 2026-03-21:

```text
proxmox-ve: 9.1.0
pve-manager: 9.1.6
running kernel: 6.17.13-2-pve
```

Management services are active and `pveproxy` is listening on `:8006`.

Proxmox host networking is now converged to:

```text
vmbr0  public bridge on enp7s0
vmbr10 internal bridge on 10.10.10.1/24
```

Host-side IPv4 forwarding and NAT are enabled for `10.10.10.0/24` guest egress.

Public ingress is now converged to the single-edge model:

```text
65.108.75.123:80  -> 10.10.10.10:80
65.108.75.123:443 -> 10.10.10.10:443
```

The shared nginx edge now enforces repo-managed HTTP security headers across every published hostname, including HSTS, CORP, CSP, clickjacking protection, MIME-sniff prevention, referrer controls, and bounded permissions policy defaults.

The private SSH jump path through the Proxmox host to the guests is working.

ADR 0144 is now implemented: Headscale runs on `proxmox_florin`, `https://headscale.lv3.org/health` returns `200` through the shared NGINX edge, the Proxmox host and one operator workstation are enrolled as `ops@`-owned nodes, and the approved `10.10.10.0/24` subnet route is reachable over the new mesh.

The private `step-ca` control plane is now live on `docker-runtime-lv3`, published only on `https://100.64.0.1:9443`, and the Proxmox host plus managed guests now trust `step-ca` for SSH host certificates and internal certificate issuance.

The private OpenBao secret authority is now live on `docker-runtime-lv3`, with a loopback bootstrap API on `127.0.0.1:8201` and a `step-ca`-issued mTLS endpoint at `https://100.64.0.1:8200` that rejects clients without a valid certificate.

Windmill is now live on `docker-runtime-lv3` and reachable privately at `http://100.64.0.1:8005`, with the repo-managed `lv3` workspace and seeded healthcheck script verified end to end.

Gitea is now live on `docker-runtime-lv3` at `http://100.64.0.1:3009`, with Keycloak-backed operator login, the repo-managed `ops/proxmox_florin_server` bootstrap path, mirrored controller-local admin and runner artifacts, and a verified self-hosted Actions runner on `docker-build-lv3`.

Harbor is now live on `docker-runtime-lv3` and published at `https://registry.lv3.org`, with Trivy-backed CVE scanning, Keycloak-backed operator login, a repo-managed `check-runner` project, and verified pull access from `docker-build-lv3` through the exact-main replay on 2026-03-29.

Signed release bundles are now live through that private Gitea path: the repo-managed `release-bundle` workflow publishes tarball, checksum, and Sigstore bundle assets into private Gitea Releases, and controller-side replay now verifies those assets with Cosign against the committed public key before treating them as eligible runtime input.

Dozzle is now live on `docker-runtime-lv3` and published at `https://logs.lv3.org`, with repo-managed agents on `docker-build-lv3` and `monitoring-lv3`, shared-edge Keycloak auth, and verified remote agent reachability over the guest network.

Homepage is now live on `docker-runtime-lv3` and published at `https://home.lv3.org`, with repo-generated service and bookmark catalogs, shared-edge Keycloak auth, and a verified public redirect to the oauth2-proxy sign-in flow.

NetBox is now live on `docker-runtime-lv3` and reachable privately at `http://100.64.0.1:8004`, with repo-managed synchronization of the Hetzner site, the Proxmox host, all managed VMs, canonical prefixes and IPs, and the governed service catalog.

The control-plane governance layer is now live on `main`: command, API, message, and event lanes are verified against the active host and mail surfaces, the current human/service/agent/break-glass principals have been re-reviewed against the identity taxonomy, and recurring live mutation is expected to use the named command catalog plus approval gates.

ADR 0080 maintenance windows are now implemented in repository automation, including the controller tool, governed command surface, and observation-loop suppression contract, but the current live NATS principal set still needs publish rights for `$KV.maintenance-windows.>` before controller-opened windows can be applied on the platform.

Mattermost is now live on `docker-runtime-lv3` and reachable privately at `http://100.64.0.1:8066`, with the repo-managed `lv3` collaboration channels, mirrored incoming webhook manifest, and Grafana alert contact point verified end to end.

Portainer is now live on `docker-runtime-lv3` and reachable privately at `https://100.64.0.1:9444`, with controller-local bootstrap artifacts under `.local/portainer` and a governed wrapper for read-mostly runtime inspection plus bounded restarts.

Private Ollama is now live on `docker-runtime-lv3` at `10.10.10.20:11434`, the repo-managed `llama3.2:3b` startup model is present, and Open WebUI now uses that connector privately through `host.docker.internal:11434` without publishing Ollama on the public edge.

Semantic platform-context retrieval is now live on `docker-runtime-lv3` at `http://100.64.0.1:8010`: the committed `0.177.26` governed `main` replay on 2026-03-28 preserved the healthy Ollama-backed vector collection, the earlier same-day latest-main replay proved the bounded repair path for legacy `384` to `768` drift, and direct API plus operator CLI queries now verify `retrieval_backend: "vector"` end to end.

The repository now also ships the repo-managed `lv3` operator CLI for terminal-first discovery, validation, status checks, and private control-plane entrypoints.
The repository now also ships ADR 0156 session workspace isolation for controller automation and the remote build gateway: separate checkouts now resolve to separate session namespaces and remote build-server workspaces, and the first live verification from current `main` completed on 2026-03-26.
The repository now also ships ADR 0264 failure-domain-isolated validation lanes: current `main` resolves changed repository surfaces into focused blocking lanes, declares live-apply receipts as a dedicated surface class, and the 2026-03-29 exact-main replay re-verified `make pre-push-gate`, `make gate-status`, `make remote-validate`, plus the worker-side lane-aware post-merge fallback from the refreshed `docker-runtime-lv3` checkout.
The repository now also ships ADR 0265 immutable validation snapshots for remote builders and schema checks: current `main` now uploads content-addressed repository snapshots into fresh `.lv3-runs/` namespaces on `docker-build-lv3`, and the newest exact-main replay on 2026-03-29 passed `make check-build-server` and `make remote-validate` end to end.
The repository now also ships ADR 0170 timeout hierarchy primitives: `config/timeout-hierarchy.yaml`, shared deadline propagation helpers, validation for catalog and hardcoded timeout drift, and runtime timeout wiring across the API gateway, scheduler, world-state workers, drift helpers, and NetBox sync; the integrated mainline live apply on 2026-03-25 re-converged the API gateway and Windmill with those runtime paths active and hardened the shared OpenBao secret-injection helper to recover from sealed restarts.
The repository now also ships ADR 0171 controlled fault injection live on production: the repo-managed `fault-injection` Windmill workflow and guarded schedule are present on `docker-runtime-lv3`, and the first `main`-based governed drills for Keycloak and OpenBao both passed on 2026-03-26 with OpenBao using pause/unpause so the secret store stays unsealed after validation.
The repository now also ships ADR 0189 network impairment matrix automation: the repo-managed Windmill workflow can render the governed staging and preview impairment plan on demand, and the 2026-03-27 live verification also hardened the mirrored worker checkout so repo-managed Python jobs no longer fail on stale editable-build metadata.
The repository now also ships ADR 0227 bounded governed command execution live on production: approved repo-managed commands now launch on `docker-runtime-lv3` through transient `systemd-run` units, stage controller-local secrets into repo-local worker paths, and preserve durable stdout, stderr, and receipt records under `.local/governed-command/`; the 2026-03-28 merged-main replay re-verified that path end to end with `network-impairment-matrix` against the guest-local Windmill API.
The new ADR 0107 extension model is now implemented in the repository: `make scaffold-service` writes the cross-cutting integration artifacts for a new service, and `lv3 validate --service <service_id>` enforces the completeness checklist with legacy per-check grandfathering until `2026-09-23`.
OpenTofu VM lifecycle automation is now implemented under `tofu/`, the six production VMs are imported into OpenTofu state through the build-server path, and `make tofu-drift ENV=production` now verifies the current production guest declarations without planned changes.
The repository now also ships continuous drift detection across OpenTofu, Ansible check mode, runtime Docker image digests, DNS records, and TLS posture, with receipts under `receipts/drift-reports/`, an ops-portal Drift Status panel, and `lv3 diff` routed to `make drift-report`; the live schedule and dashboard metric feed still require apply from `main`.
The repository now also ships ADR 0100 disaster-recovery targets, a structured recovery runbook, and `make dr-status` / `lv3 release status` readiness views; ADR 0181 off-host witness publication is now live, while the optional second off-site copy of `backup-lv3` still depends on external storage credentials.
ADR 0096 SLO tracking is now live on `monitoring-lv3`: the repo-managed blackbox exporter, generated Prometheus SLO rules and targets, and the `LV3 SLO Overview` Grafana dashboard were re-converged on 2026-03-25, and `grafana.lv3.org` now keeps `/api/health` blocked while dashboard URLs continue to redirect operators to login.
ADR 0249 HTTPS and TLS assurance is now live on `monitoring-lv3`: the repo-managed blackbox exporter now scrapes 33 declared HTTPS surfaces from the shared catalogs, Prometheus loads 99 handshake and expiry rules from the same target set, and the 2026-03-29 production `testssl.sh` replay finished with 11 medium timeout warnings and no high or critical findings.
ADR 0196 realtime metrics is now live on production: Netdata runs as a parent on `monitoring-lv3` with streamed children from `proxmox_florin`, `nginx-lv3`, `docker-runtime-lv3`, and `postgres-lv3`; `https://realtime.lv3.org` redirects through the shared oauth2 edge, and a governed read-only API route is available under `/v1/realtime`.
ADR 0105 capacity modeling is now live on `monitoring-lv3`: the `lv3-capacity-overview` Grafana dashboard, repo-managed platform alert bundle, and both capacity-report entrypoints were re-verified from latest `main` on 2026-03-27, and the official separate-worktree live-apply path now avoids SSH control-socket overflows by using compact per-run directories under `/tmp`.
ADR 0191 immutable guest replacement is now implemented in repository automation: governed stateful and edge services expose a replacement plan, and the production `live-apply-service` path now fails closed unless an operator explicitly acknowledges the narrow in-place exception.
ADR 0185 branch-scoped ephemeral preview environments are now live in the repository and verified against the platform: the repo-managed preview lifecycle can create, converge, validate, and destroy isolated preview VMs on `vmbr20`, and the latest committed-head replay completed on 2026-03-27 with a full create/validate/destroy receipt recorded for merge-to-main promotion.
The repository now also ships ADR 0115 mutation-ledger primitives live on production: the `ledger.events` Postgres schema migration, the `platform.ledger` writer/reader/replay package, the one-time `audit_log` migration helper, and optional dual-write from the existing mutation-audit emitter when `LV3_LEDGER_DSN` is configured; the latest `main` replay on 2026-03-27 re-projected the Windmill runtime ledger env and verified a fresh guest-side `execution.completed` row through both `ledger.events` and the compatibility `audit_log` view.
The repository now also ships ADR 0117 dependency-graph runtime live on production: the `platform.graph` traversal client, `graph.nodes` / `graph.edges` schema migration, repo-managed graph rebuild helpers, `/v1/graph/*` gateway routes, and risk-scorer integration are now verified against the live Windmill, PostgreSQL, and API-gateway runtime after the 2026-03-26 dependency-graph apply.
The repository now also ships ADR 0121 local search live on production: a repo-managed search fabric under `scripts/search_fabric/`, a persisted local index at `build/search-index/documents.json`, the `lv3 search` CLI command, the `/v1/search` API surface, and an ops-portal search panel backed by the same corpus, with the first production receipt recorded on 2026-03-26 after the API gateway and Windmill worker indexing paths were hardened against malformed corpus files.
The repository now also ships ADR 0122 browser-first operator access management: a repo-managed Windmill admin app at `f/lv3/operator_access_admin` backed by the governed ADR 0108 onboarding, off-boarding, reconciliation, inventory, and bounded rich-notes workflows. ADR 0238 is now live there as the AG Grid Community roster for dense operator review, ADR 0241 is the Tiptap-backed inline knowledge editor with markdown persistence, and ADR 0242 adds Shepherd.js-powered guided tours with resumable first-run task flows and direct runbook links for operators.
The repository now also ships ADR 0130 agent state persistence: `platform.agent.AgentStateClient`, the `agent.state` schema migration, and `lv3 agent state show|delete|verify` provide a governed scratch-state path for resumable agent work and post-handoff integrity validation; the first live schema apply from `main` is still pending.
The repository now also ships ADR 0131 multi-agent handoffs: `platform.handoff`, the `handoff.transfers` schema migration, mutation-ledger event types, and `lv3 handoff send|list|view|accept|refuse|complete` provide a durable transfer path between agents and operators, with concurrent burst coverage verified in-repo; the first live transport integration from `main` is still pending.
The repository now also ships ADR 0161 real-time agent coordination: `platform.agent.coordination`, `/v1/platform/agents`, the interactive ops-portal coordination panel, and committed coordination snapshot receipts expose active observation-loop and closure-loop sessions from one shared read model; the first live apply from `main` completed on 2026-03-26 with the coordination surfaces verified on `docker-runtime-lv3`.
The repository now also ships ADR 0113 world-state materializer live on production: the Windmill worker checkout refreshes nine operational surfaces into `world_state.current_view`, the host-side `WorldStateClient()` probe now works directly on `docker-runtime-lv3`, and the latest-main replay on 2026-03-27 verified every surface fresh with `is_expired = false`.
The repository now also ships ADR 0151 n8n automation live on production: the repo-managed `n8n` runtime is active on `docker-runtime-lv3`, PostgreSQL-backed persistence is pinned to `postgres-lv3` at `10.10.10.50`, and `https://n8n.lv3.org` now serves the protected editor with public webhook prefixes through the shared NGINX edge after the first successful `main`-based live apply on 2026-03-26.
The repository now also ships ADR 0148 private web search live on production: the repo-managed SearXNG runtime is active on `docker-runtime-lv3`, the Proxmox host publishes the private operator and agent entrypoint on `http://100.64.0.1`, `search.lv3.org` resolves to that tailnet proxy, and Open WebUI now uses the local SearXNG JSON endpoint for governed web search after the 2026-03-26 live apply.
The repository now also ships ADR 0165 workflow idempotency: `platform.idempotency`, scheduler-side cached result replay, closure-loop trigger scoping, `execution.idempotent_hit` ledger events, and `lv3 intent status <intent_id>` provide deterministic duplicate suppression for platform-managed workflows; the live Windmill converge from `main` on 2026-03-25 now applies and verifies the shared `platform.idempotency_records` schema on `postgres-lv3`.
The repository now also ships ADR 0119 budgeted workflow scheduling live on production: the latest-main Windmill replay on 2026-03-27 re-verified bootstrap-session auth fallback, worker token propagation, the dispatcher and lane scheduler, and both watchdog seed paths plus their enabled schedules on `docker-runtime-lv3`.
The repository now also ships ADR 0204 self-correcting automation loops: the committed correction-loop catalog governs every mutating workflow exactly once, and the 2026-03-28 Windmill observation replay verified `runtime_self_correction_watchers` end to end with the bounded retry budget persisted in durable closure-loop state.
The repository now also ships ADR 0207 anti-corruption layers at provider boundaries: the Hetzner DNS roles translate provider payloads into canonical DNS facts before shared logic consumes them, and the March 28, 2026 latest-main verification proved the same guard through the authoritative build-server validation path, the final local-fallback `remote-validate` replay, and the worker-safe Windmill post-merge fallback.
The repository now also ships ADR 0228 live on production: Windmill is the default browser-first and API-first surface for the repo-managed operations catalog, the latest-main replay keeps the representative `post_merge_gate`, `weekly_capacity_report`, `audit_token_inventory`, and `token_exposure_response` workflows seeded on CE v1.662.0, and the raw-app sync path now strips controller-local ignored frontend artifacts before the worker rebuild.
The repository now also ships ADR 0146 Langfuse observability live on production: `https://langfuse.lv3.org` is published through the shared NGINX edge, the seeded `lv3-agent-observability` project is reachable through the public API, and the 2026-03-26 smoke verification ingested a trace that resolved successfully in the Langfuse UI.
The repository now also ships ADR 0193 Plane task-board automation live on production: `https://tasks.lv3.org` is published through the shared NGINX edge with oauth2-proxy and Keycloak auth, the private controller path is available at `http://100.64.0.1:8011`, and the governed wrapper plus ADR sync path now keep the `lv3-platform` / `ADR` Plane project aligned with repository decision state.
The repository now also ships ADR 0194 Coolify repo-deploy automation live on production: `coolify-lv3` hosts the repo-managed PaaS control plane, `https://coolify.lv3.org` is published behind the shared oauth2-proxy and Keycloak edge, `https://apps.lv3.org` plus `*.apps.lv3.org` route through the shared edge to the Coolify proxy, and the 2026-03-28 merged-main replay re-verified the governed `lv3 deploy-repo` flow with `repo-smoke.apps.lv3.org`.
The repository now also ships ADR 0199 Outline living knowledge wiki live on production: `https://wiki.lv3.org` is published through the shared NGINX edge, the Keycloak-backed `outline.automation` bootstrap path is repo-managed, and the 2026-03-28 merged-main replay re-verified the five governed living-knowledge collections end to end.
The developer portal generator now stamps published docs pages with sensitivity metadata, keeps `RESTRICTED` ADRs and runbooks summary-only in portal output, and leaves `CONFIDENTIAL` documents source-only until a dedicated admin-view path exists.
Portal access is now authentication-by-default on the live platform: `ops.lv3.org`, `docs.lv3.org`, and `changelog.lv3.org` are gated by the shared Keycloak edge auth flow, and Grafana no longer serves anonymous dashboards.
ADR 0239 browser-local search is now live on `main`: `docs.lv3.org` publishes
Pagefind bundles for the generated docs corpus, the header search opens the
Pagefind-backed modal, and the latest exact-main replay re-verified both the
authenticated `302` edge contract and the published search assets on
`nginx-lv3`.
ADR 0134 changelog redaction is now live on the shared authenticated edge: the published deployment-history view masks emails, private IPs, internal hostnames, and inline secret material before changelog data reaches `changelog.lv3.org`.
ADR 0102 security posture reporting is now live on production: the Windmill-compatible weekly security scan can execute end to end from the worker checkout through the private Proxmox jump path, and committed receipts now include both the first production report and the verified worker replay from 2026-03-26.
The repository now also ships ADR 0142 public-surface security scanning: `make public-surface-security-scan ENV=production` writes structured receipts under `receipts/security-scan/`, uses `testssl.sh` and `nuclei` container runners for the live public HTTP or HTTPS surface, and can publish high or critical findings on `platform.security.*`; the live weekly schedule still requires apply from `main`.
The repository now also ships ADR 0129 runbook automation: structured YAML, JSON, and Markdown-front-matter runbooks can execute through `lv3 runbook`, persist resumable run state under `.local/runbooks/runs/`, and reuse the current Windmill plus mutation-audit surfaces.
The repository now also ships ADR 0209 use-case services and thin delivery adapters live on production: the API gateway and ops portal now expose the same shared structured runbook service already used by the CLI and Windmill wrapper, and the 2026-03-28 latest-main replay re-verified `validation-gate-status` end to end through the worker checkout, `api.lv3.org` gateway contract, and the interactive `ops.lv3.org` runbook launcher.
ADR 0244 runtime assurance matrix is now live on production: the authenticated
`api.lv3.org` gateway route and the interactive `ops.lv3.org` portal now render
the same governed service-by-environment assurance rollup from repo-managed
evidence, and the 2026-03-29 exact-main replay re-verified both surfaces end
to end on `docker-runtime-lv3`.
ADR 0255 Matrix Synapse is now live on production from `main`: the public
client API serves at `https://matrix.lv3.org`, the governed controller path
stays available at `http://100.64.0.1:8015`, and the 2026-03-29 exact-main
replay re-verified public login plus the corrected internal-edge HTTPS
assurance path from `monitoring-lv3`.
ADR 0260 Nextcloud is now live on production from `main`: `https://cloud.lv3.org/status.php`
returns `installed=true`, the published `/.well-known/caldav` and
`/.well-known/carddav` routes redirect to `https://cloud.lv3.org/remote.php/dav/`,
and the 2026-03-30 exact-main replay on release `0.177.93` re-verified the
guest-local `10.10.10.20:8084` runtime together with the shared OpenBao
publication-recovery path and the new mutable OCC recovery path for
concurrent Docker interruptions on the shared host.
ADR 0295 shared artifact cache plane is now live on production: `docker-build-lv3`
now serves internal pull-through mirrors on `10.10.10.30:5001-5004`, the
2026-03-29 exact-main replay re-warmed a repo-derived `41`-image seed set, and
`docker buildx inspect lv3-cache --bootstrap` plus the local `apt-cacher-ng`
path were both re-verified afterward.
The repository now also ships ADR 0251 stage-scoped smoke suites fully live on
production: the promotion gate and runtime-assurance scoreboard now require
declared or inherited smoke suites for active environments, the current
exact-main verification on `docker-runtime-lv3` keeps the Windmill worker
checkout aligned with those imports, `config/windmill/scripts/gate-status.py`
returns `status: ok`, the live promotion gate still rejects the stale staged
`grafana` receipt while reporting no required or observed stage-smoke suites
for that receipt, and the authenticated runtime-assurance gateway plus local
ops-portal partials verify cleanly on platform version `0.130.59`.
The repository now also ships ADR 0197 Dify visual workflow canvas fully live on production: `https://agents.lv3.org/healthz` now returns `200`, governed Dify tool calls through `https://api.lv3.org/v1/dify-tools/get-platform-status` re-verified from the latest-main replay, and the linked-worktree smoke export plus Langfuse trace path completed successfully on 2026-03-28.
The repository now also ships ADR 0231 local secret delivery live on production: `docker-runtime-lv3` now serves the control-plane backup path through a repo-managed OpenBao Agent plus systemd credentials, the legacy `/etc/lv3/control-plane-recovery/openbao-backup-token.json` artifact is gone, and the 2026-03-28 replay re-verified a fresh backup generation plus restore drill on `backup-lv3`.
The repository now also ships ADR 0137 crawl policy automation live on production: the shared public edge serves a universal `robots.txt`, emits `X-Robots-Tag: noindex, nofollow` across published hostnames, adds robots meta tags to repository-generated HTML surfaces, and includes `lv3.org` in the shared edge certificate definition.
The repository now also ships the first ADR 0166 canonical error rollout live on production: `config/error-codes.yaml` and `scripts/canonical_errors.py` now normalize repo-managed gateway and platform-context failures behind one trace-id-backed error envelope, and the 2026-03-26 live replay from `main` verified the canonical `AUTH_TOKEN_MISSING` response on both `https://api.lv3.org/v1/health` and `http://100.64.0.1:8010/v1/platform-summary`.

<!-- BEGIN GENERATED: platform-status -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

### Current Values
| Field | Value |
| --- | --- |
| Repository version | `0.177.93` |
| Platform version | `0.130.62` |
| Observed check date | `2026-03-29` |
| Observed OS | `Debian 13` |
| Observed Proxmox version | `9.1.6` |
| Observed kernel | `6.17.13-2-pve` |

### Managed Guests
| VMID | Name | IPv4 | Running |
| --- | --- | --- | --- |
| 110 | `nginx-lv3` | `10.10.10.10` | `true` |
| 120 | `docker-runtime-lv3` | `10.10.10.20` | `true` |
| 130 | `docker-build-lv3` | `10.10.10.30` | `true` |
| 140 | `monitoring-lv3` | `10.10.10.40` | `true` |
| 150 | `postgres-lv3` | `10.10.10.50` | `true` |
| 151 | `postgres-replica-lv3` | `10.10.10.51` | `false` |
| 160 | `backup-lv3` | `10.10.10.60` | `true` |
| 170 | `coolify-lv3` | `10.10.10.70` | `true` |

Template VM: `9000` `debian13-cloud-template`

### Published Service Inventory
| Hostname | Service | Exposure | Owner |
| --- | --- | --- | --- |
| `agents.lv3.org` | `dify` | `edge-published` | `docker-runtime-lv3` |
| `api.lv3.org` | `api-gateway` | `edge-published` | `docker-runtime-lv3` |
| `apps.lv3.org` | `coolify-apps` | `edge-published` | `coolify-lv3` |
| `build.lv3.org` | `docker-build` | `informational-only` | `docker-build-lv3` |
| `chat.lv3.org` | `serverclaw` | `edge-published` | `coolify-lv3` |
| `cloud.lv3.org` | `nextcloud` | `edge-published` | `docker-runtime-lv3` |
| `coolify.lv3.org` | `coolify` | `edge-published` | `coolify-lv3` |
| `database.lv3.org` | `postgres` | `private-only` | `postgres-lv3` |
| `docker.lv3.org` | `docker-runtime` | `informational-only` | `docker-runtime-lv3` |
| `draw.lv3.org` | `excalidraw` | `edge-published` | `docker-runtime-lv3` |
| `git.lv3.org` | `gitea` | `private-only` | `docker-runtime-lv3` |
| `grafana.lv3.org` | `grafana` | `edge-published` | `monitoring-lv3` |
| `headscale.lv3.org` | `headscale` | `edge-published` | `proxmox_florin` |
| `home.lv3.org` | `homepage` | `edge-published` | `docker-runtime-lv3` |
| `langfuse.lv3.org` | `langfuse` | `edge-published` | `docker-runtime-lv3` |
| `logs.lv3.org` | `dozzle` | `edge-published` | `docker-runtime-lv3` |
| `mail.lv3.org` | `mail-platform` | `informational-only` | `docker-runtime-lv3` |
| `matrix.lv3.org` | `matrix-synapse` | `edge-published` | `docker-runtime-lv3` |
| `n8n.lv3.org` | `n8n` | `edge-published` | `docker-runtime-lv3` |
| `nginx.lv3.org` | `nginx-edge` | `edge-static` | `nginx-lv3` |
| `ops.lv3.org` | `ops-portal` | `edge-published` | `docker-runtime-lv3` |
| `proxmox.lv3.org` | `proxmox-ui` | `informational-only` | `proxmox_florin` |
| `realtime.lv3.org` | `realtime` | `edge-published` | `monitoring-lv3` |
| `registry.lv3.org` | `harbor` | `edge-published` | `docker-runtime-lv3` |
| `search.lv3.org` | `searxng` | `private-only` | `docker-runtime-lv3` |
| `sso.lv3.org` | `keycloak` | `edge-published` | `docker-runtime-lv3` |
| `status.lv3.org` | `status-page` | `edge-published` | `docker-runtime-lv3` |
| `tasks.lv3.org` | `plane` | `edge-published` | `docker-runtime-lv3` |
| `uptime.lv3.org` | `uptime-kuma` | `edge-published` | `docker-runtime-lv3` |
| `vault.lv3.org` | `vaultwarden` | `private-only` | `docker-runtime-lv3` |
| `wiki.lv3.org` | `outline` | `edge-published` | `docker-runtime-lv3` |

### Latest Live-Apply Evidence
| Capability | Receipt |
| --- | --- |
| `agent_coordination` | `2026-03-26-adr-0161-real-time-agent-coordination-map-live-apply` |
| `api_gateway` | `2026-03-29-adr-0245-declared-to-live-service-attestation-live-apply` |
| `artifact_cache_plane` | `2026-03-29-adr-0295-shared-artifact-cache-plane-mainline-live-apply` |
| `backup_coverage` | `2026-03-29-adr-0271-backup-coverage-ledger-mainline-live-apply` |
| `backup_vm` | `2026-03-22-adr-0029-backup-vm-live-apply` |
| `bounded_command_execution` | `2026-03-28-adr-0227-bounded-command-execution-mainline-live-apply` |
| `budgeted_workflow_scheduler` | `2026-03-27-adr-0119-budgeted-workflow-scheduler-mainline-live-apply` |
| `build_telemetry` | `2026-03-22-adr-0028-build-telemetry-live-apply` |
| `canonical_publication_models` | `2026-03-28-adr-0210-canonical-domain-models-live-apply` |
| `capability_contracts` | `2026-03-28-adr-0205-capability-contracts-before-product-selection-mainline-live-apply` |
| `capacity_classes` | `2026-03-27-adr-0192-capacity-classes-live-apply` |
| `capacity_model` | `2026-03-27-adr-0105-capacity-model-mainline-live-apply` |
| `certificate_lifecycle` | `2026-03-27-adr-0101-certificate-lifecycle-main-live-apply` |
| `command_catalog` | `2026-03-28-adr-0230-policy-decisions-live-apply` |
| `config_merge` | `2026-03-26-adr-0158-config-merge-live-apply` |
| `control_metadata_witness` | `2026-03-27-adr-0181-control-metadata-witness-live-apply` |
| `control_plane_lanes` | `2026-03-22-adr-0045-control-plane-communication-lanes-live-apply` |
| `control_plane_recovery` | `2026-03-28-adr-0231-local-secret-delivery-live-apply` |
| `coolify` | `2026-03-29-adr-0224-coolify-dns-mirror-edge-and-education-mainline-live-apply` |
| `coolify_apps` | `2026-03-29-adr-0224-coolify-dns-mirror-edge-and-education-mainline-live-apply` |
| `deadlock_detector` | `2026-03-26-adr-0162-deadlock-detector-live-apply` |
| `dependency_graph_runtime` | `2026-03-26-adr-0117-dependency-graph-live-apply` |
| `dify` | `2026-03-28-adr-0197-dify-mainline-live-apply` |
| `docker_runtime` | `2026-03-22-adr-0023-docker-runtime-live-apply` |
| `docs_portal` | `2026-03-29-adr-0239-browser-local-search-post-merge-replay` |
| `dozzle` | `2026-03-26-adr-0150-dozzle-live-apply` |
| `excalidraw` | `2026-03-27-adr-0202-excalidraw-auto-generated-architecture-diagrams-live-apply` |
| `failure_domain_policy` | `2026-03-27-adr-0184-failure-domain-labels-live-apply` |
| `fixture_pools` | `2026-03-28-adr-0186-prewarmed-fixture-pools-live-apply` |
| `gitea` | `2026-03-26-adr-0143-gitea-live-apply` |
| `gitea_actions_runners` | `2026-03-28-adr-0229-gitea-actions-runners-live-apply` |
| `gotenberg` | `2026-03-30-adr-0278-gotenberg-mainline-live-apply` |
| `guest_network_policy` | `2026-03-22-adr-0067-guest-network-policy-live-apply` |
| `harbor` | `2026-03-29-adr-0201-harbor-mainline-live-apply` |
| `homepage` | `2026-03-26-adr-0152-homepage-live-apply` |
| `host_control_loops` | `2026-03-28-adr-0226-host-control-loops-mainline-live-apply` |
| `https_tls_assurance` | `2026-03-29-adr-0255-matrix-synapse-mainline-live-apply` |
| `identity_taxonomy` | `2026-03-22-adr-0046-identity-classes-live-apply` |
| `immutable_guest_replacement` | `2026-03-27-adr-0191-immutable-guest-replacement-live-apply` |
| `keycloak` | `2026-03-26-adr-0171-fault-injection-live-apply` |
| `keycloak_operator_access` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `langfuse` | `2026-03-26-adr-0146-langfuse-live-apply` |
| `local_search_and_indexing_fabric` | `2026-03-29-adr-0239-browser-local-search-post-merge-replay` |
| `log_queryability_canary` | `2026-03-28-adr-0250-log-queryability-canary-live-apply` |
| `mail_platform` | `2026-03-24-keycloak-password-reset-mail-live-apply` |
| `matrix_synapse` | `2026-03-29-adr-0255-matrix-synapse-mainline-live-apply` |
| `mattermost` | `2026-03-23-adr-0077-compose-runtime-secrets-live-apply` |
| `monitoring` | `2026-03-28-adr-0250-log-queryability-canary-live-apply` |
| `mutation_audit` | `2026-03-23-adr-0066-mutation-audit-live-apply` |
| `mutation_ledger` | `2026-03-27-adr-0115-mutation-ledger-mainline-live-apply` |
| `n8n` | `2026-03-29-adr-0259-n8n-serverclaw-connector-fabric-mainline-live-apply` |
| `netbox` | `2026-03-23-adr-0077-compose-runtime-secrets-live-apply` |
| `network_impairment_matrix` | `2026-03-27-adr-0189-network-impairment-matrix-live-apply` |
| `nextcloud` | `2026-03-30-adr-0260-nextcloud-personal-data-plane-mainline-live-apply` |
| `nomad_scheduler` | `2026-03-29-adr-0232-nomad-mainline-live-apply` |
| `notification_profiles` | `2026-03-22-adr-0050-notification-profiles-live-apply` |
| `ntopng` | `2026-03-22-adr-0059-ntopng-live-apply` |
| `observation_to_action_closure_loop` | `2026-03-26-adr-0126-observation-to-action-closure-loop-live-apply` |
| `ollama` | `2026-03-27-adr-0176-inventory-sharding-mainline-live-apply` |
| `open_webui` | `2026-03-25-adr-0145-open-webui-ollama-connector-live-apply` |
| `openbao` | `2026-03-27-adr-0101-certificate-lifecycle-main-live-apply` |
| `openbao_operator_entity` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `openbao_operator_policy` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access` | `2026-03-28-adr-0238-operator-grid-live-apply` |
| `operator_access_composition_root` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_guided_onboarding` | `2026-03-28-adr-0242-guided-human-onboarding-live-apply` |
| `operator_access_inventory` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_ports` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_quarterly_review` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_review` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_runbooks` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_validation` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `operator_access_workflows` | `2026-03-28-adr-0206-ports-and-adapters-live-apply` |
| `ops_portal` | `2026-03-29-adr-0245-declared-to-live-service-attestation-live-apply` |
| `ops_portal_visualizations` | `2026-03-29-adr-0240-operator-visualization-panels-mainline-live-apply` |
| `outline` | `2026-03-28-adr-0199-outline-living-knowledge-wiki-mainline-live-apply` |
| `plane` | `2026-03-28-adr-0193-plane-mainline-live-apply` |
| `platform_context` | `2026-03-28-adr-0198-semantic-rag-mainline-live-apply` |
| `platform_event_taxonomy` | `2026-03-26-adr-0124-platform-event-taxonomy-live-apply` |
| `policy_validation` | `2026-03-28-adr-0230-policy-decisions-live-apply` |
| `portainer` | `2026-03-22-adr-0055-portainer-live-apply` |
| `postgres_vm` | `2026-03-22-adr-0026-postgres-vm-live-apply` |
| `preview_environment` | `2026-03-27-adr-0185-ws-0185-live-apply-20260327t191234z` |
| `promotion_pipeline` | `2026-03-29-adr-0251-stage-smoke-promotion-gates-mainline-live-apply` |
| `provider_boundaries` | `2026-03-28-adr-0207-anti-corruption-layers-at-provider-boundaries-live-apply` |
| `public_edge_publication` | `2026-03-29-adr-0255-matrix-synapse-mainline-live-apply` |
| `public_endpoint_admission_control` | `2026-03-29-adr-0273-public-endpoint-admission-control-mainline-live-apply` |
| `realtime` | `2026-03-27-adr-0196-netdata-realtime-streaming-metrics-live-apply` |
| `remote_build_gateway` | `2026-03-29-adr-0265-immutable-validation-snapshots-mainline-live-apply` |
| `restore_verification` | `2026-03-29-adr-0272-restore-readiness-mainline-live-apply` |
| `route_dns_assertion_ledger` | `2026-03-29-adr-0273-public-endpoint-admission-control-mainline-live-apply` |
| `runtime_container_telemetry` | `2026-03-22-adr-0040-runtime-container-telemetry-live-apply` |
| `runtime_state_semantics` | `2026-03-28-adr-0246-runtime-state-semantics-live-apply` |
| `searxng` | `2026-03-26-adr-0148-searxng-live-apply` |
| `secret_rotation` | `2026-03-23-adr-0065-secret-rotation-live-apply` |
| `security_posture_reporting` | `2026-03-26-adr-0102-security-posture-live-apply` |
| `seed_data_snapshots` | `2026-03-28-adr-0187-anonymized-seed-data-snapshots-mainline-live-apply` |
| `self_correcting_automation_loops` | `2026-03-28-adr-0204-self-correcting-automation-loops-live-apply` |
| `semaphore` | `2026-03-25-adr-0149-semaphore-live-apply` |
| `server_resident_operations` | `2026-03-28-adr-0224-server-resident-operations-default-control-live-apply` |
| `server_resident_reconciliation` | `2026-03-28-adr-0225-server-resident-reconciliation-via-ansible-pull-live-apply` |
| `serverclaw` | `2026-03-30-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply` |
| `serverclaw_memory` | `2026-03-29-adr-0263-serverclaw-memory-substrate-mainline-live-apply` |
| `service_redundancy` | `2026-03-27-adr-0188-failover-rehearsal-gate-live-apply` |
| `session_logout_authority` | `2026-03-29-adr-0248-session-logout-authority-mainline-live-apply` |
| `shared_policy_packs` | `2026-03-28-adr-0211-shared-policy-packs-and-rule-registries-mainline-live-apply` |
| `short_lived_credentials_and_mtls` | `2026-03-22-adr-0047-short-lived-credentials-live-apply` |
| `signed_release_bundles` | `2026-03-28-adr-0233-signed-release-bundles-mainline-live-apply` |
| `stage_smoke_suites` | `2026-03-29-adr-0251-stage-smoke-promotion-gates-mainline-live-apply` |
| `staging_environment` | `2026-03-27-adr-0183-staging-live-apply` |
| `step_ca` | `2026-03-27-adr-0101-certificate-lifecycle-main-live-apply` |
| `tempo_tracing` | `2026-03-22-adr-0053-tempo-traces-live-apply` |
| `uptime_kuma` | `2026-03-22-adr-0027-uptime-kuma-live-apply` |
| `validation_gate` | `2026-03-29-adr-0264-failure-domain-isolated-validation-lanes-mainline-live-apply` |
| `validation_runner_contracts` | `2026-03-29-adr-0266-validation-runner-capability-contracts-mainline-live-apply` |
| `vaultwarden` | `2026-03-29-adr-0252-route-and-dns-publication-assertion-ledger-mainline-live-apply` |
| `windmill` | `2026-03-29-adr-0228-windmill-default-operations-surface-mainline-live-apply` |
| `world_state_materializer` | `2026-03-27-adr-0113-world-state-materializer-mainline-live-apply` |
<!-- END GENERATED: platform-status -->

The current access posture is:

```text
ops SSH + sudo for routine host work
routine host SSH over the Proxmox Tailscale IP
ops@pam for routine Proxmox administration
lv3-automation@pve API token for durable Proxmox object management
short-lived `step-ca` SSH certificates accepted on the Proxmox host and managed guests
short-lived OpenBao AppRole artifacts refreshed on each converge and post-verification run
ops SSH + sudo for guest VMs
root key-only break-glass on the Proxmox host
root disabled for guest SSH
password SSH disabled on host and guests
```

## Control-plane lanes

<!-- BEGIN GENERATED: control-plane-lanes -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

### Lane Summary
| Lane | Title | Transport | Surfaces | Primary Rule |
| --- | --- | --- | --- | --- |
| `command` | Command Lane | `ssh` | 2 | Use SSH only for command-lane access. |
| `api` | API Lane | `https` | 15 | Default new APIs to internal-only or operator-only publication. |
| `message` | Message Lane | `authenticated_submission` | 2 | Submit platform mail through the internal mail platform rather than arbitrary external SMTP relays. |
| `event` | Event Lane | `mixed` | 14 | Event sinks must be documented and intentionally reachable. |

### Current Governed Surfaces
| Surface | Lane | Kind | Endpoint |
| --- | --- | --- | --- |
| `proxmox-host-ops-ssh` | `command` | `ssh_endpoint` | `ops@100.64.0.1` |
| `guest-ops-ssh-via-proxmox-jump` | `command` | `ssh_endpoint` | `ops@10.10.10.0/24 via ProxyJump through ops@100.64.0.1` |
| `platform-api-gateway` | `api` | `service_api` | `https://api.lv3.org/v1` |
| `proxmox-management-api` | `api` | `management_api` | `https://100.64.0.1:8006/api2/json` |
| `step-ca-api` | `api` | `service_api` | `https://100.64.0.1:9443` |
| `openbao-api` | `api` | `service_api` | `https://100.64.0.1:8200` |
| `windmill-api` | `api` | `service_api` | `http://100.64.0.1:8005/api` |
| `netbox-api` | `api` | `service_api` | `http://100.64.0.1:8004/api/` |
| `portainer-api` | `api` | `service_api` | `https://100.64.0.1:9444` |
| `vaultwarden-api` | `api` | `service_api` | `https://vault.lv3.org` |
| `mail-gateway-api` | `api` | `service_api` | `http://10.10.10.20:8081` |
| `mattermost-operator-api` | `api` | `service_api` | `http://100.64.0.1:8066/api/v4` |
| `headscale-control-plane` | `api` | `service_api` | `https://headscale.lv3.org` |
| `langfuse-observability-api` | `api` | `service_api` | `https://langfuse.lv3.org/api/public` |
| `open-webui-operator-workbench` | `api` | `service_api` | `http://100.64.0.1:8008` |
| `ollama-local-inference-api` | `api` | `service_api` | `http://10.10.10.20:11434` |
| `platform-context-api` | `api` | `service_api` | `http://100.64.0.1:8010` |
| `mail-platform-submission` | `message` | `mail_submission` | `10.10.10.20:1587` |
| `proxmox-host-operator-notifications` | `message` | `notification_profile` | `lv3-ops-email sendmail endpoint with catch-all matcher to baditaflorin@gmail.com` |
| `stalwart-mail-events` | `event` | `webhook` | `http://10.10.10.20:8081/webhooks/stalwart` |
| `mattermost-incoming-webhooks` | `event` | `webhook` | `http://10.10.10.20:8065/hooks/<managed-id>` |
| `platform-finding-subjects` | `event` | `event_subject` | `platform.findings.*` |
| `platform-watchdog-subjects` | `event` | `event_subject` | `platform.watchdog.*` |
| `platform-api-request-events` | `event` | `event_subject` | `platform.api.request` |
| `platform-drift-subjects` | `event` | `event_subject` | `platform.drift.*` |
| `platform-security-subjects` | `event` | `event_subject` | `platform.security.*` |
| `maintenance-window-subjects` | `event` | `event_subject` | `platform.maintenance.*` |
| `platform-backup-subjects` | `event` | `event_subject` | `platform.backup.restore-verification.*` |
| `platform-world-state-events` | `event` | `event_subject` | `platform.world_state.refreshed` |
| `platform-ledger-events` | `event` | `event_subject` | `platform.ledger.event_written` |
| `platform-agent-events` | `event` | `event_subject` | `platform.agent.*` |
| `platform-execution-events` | `event` | `event_subject` | `platform.execution.*` |
| `platform-config-merge-events` | `event` | `event_subject` | `platform.config.*` |

### API Publication Tiers
| Tier | Title | Surfaces | Summary |
| --- | --- | --- | --- |
| `internal-only` | Internal-Only | 18 | Reachable only from LV3 private networks, loopback paths, or explicitly trusted control-plane hosts. |
| `operator-only` | Operator-Only | 8 | Reachable only from approved operator devices over private access such as Tailscale. |
| `public-edge` | Public Edge | 3 | Intentionally published on a public domain through the named edge model. |

### Classified API And Webhook Surfaces
| Surface | Tier | Lane | Endpoint | Reachability |
| --- | --- | --- | --- | --- |
| `platform-api-gateway` | `public-edge` | `api` | `https://api.lv3.org/v1` | Reachable on https://api.lv3.org through the NGINX edge, with Keycloak bearer-token authentication enforced by the gateway itself. |
| `headscale-control-plane` | `public-edge` | `api` | `https://headscale.lv3.org` | Reachable on https://headscale.lv3.org through the shared NGINX edge, with node-registration keys and API keys enforcing access to the mesh control plane. |
| `proxmox-management-api` | `operator-only` | `api` | `https://100.64.0.1:8006/api2/json` | Reachable only over the Proxmox host Tailscale address on port 8006. |
| `step-ca-api` | `internal-only` | `api` | `https://100.64.0.1:9443` | Reachable through the Proxmox host Tailscale proxy for approved controller and trust-bootstrap traffic only. |
| `openbao-api` | `internal-only` | `api` | `https://100.64.0.1:8200` | Reachable through the Proxmox host Tailscale proxy and the runtime loopback listener, with client-certificate authentication on the external path. |
| `windmill-api` | `operator-only` | `api` | `http://100.64.0.1:8005/api` | Reachable only through the Proxmox host Tailscale proxy on port 8005. |
| `netbox-api` | `operator-only` | `api` | `http://100.64.0.1:8004/api/` | Reachable only through the Proxmox host Tailscale proxy on port 8004. |
| `portainer-api` | `operator-only` | `api` | `https://100.64.0.1:9444` | Reachable only through the Proxmox host Tailscale proxy on port 9444. |
| `vaultwarden-api` | `operator-only` | `api` | `https://vault.lv3.org` | Reachable only through the Proxmox host Tailscale proxy at https://vault.lv3.org with the internal CA trust chain. |
| `mail-gateway-api` | `internal-only` | `api` | `http://10.10.10.20:8081` | Reachable only on the LV3 private guest network at docker-runtime-lv3:8081. |
| `mattermost-operator-api` | `operator-only` | `api` | `http://100.64.0.1:8066/api/v4` | Reachable only through the Proxmox host Tailscale proxy on port 8066. |
| `langfuse-observability-api` | `public-edge` | `api` | `https://langfuse.lv3.org/api/public` | Reachable on https://langfuse.lv3.org/api/public through the shared NGINX edge, authenticated with project-scoped API keys for ingestion and Keycloak-backed browser login for operators. |
| `open-webui-operator-workbench` | `operator-only` | `api` | `http://100.64.0.1:8008` | Reachable only through the Proxmox host Tailscale proxy on port 8008. |
| `ollama-local-inference-api` | `internal-only` | `api` | `http://10.10.10.20:11434` | Reachable only on the LV3 private guest network at docker-runtime-lv3:11434. |
| `platform-context-api` | `operator-only` | `api` | `http://100.64.0.1:8010` | Reachable only through the Proxmox host Tailscale proxy on port 8010 and requires the controller-local bearer token. |
| `stalwart-mail-events` | `internal-only` | `event` | `http://10.10.10.20:8081/webhooks/stalwart` | Reachable only from the private mail-platform stack on docker-runtime-lv3. |
| `mattermost-incoming-webhooks` | `internal-only` | `event` | `http://10.10.10.20:8065/hooks/<managed-id>` | Reachable on the private Mattermost runtime at docker-runtime-lv3:8065, with mirrored webhook ids retained under .local/mattermost for controlled routing. |
| `platform-finding-subjects` | `internal-only` | `event` | `platform.findings.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-watchdog-subjects` | `internal-only` | `event` | `platform.watchdog.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-api-request-events` | `internal-only` | `event` | `platform.api.request` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-drift-subjects` | `internal-only` | `event` | `platform.drift.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-security-subjects` | `internal-only` | `event` | `platform.security.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `maintenance-window-subjects` | `internal-only` | `event` | `platform.maintenance.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-backup-subjects` | `internal-only` | `event` | `platform.backup.restore-verification.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-world-state-events` | `internal-only` | `event` | `platform.world_state.refreshed` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-ledger-events` | `internal-only` | `event` | `platform.ledger.event_written` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-agent-events` | `internal-only` | `event` | `platform.agent.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-execution-events` | `internal-only` | `event` | `platform.execution.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
| `platform-config-merge-events` | `internal-only` | `event` | `platform.config.*` | Published only on the private docker-runtime-lv3 NATS runtime and consumed by approved internal subscribers. |
<!-- END GENERATED: control-plane-lanes -->

The current host security posture is:

```text
Proxmox firewall enabled for host management traffic
SSH and port 8006 limited to declared management source ranges
Tailscale is the primary management path for the host
Let's Encrypt certificate active for proxmox.lv3.org
sendmail notification endpoint and catch-all matcher configured
ops@pam protected by TOTP
```

The current monitoring posture is:

```text
InfluxDB 2 running on 10.10.10.40:8086
Grafana running on 10.10.10.40:3000
Proxmox metric server influxdb-http active and writing to the proxmox bucket
Grafana published at https://grafana.lv3.org via the NGINX edge
Grafana folder LV3 provisioned from repo
Grafana dashboard LV3 Platform Overview provisioned from repo
Per-VM dashboards provisioned for nginx-lv3, docker-runtime-lv3, docker-build-lv3, and monitoring-lv3
Overview and VM dashboards together cover the Proxmox host plus nginx-lv3, docker-runtime-lv3, docker-build-lv3, and monitoring-lv3 individually
NGINX guest telemetry now includes loopback-only stub_status plus Telegraf shipping into InfluxDB
Dashboard now also includes nginx service panels for active connections, requests per second, accepts and handled rates, and connection states
Docker runtime monitoring now includes container-level CPU, memory, network, health, and snapshot panels for docker-runtime-lv3
```

The current Docker runtime posture is:

```text
Docker Engine 29.3.0 installed from Docker's official Debian repository
Docker Compose plugin v5.1.1 available through `docker compose`
Docker live-restore enabled
json-file logging capped at 10m with 5 retained files
ops present in the local docker group on docker-runtime-lv3
telegraf active on docker-runtime-lv3 with Docker socket access for container telemetry
Uptime Kuma running from /opt/uptime-kuma and published at https://uptime.lv3.org
repo-local Uptime Kuma auth and monitor management material stored under .local/uptime-kuma
Portainer running from /opt/portainer and published privately through the Proxmox host Tailscale path at https://100.64.0.1:9444
repo-local Portainer bootstrap and controller auth material stored under .local/portainer
```

The current PostgreSQL posture is:

```text
PostgreSQL running on postgres-lv3 at 10.10.10.50
database.lv3.org resolves to the Proxmox host Tailscale IP 100.64.0.1
database access is proxied only on Tailscale port 5432
65.108.75.123:5432 remains closed on the public IPv4
guest firewall only accepts proxied PostgreSQL traffic from 10.10.10.1/32
```

The current backup posture is:

```text
backup-lv3 runs Proxmox Backup Server on 10.10.10.60
PBS datastore proxmox is mounted at /mnt/datastore/proxmox on the dedicated backup disk
Proxmox storage lv3-backup-pbs points to 10.10.10.60:8007
nightly job backup-lv3-nightly protects VMIDs 110, 120, 130, 140, 150, and 170 at 02:30
the backup coverage ledger now shows 6 of 7 governed assets protected; backup-lv3 remains uncovered until lv3-backup-offsite exists
control-plane recovery archives from docker-runtime-lv3 now land on /srv/control-plane-recovery/runtime/docker-runtime-lv3/latest
the mirrored controller recovery bundle now lives under /srv/control-plane-recovery/controller
the scheduled restore drill on backup-lv3 last passed at 2026-03-22T21:29:48Z
restore-oriented verification is documented and includes artifact listing plus test backup validation
this is still same-host recovery, not off-host disaster recovery
```

## Documents

<!-- BEGIN GENERATED: document-index -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

### Core Documents
- [Changelog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md)
- [Release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md)
- [Repository map](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/repository-map.md)
- [Assistant operator guide](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/assistant-operator-guide.md)
- [Release process](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-process.md)
- [Workstreams registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
- [Workstreams guide](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/README.md)

### Runbooks
- [Add A New Service](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/add-a-new-service.md)
- [Agent Capability Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/agent-capability-policy.md)
- [Agent Coordination Map](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/agent-coordination-map.md)
- [Agent Handoff Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/agent-handoff-protocol.md)
- [Agent Observation Loop](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/agent-observation-loop.md)
- [Agent Session Workspace Isolation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/agent-session-workspace-isolation.md)
- [Agent State Store](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/agent-state-store.md)
- [Agent Tool Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/agent-tool-registry.md)
- [Ansible Collection Development](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/ansible-collection-development.md)
- [Ansible Inventory Sharding](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/ansible-inventory-sharding.md)
- [Ansible Role Idempotency CI](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/ansible-role-idempotency-ci.md)
- [Artifact Cache Runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/artifact-cache-runtime.md)
- [Backup Coverage Ledger](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/backup-coverage-ledger.md)
- [Backup Restore Verification](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/backup-restore-verification.md)
- [Bounded Command Execution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/bounded-command-execution.md)
- [Break-Glass Recovery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/break-glass-recovery.md)
- [Break-Glass References](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/break-glass.md)
- [Budgeted Workflow Scheduler](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/budgeted-workflow-scheduler.md)
- [Canonical Truth Assembly](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/canonical-truth-assembly.md)
- [Capability Contract Catalog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/capability-contract-catalog.md)
- [Capacity Classes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/capacity-classes.md)
- [Capacity Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/capacity-model.md)
- [Certificate Expired](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/cert-expired.md)
- [Change Risk Scoring](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/change-risk-scoring.md)
- [Circuit Breaker Operations](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/circuit-breaker-operations.md)
- [Command Catalog And Approval Gates](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/command-catalog-and-approval-gates.md)
- [Complete Security Baseline Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/complete-security-baseline.md)
- [Compose Runtime Secrets Injection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/compose-secrets-injection.md)
- [Config Merge Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/config-merge-protocol.md)
- [Configure API Gateway](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-api-gateway.md)
- [Configure Backup VM](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-backup-vm.md)
- [Configure Build Artifact Cache](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-build-artifact-cache.md)
- [Configure Control-Plane Recovery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-control-plane-recovery.md)
- [Configure Coolify](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-coolify.md)
- [Configure Dify](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-dify.md)
- [Configure Docker Build VM](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-docker-build-vm.md)
- [Configure Docker Runtime Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-docker-runtime.md)
- [Configure Dozzle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-dozzle.md)
- [Configure Edge Publication](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-edge-publication.md)
- [Configure Excalidraw](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-excalidraw.md)
- [Configure Gitea](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-gitea.md)
- [Configure Gotenberg](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-gotenberg.md)
- [Configure Guest Network Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-guest-network-policy.md)
- [Configure Harbor](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-harbor.md)
- [Configure Headscale](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-headscale.md)
- [Configure Homepage](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-homepage.md)
- [Configure Host Control Loops](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-host-control-loops.md)
- [Configure Keycloak](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-keycloak.md)
- [Configure Langfuse](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-langfuse.md)
- [Configure Mail Platform](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-mail-platform.md)
- [Configure Matrix Synapse](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-matrix-synapse.md)
- [Configure Mattermost](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-mattermost.md)
- [Configure n8n](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-n8n.md)
- [Configure NetBox](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-netbox.md)
- [Configure Netdata](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-netdata.md)
- [Configure Nextcloud](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-nextcloud.md)
- [Configure Nomad](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-nomad.md)
- [Configure Ntfy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-ntfy.md)
- [Configure ntopng Private Flow Visibility](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-ntopng.md)
- [Configure Ollama](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-ollama.md)
- [Configure Open WebUI](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-open-webui.md)
- [Configure OpenBao](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-openbao.md)
- [Configure Outline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-outline.md)
- [Configure Plane](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-plane.md)
- [Configure Portainer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-portainer.md)
- [Configure PostgreSQL VM Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-postgres-vm.md)
- [Configure Proxmox Network Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-proxmox-network.md)
- [Configure Public Ingress Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md)
- [Configure SearXNG](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-searxng.md)
- [Configure Semaphore](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-semaphore.md)
- [Configure ServerClaw](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-serverclaw.md)
- [Configure step-ca](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-step-ca.md)
- [Configure Storage And Backups](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-storage-and-backups.md)
- [Configure Tailscale Private Access](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-tailscale-access.md)
- [Configure Vaultwarden](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-vaultwarden.md)
- [Configure Windmill](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-windmill.md)
- [Container Image Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/container-image-policy.md)
- [Control-Plane Communication Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/control-plane-communication-lanes.md)
- [Controller Automation Toolkit](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/controller-automation-toolkit.md)
- [Controller-Local Secrets And Preflight Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/controller-local-secrets-and-preflight.md)
- [Cross-Workstream Interface Contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/cross-workstream-interface-contracts.md)
- [Data Retention](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/data-retention.md)
- [Deadlock Detection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/deadlock-detection.md)
- [Dependency Graph Operations](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/dependency-graph.md)
- [Dependency Wave Parallel Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/dependency-wave-parallel-apply.md)
- [Deploy a Service](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/deploy-a-service.md)
- [Deploy Uptime Kuma](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/deploy-uptime-kuma.md)
- [Deployment History Portal](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/deployment-history-portal.md)
- [Developer Portal](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/developer-portal.md)
- [Disaster Recovery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/disaster-recovery.md)
- [Docker Check Runners](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/docker-check-runners.md)
- [Docker Publication Assurance Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/docker-publication-assurance.md)
- [Docker Runtime Disk Pressure](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/docker-runtime-disk-pressure.md)
- [Drift Detection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/drift-detection.md)
- [Dry-Run Semantic Diff Engine](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/dry-run-semantic-diff-engine.md)
- [Environment Promotion Pipeline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/environment-promotion-pipeline.md)
- [Ephemeral Fixtures](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/ephemeral-fixtures.md)
- [Failure-Domain Labels And Anti-Affinity Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/failure-domain-policy.md)
- [Fault Injection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/fault-injection.md)
- [Generate Status Documents](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/generate-status-documents.md)
- [Graceful Degradation Modes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/graceful-degradation-modes.md)
- [Harden Access Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/harden-access.md)
- [Health Composite Index](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/health-composite-index.md)
- [Health Probe Contracts Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/health-probe-contracts.md)
- [HTTP Security Headers](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/http-security-headers.md)
- [HTTPS And TLS Assurance](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/https-tls-assurance.md)
- [Identity Taxonomy And Managed Principals](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/identity-taxonomy-and-managed-principals.md)
- [Immutable Guest Replacement](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/immutable-guest-replacement.md)
- [Incident Triage Engine](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/incident-triage-engine.md)
- [Initial Access Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/initial-access.md)
- [Install Proxmox Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/install-proxmox.md)
- [Integration Test Suite](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/integration-test-suite.md)
- [Intent Conflict Resolution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/intent-conflict-resolution.md)
- [Intent Queue Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/intent-queue.md)
- [Runbook: Keycloak Down](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/keycloak-down.md)
- [Live Apply Merge Train](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/live-apply-merge-train.md)
- [Live Apply Receipts And Verification Evidence](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/live-apply-receipts-and-verification-evidence.md)
- [LLM Implementation Prompts — ADRs 0082–0091](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/llm-implementation-prompts.md)
- [Log Queryability Canary](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/log-queryability-canary.md)
- [Maintenance Windows](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/maintenance-windows.md)
- [Monitoring Stack Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md)
- [Mutation Audit Log](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/mutation-audit-log.md)
- [Mutation Ledger](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/mutation-ledger.md)
- [Network Impairment Matrix](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/network-impairment-matrix.md)
- [Network Policy Reference](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/network-policy-reference.md)
- [Observation-to-Action Closure Loop](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/observation-to-action-closure-loop.md)
- [Runbook: OpenBao Sealed](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/openbao-sealed.md)
- [Operator Offboarding](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/operator-offboarding.md)
- [Operator Onboarding](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/operator-onboarding.md)
- [Ops Portal Down](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/ops-portal-down.md)
- [Packer VM Templates](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/packer-vm-templates.md)
- [Parallel Intent Batch Validation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/parallel-intent-batch-validation.md)
- [Per-VM Concurrency Budgets](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/per-vm-concurrency-budgets.md)
- [Agentic Control-Plane Roadmap](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/plan-agentic-control-plane.md)
- [Plan: Human Navigation, Deployment Lifecycle, And Platform Hardening (ADRs 0072–0081)](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/plan-human-navigation-and-deployment-lifecycle.md)
- [Roadmap Runbook: IaC Potency, Build Server Offload, and User Ergonomics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/plan-iac-potency-and-build-server.md)
- [Platform Hardening And Agentic Extensibility Roadmap](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/plan-platform-hardening-and-agentic-extensibility.md)
- [Visual And Agent Operations Roadmap](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/plan-visual-agent-operations.md)
- [Platform API Error Codes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/platform-api-error-codes.md)
- [Platform CLI](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/platform-cli.md)
- [Platform Event Taxonomy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/platform-event-taxonomy.md)
- [Platform Facts Library](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/platform-facts-library.md)
- [Platform Manifest](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/platform-manifest.md)
- [Platform Operations Portal](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/platform-operations-portal.md)
- [Platform Release Management](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/platform-release-management.md)
- [Platform Timeout Hierarchy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/platform-timeout-hierarchy.md)
- [Playbook Execution Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/playbook-execution-model.md)
- [Portal Authentication By Default](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/portal-authentication-by-default.md)
- [Runbook: Postgres Down](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/postgres-down.md)
- [PostgreSQL Failover Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/postgres-failover.md)
- [Prepare Mail Platform Rollout](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/prepare-mail-platform-rollout.md)
- [Preview Environments](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/preview-environments.md)
- [Private-First API Publication](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/private-first-api-publication.md)
- [Provision Guests Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/provision-guests.md)
- [Proxmox API Automation Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/proxmox-api-automation.md)
- [Public Status Page](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/public-status-page.md)
- [Public Surface Security Scan](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/public-surface-security-scan.md)
- [Published Artifact Secret Scanning](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/published-artifact-secret-scanning.md)
- [RAG Platform Context](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/rag-platform-context.md)
- [Remote Build Gateway](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/remote-build-gateway.md)
- [Repair Guest Netplan MAC Drift](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/repair-guest-netplan-mac-drift.md)
- [Replaceability Scorecards](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/replaceability-scorecards.md)
- [Distributed Resource Lock Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/resource-lock-registry.md)
- [Retry Taxonomy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/retry-taxonomy.md)
- [Rotate Certificates](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/rotate-certificates.md)
- [Run Namespace Partitioning](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/run-namespace-partitioning.md)
- [Runbook Automation Executor](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/runbook-automation-executor.md)
- [Runtime Assurance Matrix](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/runtime-assurance-matrix.md)
- [Runtime Assurance Scoreboard](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/runtime-assurance-scoreboard.md)
- [Scaffold A New Service](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/scaffold-new-service.md)
- [Search Indexing Fabric](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/search-indexing-fabric.md)
- [Secret Rotation And Lifecycle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/secret-rotation-and-lifecycle.md)
- [Security Posture Reporting](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/security-posture-reporting.md)
- [Seed Data Snapshots](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/seed-data-snapshots.md)
- [Server-Resident Reconciliation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/server-resident-reconciliation.md)
- [ServerClaw Memory Substrate](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/serverclaw-memory-substrate.md)
- [Service Capability Catalog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/service-capability-catalog.md)
- [Service Dependency Graph Runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/service-dependency-graph-runtime.md)
- [Service Redundancy Tier Matrix](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/service-redundancy-tier-matrix.md)
- [Service Uptime Contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/service-uptime-contracts.md)
- [Signed Release Bundles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/signed-release-bundles.md)
- [Runbook: SLO Fast Burn](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/slo-fast-burn.md)
- [SLO Tracking](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/slo-tracking.md)
- [Speculative Workflow Execution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/speculative-workflow-execution.md)
- [Staging And Production Topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/staging-and-production-topology.md)
- [Staging Environment](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/staging-environment.md)
- [Structured Log Contract](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/structured-log-contract.md)
- [Subdomain Exposure Audit](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/subdomain-exposure-audit.md)
- [Subdomain Governance](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/subdomain-governance.md)
- [Synthetic Transaction Replay](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/synthetic-transaction-replay.md)
- [OpenTofu VM Import](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/tofu-vm-import.md)
- [OpenTofu VM Lifecycle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/tofu-vm-lifecycle.md)
- [Token Exposure Response](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/token-exposure-response.md)
- [Token Lifecycle Management](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/token-lifecycle-management.md)
- [Validate Repository Automation Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/validate-repository-automation.md)
- [Validation Gate Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/validation-gate.md)
- [VM-Scoped Execution Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/vm-scoped-execution-lanes.md)
- [Windmill Default Operations Surface](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/windmill-default-operations-surface.md)
- [Windmill Operator Access Admin](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/windmill-operator-access-admin.md)
- [Workflow Catalog And Execution Contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/workflow-catalog-and-execution-contracts.md)
- [Workflow Idempotency](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/workflow-idempotency.md)
- [World-State Materializer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/world-state-materializer.md)

### ADRs
- [ADR 0001: Bootstrap Dedicated Host With Ansible](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0001-bootstrap-dedicated-host-with-ansible.md)
- [ADR 0002: Target Proxmox VE 9 on Debian 13](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0002-target-proxmox-ve-9-on-debian-13.md)
- [ADR 0003: Prefer Hetzner Rescue Plus Installimage For Bootstrap](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0003-prefer-hetzner-rescue-plus-installimage-for-bootstrap.md)
- [ADR 0004: Install Proxmox VE From Debian Packages](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0004-install-proxmox-ve-from-debian-packages.md)
- [ADR 0005: Single-Node First Topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0005-single-node-first-topology.md)
- [ADR 0006: Security Baseline For Proxmox Host](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0006-security-baseline-for-proxmox-host.md)
- [ADR 0007: Agent-Oriented Access Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0007-agent-oriented-access-model.md)
- [ADR 0008: Versioning Model For Repo And Host](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0008-versioning-model-for-repo-and-host.md)
- [ADR 0009: DRY And Solid Engineering Principles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0009-dry-and-solid-engineering-principles.md)
- [ADR 0010: Initial Proxmox VM Topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0010-initial-proxmox-vm-topology.md)
- [ADR 0011: Monitoring VM With Grafana And Proxmox Metrics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0011-monitoring-vm-with-grafana-and-proxmox-metrics.md)
- [ADR 0012: Proxmox Host Bridge And NAT Network](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0012-proxmox-host-bridge-and-nat-network.md)
- [ADR 0013: Public Ingress And Guest Egress Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0013-public-ingress-and-guest-egress-model.md)
- [ADR 0014: Operator Access To Private Guest Network](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0014-operator-access-to-private-guest-network.md)
- [ADR 0015: lv3.org DNS And Subdomain Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0015-lv3-org-dns-and-subdomain-model.md)
- [ADR 0016: Provision Guests From Debian 13 Cloud Template](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0016-provision-guests-from-debian-13-cloud-template.md)
- [ADR 0017: ADR Lifecycle And Implementation Metadata](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0017-adr-lifecycle-and-implementation-metadata.md)
- [ADR 0018: Non-Root Operations For Host And Guests](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0018-non-root-operations-for-host-and-guests.md)
- [ADR 0019: Parallel ADR Delivery With Workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0019-parallel-adr-delivery-with-workstreams.md)
- [ADR 0020: Initial Storage And Backup Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0020-initial-storage-and-backup-model.md)
- [ADR 0021: Public Subdomain Publication At The NGINX Edge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0021-public-subdomain-publication-at-the-nginx-edge.md)
- [ADR 0022: NGINX Guest Observability Via Telegraf And Stub Status](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0022-nginx-guest-observability-via-telegraf-and-stub-status.md)
- [ADR 0023: Docker Runtime VM Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0023-docker-runtime-vm-baseline.md)
- [ADR 0024: Docker Guest Security Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0024-docker-guest-security-baseline.md)
- [ADR 0025: Compose-Managed Runtime Stacks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0025-compose-managed-runtime-stacks.md)
- [ADR 0026: Dedicated PostgreSQL VM Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0026-dedicated-postgresql-vm-baseline.md)
- [ADR 0027: Uptime Kuma On The Docker Runtime VM](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0027-uptime-kuma-on-the-docker-runtime-vm.md)
- [ADR 0028: Docker Build VM Build Count And Duration Telemetry Via CLI Wrapper Events](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0028-docker-build-vm-build-count-telemetry-via-cli-wrapper-events.md)
- [ADR 0029: Dedicated Backup VM With Local PBS](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0029-dedicated-backup-vm-with-local-pbs.md)
- [ADR 0030: Role Interface Contracts And Defaults Boundaries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0030-role-interface-contracts-and-defaults-boundaries.md)
- [ADR 0031: Repository Validation Pipeline For Automation Changes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0031-repository-validation-pipeline-for-automation-changes.md)
- [ADR 0032: Shared Guest Observability Framework](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0032-shared-guest-observability-framework.md)
- [ADR 0033: Declarative Service Topology Catalog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0033-declarative-service-topology-catalog.md)
- [ADR 0034: Controller-Local Secret Manifest And Preflight](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0034-controller-local-secret-manifest-and-preflight.md)
- [ADR 0035: Workflow Catalog And Machine-Readable Execution Contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0035-workflow-catalog-and-machine-readable-execution-contracts.md)
- [ADR 0036: Live Apply Receipts And Verification Evidence](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0036-live-apply-receipts-and-verification-evidence.md)
- [ADR 0037: Schema-Validated Repository Data Models](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0037-schema-validated-repository-data-models.md)
- [ADR 0038: Generated Status Documents From Canonical State](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0038-generated-status-documents-from-canonical-state.md)
- [ADR 0039: Shared Controller Automation Toolkit](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0039-shared-controller-automation-toolkit.md)
- [ADR 0040: Docker Runtime Container Telemetry Via Telegraf Docker Input](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0040-docker-runtime-container-telemetry-via-telegraf-docker-input.md)
- [ADR 0041: Dockerized Mail Platform For Server Delivery, API Automation, And Grafana Observability](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0041-dockerized-mail-platform-for-server-delivery-api-and-observability.md)
- [ADR 0042: step-ca For SSH And Internal TLS](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0042-step-ca-for-ssh-and-internal-tls.md)
- [ADR 0043: OpenBao For Secrets, Transit, And Dynamic Credentials](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0043-openbao-for-secrets-transit-and-dynamic-credentials.md)
- [ADR 0044: Windmill For Agent And Operator Workflows](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0044-windmill-for-agent-and-operator-workflows.md)
- [ADR 0045: Control-Plane Communication Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0045-control-plane-communication-lanes.md)
- [ADR 0046: Identity Classes For Humans, Services, And Agents](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0046-identity-classes-for-humans-services-and-agents.md)
- [ADR 0047: Short-Lived Credentials And Internal mTLS](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0047-short-lived-credentials-and-internal-mtls.md)
- [ADR 0048: Command Catalog And Approval Gates](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0048-command-catalog-and-approval-gates.md)
- [ADR 0049: Private-First API Publication Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0049-private-first-api-publication-model.md)
- [ADR 0050: Transactional Email And Notification Profiles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0050-transactional-email-and-notification-profiles.md)
- [ADR 0051: Control-Plane Backup, Recovery, And Break-Glass](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0051-control-plane-backup-recovery-and-break-glass.md)
- [ADR 0052: Centralized Log Aggregation With Grafana Loki](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0052-centralized-log-aggregation-with-grafana-loki.md)
- [ADR 0053: OpenTelemetry Traces And Service Maps With Grafana Tempo](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0053-opentelemetry-traces-and-service-maps-with-grafana-tempo.md)
- [ADR 0054: NetBox For Topology, IPAM, And Inventory](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0054-netbox-for-topology-ipam-and-inventory.md)
- [ADR 0055: Portainer For Read-Mostly Docker Runtime Operations](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0055-portainer-for-read-mostly-docker-runtime-operations.md)
- [ADR 0056: Keycloak For Operator And Agent SSO](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0056-keycloak-for-operator-and-agent-sso.md)
- [ADR 0057: Mattermost For ChatOps And Operator-Agent Collaboration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0057-mattermost-for-chatops-and-operator-agent-collaboration.md)
- [ADR 0058: NATS JetStream For Internal Event Bus And Agent Coordination](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0058-nats-jetstream-for-internal-event-bus-and-agent-coordination.md)
- [ADR 0059: ntopng For Private Network Flow Visibility](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0059-ntopng-for-private-network-flow-visibility.md)
- [ADR 0060: Open WebUI For Operator And Agent Workbench](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0060-open-webui-for-operator-and-agent-workbench.md)
- [ADR 0061: GlitchTip For Application Exceptions And Task Failures](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0061-glitchtip-for-application-exceptions-and-task-failures.md)
- [ADR 0062: Ansible Role Composability And DRY Defaults](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0062-ansible-role-composability-and-dry-defaults.md)
- [ADR 0063: Centralised Vars And Computed Facts Library](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0063-centralised-vars-and-computed-facts-library.md)
- [ADR 0064: Health Probe Contracts For All Services](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0064-health-probe-contracts-for-all-services.md)
- [ADR 0065: Secret Rotation Automation With OpenBao](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0065-secret-rotation-automation-with-openbao.md)
- [ADR 0066: Structured Mutation Audit Log](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0066-structured-mutation-audit-log.md)
- [ADR 0067: Guest Network Policy Enforcement](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0067-guest-network-policy-enforcement.md)
- [ADR 0068: Container Image Policy And Supply Chain Integrity](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0068-container-image-policy-and-supply-chain-integrity.md)
- [ADR 0069: Agent Tool Registry And Governed Tool Calls](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0069-agent-tool-registry-and-governed-tool-calls.md)
- [ADR 0070: Retrieval-Augmented Context For Platform Queries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0070-rag-context-for-platform-queries.md)
- [ADR 0071: Agent Observation Loop And Autonomous Drift Detection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0071-agent-observation-loop-and-drift-detection.md)
- [ADR 0072: Staging And Production Environment Topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0072-staging-and-production-environment-topology.md)
- [ADR 0073: Environment Promotion Gate And Deployment Pipeline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0073-environment-promotion-gate-and-deployment-pipeline.md)
- [ADR 0074: Platform Operations Portal](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0074-platform-operations-portal.md)
- [ADR 0075: Service Capability Catalog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0075-service-capability-catalog.md)
- [ADR 0076: Subdomain Governance And DNS Lifecycle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0076-subdomain-governance-and-dns-lifecycle.md)
- [ADR 0077: Compose Runtime Secrets Injection Via OpenBao Agent](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0077-compose-runtime-secrets-injection.md)
- [ADR 0078: Service Scaffold Generator](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0078-service-scaffold-generator.md)
- [ADR 0079: Playbook Decomposition And Shared Execution Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0079-playbook-decomposition-and-shared-execution-model.md)
- [ADR 0080: Maintenance Window And Change Suppression Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0080-maintenance-window-and-change-suppression-protocol.md)
- [ADR 0081: Platform Changelog And Deployment History Portal](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0081-platform-changelog-and-deployment-history.md)
- [ADR 0082: Remote Build Execution Gateway](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0082-remote-build-execution-gateway.md)
- [ADR 0083: Docker-Based Check Runner on Build Server](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0083-docker-based-check-runner.md)
- [ADR 0084: Packer VM Template Pipeline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0084-packer-vm-template-pipeline.md)
- [ADR 0085: OpenTofu IaC for VM Lifecycle Management](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0085-opentofu-vm-lifecycle.md)
- [ADR 0086: Ansible Collection Packaging and Versioned Role Distribution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0086-ansible-collection-packaging.md)
- [ADR 0087: Repository Validation Gate (Pre-Push and CI)](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0087-repository-validation-gate.md)
- [ADR 0088: Ephemeral Infrastructure Fixtures](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0088-ephemeral-infrastructure-fixtures.md)
- [ADR 0089: Build Artifact Cache and Layer Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0089-build-artifact-cache.md)
- [ADR 0090: Unified Platform CLI (`lv3`)](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0090-unified-platform-cli.md)
- [ADR 0091: Continuous Drift Detection and Reconciliation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0091-continuous-drift-detection.md)
- [ADR 0092: Unified Platform API Gateway](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0092-unified-platform-api-gateway.md)
- [ADR 0093: Interactive Ops Portal with Live Actions](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0093-interactive-ops-portal.md)
- [ADR 0094: Developer Portal and Service Documentation Site](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0094-developer-portal-and-documentation-site.md)
- [ADR 0095: Unified Search Across Platform Services](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0095-unified-platform-search.md)
- [ADR 0096: SLO Definitions and Error Budget Tracking](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0096-slo-definitions-and-error-budget-tracking.md)
- [ADR 0097: Alerting Routing and On-Call Runbook Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0097-alerting-routing-and-oncall-runbook-model.md)
- [ADR 0098: Postgres High Availability and Automated Failover](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0098-postgres-high-availability.md)
- [ADR 0099: Automated Backup Restore Verification](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0099-automated-backup-restore-verification.md)
- [ADR 0100: Formal RTO/RPO Targets and Disaster Recovery Playbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0100-rto-rpo-targets-and-disaster-recovery-playbook.md)
- [ADR 0101: Automated Certificate Lifecycle Management](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0101-automated-certificate-lifecycle-management.md)
- [ADR 0102: Security Posture Reporting and Benchmark Drift](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0102-security-posture-reporting.md)
- [ADR 0103: Data Classification and Retention Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0103-data-classification-and-retention-policy.md)
- [ADR 0104: Service Dependency Graph and Failure Propagation Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0104-service-dependency-graph.md)
- [ADR 0105: Platform Capacity Model and Resource Quota Enforcement](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0105-platform-capacity-model.md)
- [ADR 0106: Ephemeral Environment Lifecycle and Teardown Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0106-ephemeral-environment-lifecycle-policy.md)
- [ADR 0107: Platform Extension Model for Adding New Services](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0107-platform-extension-model.md)
- [ADR 0108: Operator Onboarding and Off-boarding Workflow](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0108-operator-onboarding-and-offboarding.md)
- [ADR 0109: Public Status Page](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0109-public-status-page.md)
- [ADR 0110: Platform Versioning, Release Notes, and Upgrade Path](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0110-platform-versioning-and-upgrade-path.md)
- [ADR 0111: End-to-End Integration Test Suite](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0111-end-to-end-integration-test-suite.md)
- [ADR 0112: Deterministic Goal Compiler](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0112-deterministic-goal-compiler.md)
- [ADR 0113: World-State Materializer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0113-world-state-materializer.md)
- [ADR 0114: Rule-Based Incident Triage Engine](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0114-rule-based-incident-triage-engine.md)
- [ADR 0115: Event-Sourced Mutation Ledger](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0115-event-sourced-mutation-ledger.md)
- [ADR 0116: Change Risk Scoring Without LLMs](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0116-change-risk-scoring.md)
- [ADR 0117: Service Dependency Graph As First-Class Runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0117-service-dependency-graph-runtime.md)
- [ADR 0118: Replayable Failure Case Library](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0118-replayable-failure-case-library.md)
- [ADR 0119: Budgeted Workflow Scheduler](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0119-budgeted-workflow-scheduler.md)
- [ADR 0120: Dry-Run Semantic Diff Engine](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0120-dry-run-semantic-diff-engine.md)
- [ADR 0121: Local Search and Indexing Fabric](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0121-local-search-and-indexing-fabric.md)
- [ADR 0122: Windmill Operator Access Admin Surface](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0122-windmill-operator-access-admin.md)
- [ADR 0123: Service Uptime Contracts And Monitor-Backed Health](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0123-service-uptime-contracts-and-monitor-backed-health.md)
- [ADR 0124: Platform Event Taxonomy And Canonical NATS Topics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0124-platform-event-taxonomy-and-canonical-nats-topics.md)
- [ADR 0125: Agent Capability Bounds and Autonomous Action Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0125-agent-capability-bounds-and-autonomous-action-policy.md)
- [ADR 0126: Observation-to-Action Closure Loop](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0126-observation-to-action-closure-loop.md)
- [ADR 0127: Intent Deduplication and Conflict Resolution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0127-intent-deduplication-and-conflict-resolution.md)
- [ADR 0128: Platform Health Composite Index](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0128-platform-health-composite-index.md)
- [ADR 0129: Runbook Automation Executor](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0129-runbook-automation-executor.md)
- [ADR 0130: Agent State Persistence Across Workflow Boundaries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0130-agent-state-persistence-across-workflow-boundaries.md)
- [ADR 0131: Multi-Agent Handoff Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0131-multi-agent-handoff-protocol.md)
- [ADR 0132: Self-Describing Platform Manifest](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0132-self-describing-platform-manifest.md)
- [ADR 0133: Portal Authentication by Default](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0133-portal-authentication-by-default.md)
- [ADR 0134: Changelog Portal Content Redaction](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0134-changelog-portal-content-redaction.md)
- [ADR 0135: Developer Portal Sensitivity Classification](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0135-developer-portal-sensitivity-classification.md)
- [ADR 0136: HTTP Security Headers Hardening](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0136-http-security-headers-hardening.md)
- [ADR 0137: Robots.txt and Crawl Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0137-robots-and-crawl-policy.md)
- [ADR 0138: Published Artifact Secret Scanning](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0138-published-artifact-secret-scanning.md)
- [ADR 0139: Subdomain Exposure Audit and Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0139-subdomain-exposure-audit-and-registry.md)
- [ADR 0140: Grafana Public Access Hardening](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0140-grafana-public-access-hardening.md)
- [ADR 0141: API Token Lifecycle and Exposure Response](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0141-api-token-lifecycle-and-exposure-response.md)
- [ADR 0142: Public Surface Automated Security Scan](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0142-public-surface-automated-security-scan.md)
- [ADR 0143: Gitea for Self-Hosted Git and Webhook-Driven Automation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0143-gitea-for-self-hosted-git-and-ci.md)
- [ADR 0144: Headscale For Zero-Trust Mesh VPN](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0144-headscale-for-zero-trust-mesh-vpn.md)
- [ADR 0145: Ollama for Local LLM Inference API](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0145-ollama-for-local-llm-inference.md)
- [ADR 0146: Langfuse For Agent Observability](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0146-langfuse-for-agent-observability.md)
- [ADR 0147: Vaultwarden for Operator Credential Management](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0147-vaultwarden-for-operator-credential-management.md)
- [ADR 0148: SearXNG for Agent Web Search](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0148-searxng-for-agent-web-search.md)
- [ADR 0149: Semaphore For Ansible Job Management UI And API](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0149-semaphore-for-ansible-job-management-ui-and-api.md)
- [ADR 0150: Dozzle for Real-Time Container Log Access](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0150-dozzle-for-real-time-container-log-access.md)
- [ADR 0151: n8n for Webhook and API Integration Automation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0151-n8n-for-webhook-and-api-integration-automation.md)
- [ADR 0152: Homepage for Unified Service Dashboard](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0152-homepage-for-unified-service-dashboard.md)
- [ADR 0153: Distributed Resource Lock Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0153-distributed-resource-lock-registry.md)
- [ADR 0154: VM-Scoped Parallel Execution Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0154-vm-scoped-parallel-execution-lanes.md)
- [ADR 0155: Intent Queue with Release-Triggered Scheduling](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0155-intent-queue-with-release-triggered-scheduling.md)
- [ADR 0156: Agent Session Workspace Isolation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0156-agent-session-workspace-isolation.md)
- [ADR 0157: Per-VM Concurrency Budget and Resource Reservation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0157-per-vm-concurrency-budget-and-resource-reservation.md)
- [ADR 0158: Conflict-Free Configuration Merge Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0158-conflict-free-configuration-merge-protocol.md)
- [ADR 0159: Speculative Parallel Execution with Compensating Transactions](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0159-speculative-parallel-execution-with-compensating-transactions.md)
- [ADR 0160: Parallel Dry-Run Fan-Out for Intent Batch Validation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0160-parallel-dry-run-fan-out-for-intent-batch-validation.md)
- [ADR 0161: Real-Time Agent Coordination Map](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0161-real-time-agent-coordination-map.md)
- [ADR 0162: Distributed Deadlock Detection and Resolution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0162-distributed-deadlock-detection-and-resolution.md)
- [ADR 0163: Platform-Wide Retry Taxonomy and Exponential Backoff](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0163-platform-wide-retry-taxonomy-and-exponential-backoff.md)
- [ADR 0163: Proxmox Break-Glass SSH Port](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0163-proxmox-break-glass-ssh-port.md)
- [ADR 0163: Repository Structure Index for Agent Discovery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0163-repository-structure-index.md)
- [ADR 0164: ADR Metadata Index and Fast Discovery Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0164-adr-metadata-index.md)
- [ADR 0164: Circuit Breaker Pattern for External Service Calls](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0164-circuit-breaker-pattern-for-external-service-calls.md)
- [ADR 0165: Playbook and Role Metadata Standard for Agent Discovery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0165-playbook-role-metadata-standard.md)
- [ADR 0165: Workflow Idempotency Keys and Double-Execution Prevention](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0165-workflow-idempotency-keys-and-double-execution-prevention.md)
- [ADR 0166: Canonical Configuration Locations Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0166-canonical-configuration-locations.md)
- [ADR 0166: Canonical Error Response Format and Error Code Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0166-canonical-error-response-format-and-error-code-registry.md)
- [ADR 0167: Agent Handoff and Context Preservation Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0167-agent-handoff-and-context-preservation.md)
- [ADR 0167: Graceful Degradation Mode Declarations](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0167-graceful-degradation-mode-declarations.md)
- [ADR 0168: Ansible Role Idempotency CI Enforcement](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0168-ansible-role-idempotency-ci-enforcement.md)
- [ADR 0168: Automated Enforcement of Agent Discovery and Handoff Standards](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0168-automated-enforcement-of-agent-standards.md)
- [ADR 0169: Structured Log Field Contract](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0169-structured-log-field-contract.md)
- [ADR 0170: Platform-Wide Timeout Hierarchy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0170-platform-wide-timeout-hierarchy.md)
- [ADR 0171: Controlled Fault Injection for Resilience Validation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0171-controlled-fault-injection-for-resilience-validation.md)
- [ADR 0172: Watchdog Escalation and Stale Job Self-Healing](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0172-watchdog-escalation-and-stale-job-self-healing.md)
- [ADR 0173: Workstream Surface Ownership Manifest](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0173-workstream-surface-ownership-manifest.md)
- [ADR 0174: Integration-Only Canonical Truth Assembly](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0174-integration-only-canonical-truth-assembly.md)
- [ADR 0175: Cross-Workstream Interface Contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0175-cross-workstream-interface-contracts.md)
- [ADR 0176: Inventory Sharding and Host-Scoped Ansible Execution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0176-inventory-sharding-and-host-scoped-ansible-execution.md)
- [ADR 0177: Run Namespace Partitioning for Parallel Tooling](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0177-run-namespace-partitioning-for-parallel-tooling.md)
- [ADR 0178: Dependency Wave Manifests for Parallel Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0178-dependency-wave-manifests-for-parallel-apply.md)
- [ADR 0179: Service Redundancy Tier Matrix](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0179-service-redundancy-tier-matrix.md)
- [ADR 0180: Standby Capacity Reservation and Placement Rules](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0180-standby-capacity-reservation-and-placement-rules.md)
- [ADR 0181: Off-Host Witness and Control Metadata Replication](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0181-off-host-witness-and-control-metadata-replication.md)
- [ADR 0182: Live Apply Merge Train and Rollback Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0182-live-apply-merge-train-and-rollback-bundle.md)
- [ADR 0183: Auxiliary Cloud Failure Domain for Witness, Recovery, and Burst Capacity](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0183-auxiliary-cloud-failure-domain-for-witness-recovery-and-burst-capacity.md)
- [ADR 0183: Keycloak Uses Shared-Mail-Network Internal Submission](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0183-keycloak-mail-network-internal-submission.md)
- [ADR 0183: Multi-Environment Live Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0183-multi-environment-live-lanes.md)
- [ADR 0184: Failure-Domain Labels and Anti-Affinity Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0184-failure-domain-labels-and-anti-affinity-policy.md)
- [ADR 0185: Branch-Scoped Ephemeral Preview Environments](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0185-branch-scoped-ephemeral-preview-environments.md)
- [ADR 0186: Prewarmed Fixture Pools and Lease-Based Ephemeral Capacity](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0186-prewarmed-fixture-pools-and-lease-based-ephemeral-capacity.md)
- [ADR 0187: Anonymized Seed Data Snapshots for Repeatable Tests](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0187-anonymized-seed-data-snapshots-for-repeatable-tests.md)
- [ADR 0188: Failover Rehearsal Gate for Redundancy Tiers](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0188-failover-rehearsal-gate-for-redundancy-tiers.md)
- [ADR 0189: Network Impairment Test Matrix for Staging and Previews](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0189-network-impairment-test-matrix-for-staging-and-previews.md)
- [ADR 0190: Synthetic Transaction Replay for Capacity and Recovery Validation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0190-synthetic-transaction-replay-for-capacity-and-recovery-validation.md)
- [ADR 0191: Immutable Guest Replacement for Stateful and Edge Services](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0191-immutable-guest-replacement-for-stateful-and-edge-services.md)
- [ADR 0192: Separate Capacity Classes for Standby, Recovery, and Preview Workloads](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0192-separate-capacity-classes-for-standby-recovery-and-preview-workloads.md)
- [ADR 0193: Plane Kanban Task Board](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0193-plane-kanban-task-board.md)
- [ADR 0194: Coolify PaaS Deploy From Repo](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0194-coolify-paas-deploy-from-repo.md)
- [ADR 0196: Netdata Realtime Streaming Metrics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0196-netdata-realtime-streaming-metrics.md)
- [ADR 0197: Dify - Visual LLM Workflow and Agent Canvas](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0197-dify-visual-llm-workflow-canvas.md)
- [ADR 0198: Qdrant Vector Search for Semantic Platform RAG](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0198-qdrant-vector-search-semantic-rag.md)
- [ADR 0199: Outline Living Knowledge Wiki](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0199-outline-living-knowledge-wiki.md)
- [ADR 0201: Harbor - Vulnerability-Scanning Container Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0201-harbor-container-registry-with-cve-scanning.md)
- [ADR 0202: Excalidraw Auto Generated Architecture Diagrams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0202-excalidraw-auto-generated-architecture-diagrams.md)
- [ADR 0204: Self-Correcting Automation Loops](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0204-self-correcting-automation-loops.md)
- [ADR 0205: Capability Contracts Before Product Selection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0205-capability-contracts-before-product-selection.md)
- [ADR 0206: Ports And Adapters For External Integrations](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0206-ports-and-adapters-for-external-integrations.md)
- [ADR 0207: Anti-Corruption Layers At Provider Boundaries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0207-anti-corruption-layers-at-provider-boundaries.md)
- [ADR 0208: Dependency Direction And Composition Roots](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0208-dependency-direction-and-composition-roots.md)
- [ADR 0209: Use-Case Services And Thin Delivery Adapters](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0209-use-case-services-and-thin-delivery-adapters.md)
- [ADR 0210: Canonical Domain Models Over Vendor Schemas](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0210-canonical-domain-models-over-vendor-schemas.md)
- [ADR 0211: Shared Policy Packs And Rule Registries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0211-shared-policy-packs-and-rule-registries.md)
- [ADR 0212: Replaceability Scorecards And Vendor Exit Plans](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0212-replaceability-scorecards-and-vendor-exit-plans.md)
- [ADR 0213: Architecture Fitness Functions In The Validation Gate](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0213-architecture-fitness-functions-in-the-validation-gate.md)
- [ADR 0214: Production And Staging Cells As The Unit Of High Availability](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0214-production-and-staging-cells-as-the-unit-of-high-availability.md)
- [ADR 0215: Node Role Taxonomy For Bootstrap, Control, State, Edge, Workload, Observability, Recovery, And Build](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0215-node-role-taxonomy-for-bootstrap-control-state-edge-workload-observability-recovery-and-build.md)
- [ADR 0216: Service Criticality Rings For Foundation, Core, Supporting, And Peripheral Functions](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0216-service-criticality-rings-for-foundation-core-supporting-and-peripheral-functions.md)
- [ADR 0217: One-Way Environment Data Flow And Replication Authority](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0217-one-way-environment-data-flow-and-replication-authority.md)
- [ADR 0218: Relational Database Replication And Single-Writer Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0218-relational-database-replication-and-single-writer-policy.md)
- [ADR 0219: Data-Class Replication Policies For Queues, Object Stores, Search, Cache, Secrets, And Time-Series](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0219-data-class-replication-policies-for-queues-object-stores-search-cache-secrets-and-time-series.md)
- [ADR 0220: Bootstrap And Recovery Sequencing For Environment Cells](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0220-bootstrap-and-recovery-sequencing-for-environment-cells.md)
- [ADR 0221: Role-Based Node Pools And Placement Boundaries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0221-role-based-node-pools-and-placement-boundaries.md)
- [ADR 0222: Failover Authority And Service Endpoint Separation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0222-failover-authority-and-service-endpoint-separation.md)
- [ADR 0223: Canonical HA Topology Catalog And Reusable Automation Profiles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0223-canonical-ha-topology-catalog-and-reusable-automation-profiles.md)
- [ADR 0224: Self-Service Repo Intake And Agent-Assisted Deployments](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md)
- [ADR 0224: Server-Resident Operations As The Default Control Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0224-server-resident-operations-as-the-default-control-model.md)
- [ADR 0225: Server-Resident Reconciliation Via Ansible Pull](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0225-server-resident-reconciliation-via-ansible-pull.md)
- [ADR 0226: Systemd Units, Timers, And Paths For Host-Resident Control Loops](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md)
- [ADR 0227: Bounded Command Execution Via Systemd-Run And Approved Wrappers](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md)
- [ADR 0228: Windmill As The Default Browser-And-API Operations Surface](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md)
- [ADR 0229: Gitea Actions Runners For On-Platform Validation And Release Preparation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md)
- [ADR 0230: Policy Decisions Via Open Policy Agent And Conftest](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0230-policy-decisions-via-open-policy-agent-and-conftest.md)
- [ADR 0231: Local Secret Delivery Via OpenBao Agent And Systemd Credentials](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials.md)
- [ADR 0232: Nomad For Durable Batch And Long-Running Internal Jobs](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md)
- [ADR 0233: Signed Release Bundles Via Gitea Releases And Cosign](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md)
- [ADR 0234: Shared Human App Shell And Navigation Via PatternFly](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0234-shared-human-app-shell-and-navigation-via-patternfly.md)
- [ADR 0235: Cross-Application Launcher And Favorites Via PatternFly Application Launcher](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md)
- [ADR 0236: Server-State And Mutation Feedback Via TanStack Query](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md)
- [ADR 0237: Schema-First Human Forms Via React Hook Form And Zod](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0237-schema-first-human-forms-via-react-hook-form-and-zod.md)
- [ADR 0238: Data-Dense Operator Grids Via AG Grid Community](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md)
- [ADR 0239: Browser-Local Search Experience Via Pagefind](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0239-browser-local-search-experience-via-pagefind.md)
- [ADR 0240: Operator Visualization Panels Via Apache ECharts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0240-operator-visualization-panels-via-apache-echarts.md)
- [ADR 0241: Rich Content And Inline Knowledge Editing Via Tiptap](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md)
- [ADR 0242: Guided Human Onboarding Via Shepherd Tours](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0242-guided-human-onboarding-via-shepherd-tours.md)
- [ADR 0243: Component Stories, Accessibility, And UI Contracts Via Storybook, Playwright, And Axe-Core](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0243-component-stories-accessibility-and-ui-contracts-via-storybook-playwright-and-axe-core.md)
- [ADR 0244: Runtime Assurance Matrix Per Service And Environment](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0244-runtime-assurance-matrix-per-service-and-environment.md)
- [ADR 0245: Declared-To-Live Service Attestation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0245-declared-to-live-service-attestation.md)
- [ADR 0246: Startup, Readiness, Liveness, And Degraded State Semantics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0246-startup-readiness-liveness-and-degraded-state-semantics.md)
- [ADR 0247: Authenticated Browser Journey Verification Via Playwright](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0247-authenticated-browser-journey-verification-via-playwright.md)
- [ADR 0248: Session And Logout Authority Across Keycloak, Oauth2-Proxy, And App Surfaces](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md)
- [ADR 0249: HTTPS And TLS Assurance Via Blackbox Exporter And testssl.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0249-https-and-tls-assurance-via-blackbox-exporter-and-testssl-sh.md)
- [ADR 0250: Log Ingestion And Queryability Canaries Via Loki Canary](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0250-log-ingestion-and-queryability-canaries-via-loki-canary.md)
- [ADR 0251: Stage-Scoped Smoke Suites And Promotion Gates](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- [ADR 0252: Route And DNS Publication Assertion Ledger](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0252-route-and-dns-publication-assertion-ledger.md)
- [ADR 0253: Unified Runtime Assurance Scoreboard And Rollup](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0253-unified-runtime-assurance-scoreboard-and-rollup.md)
- [ADR 0254: ServerClaw As A Distinct Self-Hosted Agent Product On LV3](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- [ADR 0255: Matrix Synapse As The Canonical ServerClaw Conversation Hub](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md)
- [ADR 0256: Mautrix Bridges For External Chat Channel Adapters](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0256-mautrix-bridges-for-external-chat-channel-adapters.md)
- [ADR 0257: OpenClaw-Compatible SKILL.md Packs And Workspace Precedence For ServerClaw](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md)
- [ADR 0258: Temporal As The Durable ServerClaw Session Orchestrator](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0258-temporal-as-the-durable-serverclaw-session-orchestrator.md)
- [ADR 0259: n8n As The External App Connector Fabric For ServerClaw](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md)
- [ADR 0260: Nextcloud As The Canonical Personal Data Plane For ServerClaw](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0260-nextcloud-as-the-canonical-personal-data-plane-for-serverclaw.md)
- [ADR 0261: Playwright Browser Runners For ServerClaw Web Action And Extraction](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md)
- [ADR 0262: OpenFGA And Keycloak For Delegated ServerClaw Capability Authorization](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md)
- [ADR 0263: Qdrant, PostgreSQL, And Local Search As The ServerClaw Memory Substrate](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md)
- [ADR 0264: Failure-Domain-Isolated Validation Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0264-failure-domain-isolated-validation-lanes.md)
- [ADR 0265: Immutable Validation Snapshots For Remote Builders And Schema Checks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md)
- [ADR 0266: Validation Runner Capability Contracts And Environment Attestation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0266-validation-runner-capability-contracts-and-environment-attestation.md)
- [ADR 0267: Expiring Gate Bypass Waivers With Structured Reason Codes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0267-expiring-gate-bypass-waivers-with-structured-reason-codes.md)
- [ADR 0268: Fresh-Worktree Bootstrap Manifests For Generated Artifacts And Local Inputs](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md)
- [ADR 0269: Vulnerability Budgets And Image-Host Freshness Promotion Gates](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0269-vulnerability-budgets-and-image-host-freshness-promotion-gates.md)
- [ADR 0270: Docker Publication Self-Healing And Port-Programming Assertions](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0270-docker-publication-self-healing-and-port-programming-assertions.md)
- [ADR 0271: Backup Coverage Assertion Ledger And Backup-Of-Backup Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0271-backup-coverage-assertion-ledger-and-backup-of-backup-policy.md)
- [ADR 0272: Restore Readiness Ladders And Stateful Warm-Up Verification Profiles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0272-restore-readiness-ladders-and-stateful-warm-up-verification-profiles.md)
- [ADR 0273: Public Endpoint Admission Control For DNS Catalog And Certificate Concordance](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0273-public-endpoint-admission-control-for-dns-catalog-and-certificate-concordance.md)
- [ADR 0274: Governed Base Image Mirrors And Warm Caches For Repo Deployments](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0274-governed-base-image-mirrors-and-warm-caches-for-repo-deployments.md)
- [ADR 0274: MinIO As The S3-Compatible Object Storage Layer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0274-minio-as-the-s3-compatible-object-storage-layer.md)
- [ADR 0275: Apache Tika Server For Document Text Extraction In The RAG Pipeline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline.md)
- [ADR 0276: NATS JetStream As The Platform Event Bus](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0276-nats-jetstream-as-the-platform-event-bus.md)
- [ADR 0277: Typesense As The Full-Text Search Engine For Internal Structured Data](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0277-typesense-as-the-full-text-search-engine-for-internal-structured-data.md)
- [ADR 0278: Gotenberg As The Document-To-PDF Rendering Service](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0278-gotenberg-as-the-document-to-pdf-rendering-service.md)
- [ADR 0279: Grist As The No-Code Operational Spreadsheet Database](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md)
- [ADR 0280: Changedetection.io For External Content And API Change Monitoring](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0280-changedetection-io-for-external-content-and-api-change-monitoring.md)
- [ADR 0281: GlitchTip As The Sentry-Compatible Application Error Tracker](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md)
- [ADR 0282: Mailpit As The SMTP Development Mail Interceptor](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md)
- [ADR 0283: Plausible Analytics As The Privacy-First Web Traffic Analytics Layer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer.md)
- [ADR 0284: Netbox As The Network IPAM And Topology Source Of Truth](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0284-netbox-as-the-network-ipam-and-topology-source-of-truth.md)
- [ADR 0284: Piper TTS As The CPU Neural Text-To-Speech Service](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0284-piper-tts-as-the-cpu-neural-text-to-speech-service.md)
- [ADR 0285: Paperless-ngx As The Document Management And Archive API](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0285-paperless-ngx-as-the-document-management-and-archive-api.md)
- [ADR 0285: Whisper ASR As The CPU Speech-To-Text Service](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0285-whisper-asr-as-the-cpu-speech-to-text-service.md)
- [ADR 0286: Tesseract OCR Service For Scanned Image Text Extraction](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0286-tesseract-ocr-service-for-scanned-image-text-extraction.md)
- [ADR 0286: Vikunja As The Task And Project Management REST API](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0286-vikunja-as-the-task-and-project-management-rest-api.md)
- [ADR 0287: LiteLLM As The Unified LLM API Proxy And Router](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0287-litellm-as-the-unified-llm-api-proxy-and-router.md)
- [ADR 0287: Woodpecker CI As The API-Driven Continuous Integration Server](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0287-woodpecker-ci-as-the-api-driven-continuous-integration-server.md)
- [ADR 0288: Crawl4AI As The LLM-Optimised Web Content Crawler](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0288-crawl4ai-as-the-llm-optimised-web-content-crawler.md)
- [ADR 0288: Flagsmith As The Feature Flag And Remote Configuration Service](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md)
- [ADR 0289: Directus As The REST And GraphQL Data API Layer Over Postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0289-directus-as-the-rest-graphql-data-api-layer-over-postgres.md)
- [ADR 0289: Label Studio As The Human-In-The-Loop Data Annotation Platform](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0289-label-studio-as-the-human-in-the-loop-data-annotation-platform.md)
- [ADR 0290: MLflow As The Machine Learning Experiment Tracker And Model Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0290-mlflow-as-the-machine-learning-experiment-tracker-and-model-registry.md)
- [ADR 0290: Redpanda As The Kafka-Compatible Streaming Platform](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0290-redpanda-as-the-kafka-compatible-streaming-platform.md)
- [ADR 0291: JupyterHub As The Interactive Notebook Environment](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0291-jupyterhub-as-the-interactive-notebook-environment.md)
- [ADR 0291: SFTPGo As The Managed File Transfer Service With REST Provisioning](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0291-sftpgo-as-the-managed-file-transfer-service-with-rest-provisioning.md)
- [ADR 0292: Apache Superset As The SQL-First Business Intelligence Layer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0292-apache-superset-as-the-sql-first-business-intelligence-layer.md)
- [ADR 0292: Lago As The Usage Metering And Billing API Layer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0292-lago-as-the-usage-metering-and-billing-api-layer.md)
- [ADR 0293: Livekit As The Real-Time Audio And Voice Channel For Agents](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0293-livekit-as-the-real-time-audio-and-voice-channel-for-agents.md)
- [ADR 0293: Temporal As The Durable Workflow And Task Queue Engine](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0293-temporal-as-the-durable-workflow-and-task-queue-engine.md)
- [ADR 0294: One-API As The Unified LLM API Proxy And Router](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0294-one-api-as-the-unified-llm-api-proxy-and-router.md)
- [ADR 0295: Shared Artifact Cache Plane For Container And Package Dependencies](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0295-shared-artifact-cache-plane-for-container-and-package-dependencies.md)
- [ADR 0296: Dedicated Artifact-Cache VM With Phased Consumer Adoption](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0296-dedicated-artifact-cache-vm-with-phased-consumer-adoption.md)
- [ADR 0297: Renovate Bot As The Automated Stack Version Upgrade Proposer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0297-renovate-bot-as-the-automated-stack-version-upgrade-proposer.md)
- [ADR 0298: Syft And Grype For Platform-Wide SBOM Generation And Continuous CVE Scanning](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0298-syft-and-grype-for-platform-wide-sbom-generation-and-continuous-cve-scanning.md)
- [ADR 0299: Ntfy As The Self-Hosted Push Notification Channel For Programmatic Alert Delivery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0299-ntfy-as-the-self-hosted-push-notification-channel-for-programmatic-alert-delivery.md)
- [ADR 0300: Falco For Container Runtime Syscall Security Monitoring And Autonomous Anomaly Detection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0300-falco-for-container-runtime-syscall-security-monitoring-and-autonomous-anomaly-detection.md)
- [ADR 0301: Semgrep For SAST And Application Code Security Scanning In The CI Gate](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0301-semgrep-for-sast-and-application-code-security-scanning-in-the-ci-gate.md)
- [ADR 0302: Restic For Encrypted File-Level Backup Of Platform Configuration And State Artifacts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0302-restic-for-encrypted-file-level-backup-of-platform-configuration-and-state-artifacts.md)
- [ADR 0303: pgaudit For PostgreSQL Query And Privilege Change Audit Logging](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0303-pgaudit-for-postgresql-query-and-privilege-change-audit-logging.md)
- [ADR 0304: Atlas For Declarative Database Schema Migration Versioning And Pre-Migration Linting](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md)
- [ADR 0305: k6 For Continuous Load Testing And SLO Error Budget Burn Validation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md)
- [ADR 0306: Checkov For IaC Policy Compliance Scanning Of OpenTofu, Compose, And Ansible](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0306-checkov-for-iac-policy-compliance-scanning-of-opentofu-compose-and-ansible.md)

### Workstream Documents
- [Workstream ADR 0011: Monitoring Stack Rollout](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0011-monitoring.md)
- [Workstream ADR 0014: Tailscale Private Access Rollout](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0014-tailscale.md)
- [Workstream ADR 0020: Initial Storage And Backup Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0020-backups.md)
- [Workstream ADR 0023: Docker Runtime VM Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0023-docker-runtime.md)
- [Workstream ADR 0024: Docker Guest Security Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0024-docker-security.md)
- [Workstream ADR 0025: Compose-Managed Runtime Stacks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0025-docker-compose-stacks.md)
- [Workstream ADR 0026: Dedicated PostgreSQL VM Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0026-postgres-vm.md)
- [Workstream ADR 0027: Uptime Kuma On The Docker Runtime VM](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0027-uptime-kuma.md)
- [Workstream ADR 0028: Docker Build VM Build Count And Duration Telemetry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0028-build-telemetry.md)
- [Workstream ADR 0029: Dedicated Backup VM With Local PBS](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0029-backup-vm.md)
- [Workstream ADR 0040: Docker Runtime Container Telemetry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0040-runtime-container-telemetry.md)
- [Workstream ADR 0041: Dockerized Mail Platform Live Rollout](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0041-email-platform-live.md)
- [Workstream ADR 0041: Dockerized Mail Platform With API, Grafana Telemetry, And Failover Delivery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0041-email-platform.md)
- [Workstream ADR 0042: step-ca For SSH And Internal TLS](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0042-step-ca.md)
- [Workstream ADR 0043: OpenBao For Secrets, Transit, And Dynamic Credentials](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0043-openbao.md)
- [Workstream ADR 0044: Windmill For Agent And Operator Workflows](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0044-windmill.md)
- [Workstream ADR 0045: Control-Plane Communication Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0045-communication-lanes.md)
- [Workstream ADR 0046: Identity Classes For Humans, Services, And Agents](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0046-identity-classes.md)
- [Workstream ADR 0047: Short-Lived Credentials And Internal mTLS](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0047-short-lived-creds.md)
- [Workstream ADR 0048: Command Catalog And Approval Gates](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0048-command-catalog.md)
- [Workstream ADR 0049: Private-First API Publication Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0049-private-api-publication.md)
- [Workstream ADR 0050: Transactional Email And Notification Profiles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0050-notification-profiles.md)
- [Workstream ADR 0051: Control-Plane Backup, Recovery, And Break-Glass](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0051-control-plane-recovery.md)
- [Workstream ADR 0052: Centralized Log Aggregation With Grafana Loki](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0052-loki-logs.md)
- [Workstream ADR 0053: OpenTelemetry Traces And Service Maps With Grafana Tempo](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0053-tempo-traces.md)
- [Workstream ADR 0054: NetBox For Topology, IPAM, And Inventory](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0054-netbox-topology.md)
- [Workstream ADR 0055: Portainer For Read-Mostly Docker Runtime Operations](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0055-portainer-operations.md)
- [Workstream ADR 0056: Keycloak For Operator And Agent SSO](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0056-keycloak-sso.md)
- [Workstream ADR 0057: Mattermost For ChatOps And Operator-Agent Collaboration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0057-mattermost-chatops.md)
- [Workstream ADR 0058: NATS JetStream For Internal Event Bus And Agent Coordination](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0058-nats-event-bus.md)
- [Workstream ADR 0059: ntopng For Private Network Flow Visibility](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0059-ntopng-network-visibility.md)
- [Workstream ADR 0060: Open WebUI For Operator And Agent Workbench](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0060-open-webui-workbench.md)
- [Workstream ADR 0061: GlitchTip For Application Exceptions And Task Failures](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0061-glitchtip-failure-signals.md)
- [Workstream ADR 0062: Ansible Role Composability And DRY Defaults](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0062-role-composability.md)
- [Workstream ADR 0063: Centralised Vars And Computed Facts Library](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0063-platform-vars-library.md)
- [Workstream ADR 0064: Health Probe Contracts For All Services](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0064-health-probe-contracts.md)
- [Workstream ADR 0065: Secret Rotation Automation With OpenBao](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0065-secret-rotation-automation.md)
- [Workstream ADR 0066: Structured Mutation Audit Log](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0066-mutation-audit-log.md)
- [Workstream ADR 0067: Guest Network Policy Enforcement](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0067-guest-network-policy.md)
- [Workstream ADR 0068: Container Image Policy And Supply Chain Integrity](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0068-container-image-policy.md)
- [Workstream ADR 0069: Agent Tool Registry And Governed Tool Calls](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0069-agent-tool-registry.md)
- [Workstream ADR 0070: Retrieval-Augmented Context For Platform Queries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0070-rag-platform-context.md)
- [Workstream ADR 0071: Agent Observation Loop And Autonomous Drift Detection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0071-agent-observation-loop.md)
- [Workstream ADR 0072: Staging And Production Environment Topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0072-staging-environment.md)
- [Workstream ADR 0072: Staging And Production Environment Topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0072-staging-production-topology.md)
- [Workstream ADR 0073: Environment Promotion Gate And Deployment Pipeline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0073-promotion-pipeline.md)
- [Workstream ADR 0074: Platform Operations Portal](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0074-ops-portal.md)
- [Workstream ADR 0075: Service Capability Catalog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0075-service-capability-catalog.md)
- [Workstream ADR 0076: Subdomain Governance And DNS Lifecycle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0076-subdomain-governance.md)
- [Workstream ADR 0077: Compose Runtime Secrets Injection Via OpenBao Agent](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0077-compose-secrets-injection.md)
- [Workstream ADR 0078: Service Scaffold Generator](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0078-service-scaffold.md)
- [Workstream ADR 0079: Playbook Decomposition And Shared Execution Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0079-playbook-decomposition.md)
- [Workstream ADR 0080: Maintenance Window And Change Suppression Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0080-maintenance-windows.md)
- [Workstream ADR 0081: Platform Changelog And Deployment History Portal](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0081-changelog-portal.md)
- [Workstream ADR 0082: Remote Build Execution Gateway](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0082-remote-build-gateway.md)
- [Workstream ADR 0083: Docker-Based Check Runner](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0083-docker-check-runner.md)
- [Workstream ADR 0084: Packer VM Template Pipeline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0084-packer-pipeline.md)
- [Workstream ADR 0085: OpenTofu VM Lifecycle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0085-opentofu-vm-lifecycle.md)
- [Workstream ADR 0086: Ansible Collection Packaging](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0086-ansible-collections.md)
- [Workstream ADR 0087: Repository Validation Gate](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0087-validation-gate.md)
- [Workstream ADR 0088: Ephemeral Infrastructure Fixtures](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0088-ephemeral-fixtures.md)
- [Workstream ADR 0089: Build Artifact Cache and Layer Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0089-build-cache.md)
- [Workstream ADR 0090: Unified Platform CLI (`lv3`)](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0090-platform-cli.md)
- [Workstream ADR 0091: Continuous Drift Detection and Reconciliation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0091-drift-detection.md)
- [Workstream ADR 0092: Unified Platform API Gateway](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0092-platform-api-gateway.md)
- [Workstream ADR 0093: Interactive Ops Portal with Live Actions](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0093-interactive-ops-portal.md)
- [Workstream ADR 0094: Developer Portal and Service Documentation Site](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0094-developer-portal.md)
- [Workstream ADR 0095: Unified Search Across Platform Services](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0095-unified-search.md)
- [Workstream ADR 0096: SLO Definitions and Error Budget Tracking](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0096-slo-tracking.md)
- [Workstream ADR 0097: Alerting Routing and On-Call Runbook Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0097-alerting-routing.md)
- [Workstream ADR 0098: Postgres High Availability and Automated Failover](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0098-postgres-ha.md)
- [Workstream ADR 0099: Automated Backup Restore Verification](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0099-backup-restore-verification.md)
- [Workstream ADR 0100: RTO/RPO Targets and Disaster Recovery Playbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0100-disaster-recovery-playbook.md)
- [Workstream ADR 0101: Automated Certificate Lifecycle Management](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0101-certificate-lifecycle.md)
- [Workstream ADR 0102: Security Posture Reporting and Benchmark Drift](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0102-security-posture-reporting.md)
- [Workstream ADR 0103: Data Classification and Retention Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0103-data-retention-policy.md)
- [Workstream ADR 0104: Service Dependency Graph and Failure Propagation Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0104-dependency-graph.md)
- [Workstream ADR 0105: Platform Capacity Model and Resource Quota Enforcement](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0105-capacity-model.md)
- [Workstream ADR 0106: Ephemeral Environment Lifecycle and Teardown Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0106-ephemeral-lifecycle.md)
- [Workstream ADR 0107: Platform Extension Model for Adding New Services](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0107-extension-model.md)
- [Workstream ADR 0108: Operator Onboarding and Off-boarding Workflow](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0108-operator-onboarding.md)
- [Workstream ADR 0109: Public Status Page](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0109-public-status-page.md)
- [Workstream ADR 0110: Platform Versioning, Release Notes, and Upgrade Path](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0110-platform-versioning.md)
- [Workstream ADR 0111: End-to-End Integration Test Suite](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0111-integration-test-suite.md)
- [Workstream ADR 0112: Deterministic Goal Compiler](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0112-goal-compiler.md)
- [Workstream ADR 0113: World-State Materializer](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0113-world-state-materializer.md)
- [Workstream ADR 0114: Rule-Based Incident Triage Engine](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0114-incident-triage-engine.md)
- [Workstream ADR 0115: Event-Sourced Mutation Ledger](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0115-mutation-ledger.md)
- [Workstream ADR 0116: Change Risk Scoring Without LLMs](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0116-change-risk-scoring.md)
- [Workstream ADR 0117: Service Dependency Graph As First-Class Runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0117-dependency-graph-runtime.md)
- [Workstream ADR 0118: Replayable Failure Case Library](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0118-failure-case-library.md)
- [Workstream ADR 0119: Budgeted Workflow Scheduler](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0119-budgeted-workflow-scheduler.md)
- [Workstream ADR 0120: Dry-Run Semantic Diff Engine](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0120-dry-run-diff-engine.md)
- [Workstream ADR 0121: Local Search and Indexing Fabric](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0121-search-indexing-fabric.md)
- [Workstream ADR 0122: Windmill Operator Access Admin Surface](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0122-operator-access-admin.md)
- [Workstream ADR 0123: Service Uptime Contracts And Monitor-Backed Health](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0123-service-uptime-contracts.md)
- [Workstream ADR 0124: Platform Event Taxonomy And Canonical NATS Topics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0124-platform-event-taxonomy.md)
- [Workstream ADR 0125: Agent Capability Bounds](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0125-agent-capability-bounds.md)
- [Workstream ADR 0126: Observation-To-Action Closure Loop](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0126-observation-to-action-closure-loop.md)
- [Workstream ADR 0127: Intent Conflict Resolution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0127-intent-conflict-resolution.md)
- [Workstream ADR 0128: Platform Health Composite Index](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0128-platform-health-composite-index.md)
- [Workstream ADR 0129: Runbook Automation Executor](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0129-runbook-automation-executor.md)
- [Workstream ADR 0130: Agent State Persistence Across Workflow Boundaries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0130-agent-state-persistence.md)
- [Workstream ADR 0131: Multi-Agent Handoff Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0131-agent-handoff-protocol.md)
- [Workstream ADR 0132: Self-Describing Platform Manifest](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0132-self-describing-platform-manifest.md)
- [Workstream ADR 0133: Portal Authentication By Default](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0133-portal-authentication-by-default.md)
- [Workstream ADR 0134: Changelog Portal Content Redaction](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0134-changelog-redaction.md)
- [Workstream ADR 0135: Developer Portal Sensitivity Classification](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0135-developer-portal-sensitivity-classification.md)
- [Workstream ADR 0136: HTTP Security Headers Hardening](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0136-http-security-headers.md)
- [Workstream ADR 0137: Robots And Crawl Policy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0137-robots-and-crawl-policy.md)
- [Workstream ADR 0138: Published Artifact Secret Scanning](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0138-published-artifact-secret-scanning.md)
- [Workstream ADR 0139: Subdomain Exposure Audit And Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0139-subdomain-exposure-audit.md)
- [Workstream ADR 0140: Grafana Public Access Hardening](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0140-grafana-public-access-hardening.md)
- [Workstream ADR 0141: API Token Lifecycle and Exposure Response](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0141-api-token-lifecycle.md)
- [Workstream ADR 0142: Public Surface Automated Security Scan](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0142-public-surface-security-scan.md)
- [Workstream ADR 0143: Gitea for Self-Hosted Git and Webhook-Driven Automation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0143-gitea-ci.md)
- [Workstream ADR 0144: Headscale Mesh Control Plane](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0144-headscale.md)
- [Workstream ADR 0145: Ollama for Local LLM Inference API](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0145-ollama.md)
- [Workstream ADR 0146: Langfuse For Agent Observability](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0146-ai-observability.md)
- [Workstream ADR 0147: Vaultwarden for Operator Credential Management](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0147-vaultwarden.md)
- [Workstream ADR 0148: SearXNG for Agent Web Search](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0148-searxng-web-search.md)
- [Workstream ADR 0149: Semaphore For Ansible Job Management UI And API](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0149-semaphore.md)
- [Workstream ADR 0150: Dozzle for Real-Time Container Log Access](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0150-dozzle.md)
- [Workstream ADR 0151: n8n for Webhook and API Integration Automation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0151-n8n.md)
- [Workstream ADR 0152: Homepage for Unified Service Dashboard](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0152-homepage.md)
- [Workstream ADR 0153: Distributed Resource Lock Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0153-distributed-resource-lock-registry.md)
- [Workstream ADR 0154: VM-Scoped Parallel Execution Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0154-vm-scoped-execution-lanes.md)
- [Workstream ADR 0155: Intent Queue with Release-Triggered Scheduling](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0155-intent-queue-with-release-triggered-scheduling.md)
- [Workstream ADR 0156: Agent Session Workspace Isolation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0156-agent-session-workspace-isolation.md)
- [ADR 0157 Workstream](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0157-per-vm-concurrency-budget.md)
- [Workstream ADR 0158: Conflict-Free Configuration Merge Protocol](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0158-config-merge-protocol.md)
- [Workstream ADR 0159: Speculative Parallel Execution with Compensating Transactions](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0159-speculative-parallel-execution.md)
- [Workstream ADR 0160: Parallel Dry-Run Fan-Out](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0160-parallel-dry-run-fan-out.md)
- [Workstream ADR 0161: Real-Time Agent Coordination Map](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0161-real-time-agent-coordination-map.md)
- [Workstream ADR 0162: Distributed Deadlock Detection and Resolution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0162-deadlock-detector.md)
- [Workstream ADR 0163: Platform-Wide Retry Taxonomy And Exponential Backoff](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0163-retry-taxonomy.md)
- [Workstream ADR 0164: Circuit Breaker Pattern for External Service Calls](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0164-circuit-breaker-pattern.md)
- [Workstream ADR 0165: Workflow Idempotency Keys and Double-Execution Prevention](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0165-workflow-idempotency.md)
- [Workstream ADR 0166: Canonical Error Response Format And Error Code Registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0166-canonical-error-response-format.md)
- [Workstream ADR 0167: Graceful Degradation Mode Declarations](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0167-graceful-degradation-mode-declarations.md)
- [Workstream ADR 0168: Ansible Role Idempotency CI Enforcement](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0168-idempotency-ci.md)
- [Workstream ADR 0169: Structured Log Field Contract](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0169-structured-log-field-contract.md)
- [Workstream ADR 0170: Platform-Wide Timeout Hierarchy](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0170-timeout-hierarchy.md)
- [Workstream ADR 0171: Controlled Fault Injection for Resilience Validation](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0171-controlled-fault-injection.md)
- [Workstream ADR 0172: Watchdog Escalation and Stale Job Self-Healing](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0172-watchdog-escalation-and-stale-job-self-healing.md)
- [Workstream ADR 0173: Workstream Surface Ownership Manifest](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0173-workstream-surface-ownership-manifest.md)
- [Workstream ADR 0174: Integration-Only Canonical Truth Assembly](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0174-canonical-truth-assembly.md)
- [Workstream ADR 0175: Cross-Workstream Interface Contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0175-cross-workstream-interface-contracts.md)
- [Workstream ADR 0176: Inventory Sharding And Host-Scoped Ansible Execution](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0176-inventory-sharding.md)
- [Workstream ADR 0177: Run Namespace Partitioning](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0177-run-namespace-partitioning.md)
- [Workstream ADR 0178: Dependency Wave Manifests](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0178-dependency-wave-manifests.md)
- [Workstream ADR 0179: Service Redundancy Tier Matrix](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0179-service-redundancy-tier-matrix.md)
- [Workstream ADR 0180: Standby Capacity Reservation and Placement Rules](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0180-standby-capacity-reservation-and-placement-rules.md)
- [Workstream ADR 0181: Off-Host Witness And Control Metadata Replication](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0181-off-host-witness-replication.md)
- [Workstream ADR 0182: Live Apply Merge Train and Rollback Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0182-live-apply-merge-train-and-rollback-bundle.md)
- [Workstream ADR 0183: Multi-Environment Live Lanes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0183-multi-environment-live-lanes.md)
- [Workstream ADR 0185: Branch-Scoped Ephemeral Preview Environments](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0185-branch-scoped-ephemeral-preview-environments.md)
- [Workstream ADR 0193: Plane Kanban Task Board](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0193-plane-kanban-task-board.md)
- [Workstream ADR 0194: Coolify PaaS Deploy From Repo](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0194-coolify-paas-deploy-from-repo.md)
- [Workstream ADR 0196: Netdata Realtime Streaming Metrics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0196-netdata-realtime-streaming-metrics.md)
- [Workstream ADR 0198: Qdrant Vector Search for Semantic Platform RAG](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0198-qdrant-vector-search-semantic-rag.md)
- [Workstream ADR 0199: Outline Living Knowledge Wiki](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0199-outline-living-knowledge-wiki.md)
- [Workstream ADR 0202: Excalidraw Auto Generated Architecture Diagrams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0202-excalidraw-auto-generated-architecture-diagrams.md)
- [Workstream ADR 0204: Architecture Governance Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0204-architecture-governance.md)
- [Workstream ADR 0205: Capability Contracts Before Product Selection](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0205-capability-contracts-before-product-selection.md)
- [Workstream ADR 0207: Anti-Corruption Layers At Provider Boundaries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0207-anti-corruption-layers-at-provider-boundaries.md)
- [Workstream WS-0211: Shared Policy Packs And Rule Registries Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0211-shared-policy-packs-and-rule-registries.md)
- [Workstream ADR 0214: HA And Replication Architecture Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0214-ha-replication-architecture-bundle.md)
- [Workstream ADR 0224: Self-Service Repo Intake And Agent-Assisted Deployments](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0224-self-service-repo-intake-and-agent-assisted-deployments.md)
- [Workstream ADR 0224: Server-Resident Operations Architecture Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0224-server-resident-operations-architecture-bundle.md)
- [Workstream ADR 0234: Human User Experience Architecture Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0234-human-user-experience-architecture-bundle.md)
- [Workstream ADR 0244: Runtime Assurance Architecture Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0244-runtime-assurance-architecture-bundle.md)
- [Workstream ADR 0254: ServerClaw Architecture Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0254-serverclaw-architecture-bundle.md)
- [Workstream ADR 0263: ServerClaw Memory Substrate](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0263-serverclaw-memory-substrate.md)
- [Workstream ADR 0264: Receipt-Driven Resilience Architecture Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0264-receipt-driven-resilience-architecture-bundle.md)
- [Workstream WS-0265: Immutable Validation Snapshots For Remote Builders And Schema Checks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md)
- [Workstream ADR 0266: Validation Runner Capability Contracts Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0266-validation-runner-capability-contracts-live-apply.md)
- [Workstream ADR 0270: Docker Publication Self-Healing And Port-Programming Assertions](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0270-docker-publication-self-healing-and-port-programming-assertions.md)
- [Workstream ADR 0273: Public Endpoint Admission Control](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0273-public-endpoint-admission-control.md)
- [Workstream ADR 0295: Artifact Cache Architecture Bundle](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0295-artifact-cache-architecture-bundle.md)
- [Workstream ws-0021-edge-cert-repair: Shared Edge Certificate Expansion Repair](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0021-edge-cert-repair.md)
- [Workstream ws-0101-live-apply: ADR 0101 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0101-live-apply.md)
- [Workstream ws-0105-live-apply: Live Apply ADR 0105 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0105-live-apply.md)
- [Workstream WS-0108: Operator Onboarding and Off-boarding Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0108-live-apply.md)
- [Workstream WS-0184: Failure-Domain Labels And Anti-Affinity Policy Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0184-live-apply.md)
- [Workstream ws-0186-live-apply: Live Apply ADR 0186 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0186-live-apply.md)
- [Workstream ws-0187-live-apply: ADR 0187 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0187-live-apply.md)
- [Workstream WS-0188: Failover Rehearsal Gate Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0188-live-apply.md)
- [Workstream ws-0189-live-apply: ADR 0189 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0189-live-apply.md)
- [Workstream ws-0190-live-apply: ADR 0190 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0190-live-apply.md)
- [Workstream ws-0191-live-apply: ADR 0191 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0191-live-apply.md)
- [Workstream ws-0192-live-apply: Live Apply ADR 0192 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0192-live-apply.md)
- [Workstream ws-0193-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0193-main-merge.md)
- [Workstream ws-0194-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0194-main-merge.md)
- [Workstream ws-0196-live-apply: Live Apply ADR 0196 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0196-live-apply.md)
- [Workstream WS-0197: Dify Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0197-live-apply.md)
- [Workstream ws-0201-live-apply: ADR 0201 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0201-live-apply.md)
- [Workstream ws-0201-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0201-main-merge.md)
- [Workstream WS-0204: Self-Correcting Automation Loops Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0204-live-apply.md)
- [Workstream ws-0205-main-final](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0205-main-final.md)
- [Workstream WS-0206: Ports And Adapters Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0206-live-apply.md)
- [Workstream WS-0206 Main Merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0206-main-merge.md)
- [Workstream WS-0207 Main Merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0207-main-merge.md)
- [Workstream ws-0208-live-apply: Dependency Direction And Composition Roots](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0208-live-apply.md)
- [Workstream ws-0208-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0208-main-merge.md)
- [Workstream WS-0209: Runbook Use-Case Service Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0209-live-apply.md)
- [Workstream ws-0210-live-apply: ADR 0210 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0210-live-apply.md)
- [Workstream ws-0211-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0211-main-merge.md)
- [Workstream ws-0212-live-apply: ADR 0212 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0212-live-apply.md)
- [Workstream WS-0224: Server-Resident Operations Default-Control Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0224-live-apply.md)
- [Workstream WS-0225: Server-Resident Reconciliation Via Ansible Pull Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0225-live-apply.md)
- [Workstream WS-0226: Host Control Loops Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0226-live-apply.md)
- [Workstream ws-0226-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0226-main-merge.md)
- [Workstream WS-0227: Bounded Command Execution Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0227-live-apply.md)
- [Workstream WS-0228: Windmill Default Operations Surface Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0228-live-apply.md)
- [Workstream ws-0228-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0228-main-merge.md)
- [Workstream ws-0229-live-apply: ADR 0229 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0229-live-apply.md)
- [Workstream ws-0229-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0229-main-merge.md)
- [Workstream WS-0230: Policy Decisions Via Open Policy Agent And Conftest Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0230-live-apply.md)
- [Workstream WS-0231: Local Secret Delivery Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0231-live-apply.md)
- [Workstream ws-0231-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0231-main-merge.md)
- [Workstream WS-0232: Nomad Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0232-live-apply.md)
- [Workstream ws-0232-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0232-main-merge.md)
- [Workstream WS-0233: Signed Release Bundles Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0233-live-apply.md)
- [Workstream ws-0233-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0233-main-merge.md)
- [Workstream WS-0234: PatternFly Human Shell Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0234-live-apply.md)
- [Workstream WS-0235: Cross-Application Launcher Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0235-live-apply.md)
- [Workstream ws-0235-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0235-main-merge.md)
- [Workstream WS-0236: TanStack Query Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0236-live-apply.md)
- [Workstream WS-0236: Mainline Integration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0236-main-merge.md)
- [Workstream WS-0237: Schema-First Human Forms Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0237-live-apply.md)
- [Workstream ws-0237-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0237-main-merge.md)
- [Workstream WS-0238: Data-Dense Operator Grids Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0238-live-apply.md)
- [Workstream ws-0238-main-integration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0238-main-integration.md)
- [Workstream WS-0239: Browser-Local Search Experience Via Pagefind Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0239-live-apply.md)
- [Workstream ws-0239-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0239-main-merge.md)
- [Workstream WS-0240: Operator Visualization Panels Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0240-live-apply.md)
- [Workstream ws-0240-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0240-main-merge.md)
- [Workstream WS-0241: Rich Content And Inline Knowledge Editing Via Tiptap Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0241-live-apply.md)
- [Workstream ws-0241-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0241-main-merge.md)
- [Workstream WS-0242: Guided Human Onboarding Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0242-live-apply.md)
- [Workstream ws-0242-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0242-main-merge.md)
- [Workstream WS-0244: Runtime Assurance Matrix Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0244-live-apply.md)
- [Workstream WS-0244: Mainline Integration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0244-main-merge.md)
- [Workstream WS-0245: Declared-To-Live Service Attestation Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0245-live-apply.md)
- [Workstream ws-0246-live-apply: ADR 0246 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0246-live-apply.md)
- [Workstream ws-0246-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0246-main-merge.md)
- [Workstream WS-0248: Session And Logout Authority Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0248-live-apply.md)
- [Workstream ws-0248-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0248-main-merge.md)
- [Workstream ws-0249-live-apply: ADR 0249 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0249-live-apply.md)
- [Workstream ws-0250-live-apply: Live Apply ADR 0250 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0250-live-apply.md)
- [Workstream ws-0251-live-apply-r2: Stage-Scoped Smoke Suites And Promotion Gates](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0251-live-apply-r2.md)
- [Workstream WS-0251: Stage-Scoped Smoke Suites Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0251-live-apply.md)
- [Workstream ws-0251-main-integration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0251-main-integration.md)
- [Workstream WS-0252: Route And DNS Publication Assertion Ledger Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0252-live-apply.md)
- [Workstream ws-0252-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0252-main-merge.md)
- [Workstream ws-0252-mainline-replay](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0252-mainline-replay.md)
- [Workstream WS-0253: Unified Runtime Assurance Scoreboard Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0253-live-apply.md)
- [Workstream ws-0254-live-apply: Live Apply ADR 0254 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0254-live-apply.md)
- [Workstream ws-0254-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0254-main-merge.md)
- [Workstream ws-0255-live-apply: ADR 0255 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0255-live-apply.md)
- [Workstream ws-0255-main-integration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0255-main-integration.md)
- [Workstream WS-0259: n8n Connector Fabric Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0259-live-apply.md)
- [Workstream ws-0259-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0259-main-merge.md)
- [Workstream ws-0260-live-apply: ADR 0260 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0260-live-apply.md)
- [Workstream ws-0260-main-integration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0260-main-integration.md)
- [Workstream ws-0263-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0263-main-merge.md)
- [Workstream ws-0264-live-apply: Live Apply ADR 0264 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0264-live-apply.md)
- [Workstream ws-0264-main-merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0264-main-merge.md)
- [Workstream ws-0268-live-apply: Live Apply ADR 0268 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0268-live-apply.md)
- [Workstream ws-0268-main-integration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0268-main-integration.md)
- [Workstream WS-0271: Backup Coverage Assertion Ledger Live Apply](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0271-live-apply.md)
- [Workstream ws-0272-live-apply: ADR 0272 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0272-live-apply.md)
- [Workstream ws-0278-live-apply: ADR 0278 Live Apply From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0278-live-apply.md)
- [Workstream ws-0278-main-integration](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0278-main-integration.md)
- [Workstream ws-0295-live-apply: Live Apply ADR 0295 From Latest `origin/main`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0295-live-apply.md)
- [Workstream WS-0296: Education Repo Refresh And Named Deploy Profiles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0296-education-refresh.md)
<!-- END GENERATED: document-index -->

## Versioning

This repo now tracks three distinct things:

- Repository version: [`VERSION`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION)
- Desired platform and observed host state: [`versions/stack.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- Versioning rules: [ADR 0008](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0008-versioning-model-for-repo-and-host.md)

Current values on `main`:

<!-- BEGIN GENERATED: version-summary -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

| Field | Value |
| --- | --- |
| Repository version | `0.177.93` |
| Platform version | `0.130.62` |
| Observed OS | `Debian 13` |
| Observed Proxmox installed | `true` |
| Observed PVE manager version | `9.1.6` |
<!-- END GENERATED: version-summary -->

ADR metadata now tracks both acceptance and implementation:

- decision status
- implementation status
- first repo version implemented
- first platform version implemented
- implementation date

Repository releases are indexed in [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md), with versioned notes under [docs/release-notes/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/README.md) and detailed change history generated into the deployment portal build.

## Delivery Model

This repository now supports parallel implementation:

- ADRs remain the architecture truth
- active implementation is tracked in [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
- each active implementation stream gets its own file in [docs/workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams)
- each workstream should run on its own `codex/` branch and preferably its own git worktree
- shared release files are reconciled during integration on `main`, not rewritten independently on every workstream branch
- `VERSION` is bumped on merge to `main`, not on every branch-local change
- `platform_version` is bumped only after merged work is applied live from `main`

## Engineering stance

This repository is intentionally opinionated:

- DRY by default
- explicit versioning for repo and platform state
- small reversible infrastructure changes
- clear separation between bootstrap, security, storage, networking, and Proxmox object management

## Merged Workstreams

<!-- BEGIN GENERATED: merged-workstreams -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

| ADR | Title | Status | Doc |
| --- | --- | --- | --- |
| `0011` | Monitoring stack rollout | `live_applied` | [adr-0011-monitoring.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0011-monitoring.md) |
| `0014` | Tailscale private access rollout | `live_applied` | [adr-0014-tailscale.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0014-tailscale.md) |
| `0020` | Initial storage and backup model | `merged` | [adr-0020-backups.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0020-backups.md) |
| `0021` | Repair shared edge certificate expansion during service-specific converges | `live_applied` | [ws-0021-edge-cert-repair.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0021-edge-cert-repair.md) |
| `0023` | Docker runtime VM baseline | `live_applied` | [adr-0023-docker-runtime.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0023-docker-runtime.md) |
| `0024` | Docker guest security baseline | `live_applied` | [adr-0024-docker-security.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0024-docker-security.md) |
| `0025` | Compose-managed runtime stacks | `merged` | [adr-0025-docker-compose-stacks.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0025-docker-compose-stacks.md) |
| `0026` | Dedicated PostgreSQL VM baseline | `merged` | [adr-0026-postgres-vm.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0026-postgres-vm.md) |
| `0027` | Uptime Kuma rollout on the Docker runtime VM | `merged` | [adr-0027-uptime-kuma.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0027-uptime-kuma.md) |
| `0028` | Docker build VM build count and duration telemetry | `live_applied` | [adr-0028-build-telemetry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0028-build-telemetry.md) |
| `0029` | Dedicated backup VM with local PBS | `merged` | [adr-0029-backup-vm.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0029-backup-vm.md) |
| `0040` | Docker runtime container telemetry | `live_applied` | [adr-0040-runtime-container-telemetry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0040-runtime-container-telemetry.md) |
| `0041` | Dockerized mail platform with API, Grafana telemetry, and failover delivery | `merged` | [adr-0041-email-platform.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0041-email-platform.md) |
| `0041` | Dockerized mail platform live rollout | `live_applied` | [adr-0041-email-platform-live.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0041-email-platform-live.md) |
| `0042` | step-ca for SSH and internal TLS | `live_applied` | [adr-0042-step-ca.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0042-step-ca.md) |
| `0043` | OpenBao for secrets, transit, and dynamic credentials | `live_applied` | [adr-0043-openbao.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0043-openbao.md) |
| `0044` | Windmill for agent and operator workflows | `live_applied` | [adr-0044-windmill.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0044-windmill.md) |
| `0045` | Control-plane communication lanes | `live_applied` | [adr-0045-communication-lanes.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0045-communication-lanes.md) |
| `0046` | Identity classes for humans, services, agents, and break-glass | `live_applied` | [adr-0046-identity-classes.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0046-identity-classes.md) |
| `0047` | Short-lived credentials and internal mTLS | `live_applied` | [adr-0047-short-lived-creds.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0047-short-lived-creds.md) |
| `0048` | Command catalog and approval gates | `live_applied` | [adr-0048-command-catalog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0048-command-catalog.md) |
| `0049` | Private-first API publication model | `merged` | [adr-0049-private-api-publication.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0049-private-api-publication.md) |
| `0050` | Transactional email and notification profiles | `merged` | [adr-0050-notification-profiles.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0050-notification-profiles.md) |
| `0051` | Control-plane backup, recovery, and break-glass | `live_applied` | [adr-0051-control-plane-recovery.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0051-control-plane-recovery.md) |
| `0052` | Centralized log aggregation with Grafana Loki | `live_applied` | [adr-0052-loki-logs.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0052-loki-logs.md) |
| `0053` | OpenTelemetry traces and service maps with Grafana Tempo | `live_applied` | [adr-0053-tempo-traces.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0053-tempo-traces.md) |
| `0054` | NetBox for topology, IPAM, and inventory | `live_applied` | [adr-0054-netbox-topology.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0054-netbox-topology.md) |
| `0055` | Portainer for read-mostly Docker runtime operations | `live_applied` | [adr-0055-portainer-operations.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0055-portainer-operations.md) |
| `0056` | Keycloak for operator and agent SSO | `live_applied` | [adr-0056-keycloak-sso.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0056-keycloak-sso.md) |
| `0057` | Mattermost for ChatOps and operator-agent collaboration | `live_applied` | [adr-0057-mattermost-chatops.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0057-mattermost-chatops.md) |
| `0059` | ntopng for private network flow visibility | `live_applied` | [adr-0059-ntopng-network-visibility.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0059-ntopng-network-visibility.md) |
| `0060` | Open WebUI for operator and agent workbench | `live_applied` | [adr-0060-open-webui-workbench.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0060-open-webui-workbench.md) |
| `0062` | Ansible role composability and DRY defaults | `merged` | [adr-0062-role-composability.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0062-role-composability.md) |
| `0063` | Centralised vars and computed facts library | `merged` | [adr-0063-platform-vars-library.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0063-platform-vars-library.md) |
| `0064` | Health probe contracts for all services | `merged` | [adr-0064-health-probe-contracts.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0064-health-probe-contracts.md) |
| `0065` | Secret rotation automation with OpenBao | `live_applied` | [adr-0065-secret-rotation-automation.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0065-secret-rotation-automation.md) |
| `0067` | Guest network policy enforcement | `live_applied` | [adr-0067-guest-network-policy.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0067-guest-network-policy.md) |
| `0068` | Container image policy and supply chain integrity | `merged` | [adr-0068-container-image-policy.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0068-container-image-policy.md) |
| `0069` | Agent tool registry and governed tool calls | `merged` | [adr-0069-agent-tool-registry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0069-agent-tool-registry.md) |
| `0070` | Retrieval-augmented context for platform queries | `live_applied` | [adr-0070-rag-platform-context.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0070-rag-platform-context.md) |
| `0071` | Agent observation loop and autonomous drift detection | `merged` | [adr-0071-agent-observation-loop.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0071-agent-observation-loop.md) |
| `0072` | Staging and production environment topology | `merged` | [adr-0072-staging-production-topology.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0072-staging-production-topology.md) |
| `0073` | Environment promotion gate and deployment pipeline | `merged` | [adr-0073-promotion-pipeline.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0073-promotion-pipeline.md) |
| `0074` | Platform operations portal | `live_applied` | [adr-0074-ops-portal.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0074-ops-portal.md) |
| `0075` | Service capability catalog | `merged` | [adr-0075-service-capability-catalog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0075-service-capability-catalog.md) |
| `0076` | Subdomain governance and DNS lifecycle | `merged` | [adr-0076-subdomain-governance.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0076-subdomain-governance.md) |
| `0077` | Compose runtime secrets injection via OpenBao Agent | `live_applied` | [adr-0077-compose-secrets-injection.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0077-compose-secrets-injection.md) |
| `0078` | Service scaffold generator | `merged` | [adr-0078-service-scaffold.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0078-service-scaffold.md) |
| `0079` | Playbook decomposition and shared execution model | `merged` | [adr-0079-playbook-decomposition.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0079-playbook-decomposition.md) |
| `0080` | Maintenance window and change suppression protocol | `merged` | [adr-0080-maintenance-windows.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0080-maintenance-windows.md) |
| `0081` | Platform changelog and deployment history portal | `live_applied` | [adr-0081-changelog-portal.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0081-changelog-portal.md) |
| `0082` | Remote build execution gateway | `live_applied` | [adr-0082-remote-build-gateway.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0082-remote-build-gateway.md) |
| `0083` | Docker-based check runner | `merged` | [adr-0083-docker-check-runner.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0083-docker-check-runner.md) |
| `0084` | Packer VM template pipeline | `merged` | [adr-0084-packer-pipeline.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0084-packer-pipeline.md) |
| `0085` | Declarative VM provisioning with OpenTofu | `merged` | [adr-0085-opentofu-vm-lifecycle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0085-opentofu-vm-lifecycle.md) |
| `0086` | Ansible collection packaging | `merged` | [adr-0086-ansible-collections.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0086-ansible-collections.md) |
| `0087` | Repository validation gate | `merged` | [adr-0087-validation-gate.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0087-validation-gate.md) |
| `0088` | Ephemeral infrastructure fixtures | `merged` | [adr-0088-ephemeral-fixtures.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0088-ephemeral-fixtures.md) |
| `0089` | Build artifact cache and layer registry | `merged` | [adr-0089-build-cache.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0089-build-cache.md) |
| `0090` | Unified platform CLI | `merged` | [adr-0090-platform-cli.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0090-platform-cli.md) |
| `0091` | Continuous drift detection and reconciliation | `merged` | [adr-0091-drift-detection.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0091-drift-detection.md) |
| `0092` | Unified platform API gateway | `live_applied` | [adr-0092-platform-api-gateway.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0092-platform-api-gateway.md) |
| `0093` | Interactive ops portal with live actions | `live_applied` | [adr-0093-interactive-ops-portal.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0093-interactive-ops-portal.md) |
| `0094` | Developer portal and service documentation site | `live_applied` | [adr-0094-developer-portal.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0094-developer-portal.md) |
| `0096` | SLO definitions and error budget tracking | `live_applied` | [adr-0096-slo-tracking.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0096-slo-tracking.md) |
| `0097` | Alerting routing and on-call runbook model | `merged` | [adr-0097-alerting-routing.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0097-alerting-routing.md) |
| `0098` | Postgres high availability and automated failover | `merged` | [adr-0098-postgres-ha.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0098-postgres-ha.md) |
| `0099` | Automated backup restore verification | `merged` | [adr-0099-backup-restore-verification.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0099-backup-restore-verification.md) |
| `0100` | RTO/RPO targets and disaster recovery playbook | `merged` | [adr-0100-disaster-recovery-playbook.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0100-disaster-recovery-playbook.md) |
| `0101` | Automated certificate lifecycle management | `live_applied` | [adr-0101-certificate-lifecycle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0101-certificate-lifecycle.md) |
| `0101` | ADR 0101 live apply from latest origin/main | `live_applied` | [ws-0101-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0101-live-apply.md) |
| `0102` | Security posture reporting and benchmark drift | `merged` | [adr-0102-security-posture-reporting.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0102-security-posture-reporting.md) |
| `0103` | Data classification and retention policy | `merged` | [adr-0103-data-retention-policy.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0103-data-retention-policy.md) |
| `0104` | Service dependency graph and failure propagation model | `merged` | [adr-0104-dependency-graph.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0104-dependency-graph.md) |
| `0105` | Platform capacity model and resource quota enforcement | `merged` | [adr-0105-capacity-model.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0105-capacity-model.md) |
| `0105` | ADR 0105 live apply from latest origin/main | `merged` | [ws-0105-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0105-live-apply.md) |
| `0106` | Ephemeral environment lifecycle and teardown policy | `merged` | [adr-0106-ephemeral-lifecycle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0106-ephemeral-lifecycle.md) |
| `0107` | Platform extension model for adding new services | `merged` | [adr-0107-extension-model.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0107-extension-model.md) |
| `0108` | Operator onboarding and off-boarding workflow | `live_applied` | [adr-0108-operator-onboarding.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0108-operator-onboarding.md) |
| `0108` | Operator onboarding and off-boarding live apply | `live_applied` | [ws-0108-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0108-live-apply.md) |
| `0109` | Public status page | `merged` | [adr-0109-public-status-page.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0109-public-status-page.md) |
| `0110` | Platform versioning, release notes, and upgrade path | `merged` | [adr-0110-platform-versioning.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0110-platform-versioning.md) |
| `0111` | End-to-end integration test suite | `merged` | [adr-0111-integration-test-suite.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0111-integration-test-suite.md) |
| `0112` | Deterministic goal compiler | `merged` | [adr-0112-goal-compiler.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0112-goal-compiler.md) |
| `0113` | World-state materializer | `live_applied` | [adr-0113-world-state-materializer.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0113-world-state-materializer.md) |
| `0114` | Rule-based incident triage engine | `merged` | [adr-0114-incident-triage-engine.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0114-incident-triage-engine.md) |
| `0115` | Event-sourced mutation ledger | `merged` | [adr-0115-mutation-ledger.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0115-mutation-ledger.md) |
| `0116` | Deterministic workflow change risk scoring | `merged` | [adr-0116-change-risk-scoring.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0116-change-risk-scoring.md) |
| `0117` | Service dependency graph as first-class runtime | `live_applied` | [adr-0117-dependency-graph-runtime.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0117-dependency-graph-runtime.md) |
| `0119` | Budgeted workflow scheduler | `live_applied` | [adr-0119-budgeted-workflow-scheduler.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0119-budgeted-workflow-scheduler.md) |
| `0120` | Dry-run semantic diff engine | `merged` | [adr-0120-dry-run-diff-engine.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0120-dry-run-diff-engine.md) |
| `0121` | Local search and indexing fabric | `merged` | [adr-0121-search-indexing-fabric.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0121-search-indexing-fabric.md) |
| `0122` | Windmill operator access admin surface | `live_applied` | [adr-0122-operator-access-admin.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0122-operator-access-admin.md) |
| `0123` | Service uptime contracts and monitor-backed health | `merged` | [adr-0123-service-uptime-contracts.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0123-service-uptime-contracts.md) |
| `0124` | Platform event taxonomy and canonical NATS topics | `live_applied` | [adr-0124-platform-event-taxonomy.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0124-platform-event-taxonomy.md) |
| `0125` | Agent capability bounds and autonomous action policy | `merged` | [adr-0125-agent-capability-bounds.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0125-agent-capability-bounds.md) |
| `0126` | Observation-to-action closure loop | `live_applied` | [adr-0126-observation-to-action-closure-loop.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0126-observation-to-action-closure-loop.md) |
| `0127` | Intent deduplication and conflict resolution | `merged` | [adr-0127-intent-conflict-resolution.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0127-intent-conflict-resolution.md) |
| `0128` | Platform health composite index | `merged` | [adr-0128-platform-health-composite-index.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0128-platform-health-composite-index.md) |
| `0129` | Runbook automation executor | `merged` | [adr-0129-runbook-automation-executor.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0129-runbook-automation-executor.md) |
| `0130` | Agent state persistence across workflow boundaries | `merged` | [adr-0130-agent-state-persistence.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0130-agent-state-persistence.md) |
| `0131` | Multi-agent handoff protocol | `merged` | [adr-0131-agent-handoff-protocol.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0131-agent-handoff-protocol.md) |
| `0132` | Self-describing platform manifest | `merged` | [adr-0132-self-describing-platform-manifest.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0132-self-describing-platform-manifest.md) |
| `0133` | Portal authentication by default | `merged` | [adr-0133-portal-authentication-by-default.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0133-portal-authentication-by-default.md) |
| `0134` | Changelog portal content redaction | `merged` | [adr-0134-changelog-redaction.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0134-changelog-redaction.md) |
| `0135` | Developer portal sensitivity classification | `merged` | [adr-0135-developer-portal-sensitivity-classification.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0135-developer-portal-sensitivity-classification.md) |
| `0136` | HTTP security headers hardening | `live_applied` | [adr-0136-http-security-headers.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0136-http-security-headers.md) |
| `0137` | Robots.txt and crawl policy | `live_applied` | [adr-0137-robots-and-crawl-policy.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0137-robots-and-crawl-policy.md) |
| `0138` | Published artifact secret scanning | `live_applied` | [adr-0138-published-artifact-secret-scanning.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0138-published-artifact-secret-scanning.md) |
| `0139` | Subdomain exposure audit and registry | `merged` | [adr-0139-subdomain-exposure-audit.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0139-subdomain-exposure-audit.md) |
| `0140` | Grafana public access hardening | `live_applied` | [adr-0140-grafana-public-access-hardening.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0140-grafana-public-access-hardening.md) |
| `0141` | API token lifecycle and exposure response | `merged` | [adr-0141-api-token-lifecycle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0141-api-token-lifecycle.md) |
| `0142` | Public surface automated security scan | `merged` | [adr-0142-public-surface-security-scan.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0142-public-surface-security-scan.md) |
| `0143` | Private Gitea with self-hosted CI | `merged` | [adr-0143-gitea-ci.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0143-gitea-ci.md) |
| `0144` | Headscale mesh control plane | `merged` | [adr-0144-headscale.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0144-headscale.md) |
| `0145` | Ollama for local LLM inference | `live_applied` | [adr-0145-ollama.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0145-ollama.md) |
| `0146` | Langfuse for agent observability | `live_applied` | [adr-0146-ai-observability.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0146-ai-observability.md) |
| `0147` | Vaultwarden for operator credential management | `live_applied` | [adr-0147-vaultwarden.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0147-vaultwarden.md) |
| `0148` | SearXNG for agent web search | `merged` | [adr-0148-searxng-web-search.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0148-searxng-web-search.md) |
| `0150` | Dozzle for real-time container log access | `live_applied` | [adr-0150-dozzle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0150-dozzle.md) |
| `0151` | n8n for webhook and API integration automation | `live_applied` | [adr-0151-n8n.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0151-n8n.md) |
| `0152` | Homepage for unified service dashboard | `live_applied` | [adr-0152-homepage.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0152-homepage.md) |
| `0153` | Distributed resource lock registry | `merged` | [adr-0153-distributed-resource-lock-registry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0153-distributed-resource-lock-registry.md) |
| `0154` | VM-scoped parallel execution lanes | `live_applied` | [adr-0154-vm-scoped-execution-lanes.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0154-vm-scoped-execution-lanes.md) |
| `0155` | Intent queue with release-triggered scheduling | `live_applied` | [adr-0155-intent-queue-with-release-triggered-scheduling.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0155-intent-queue-with-release-triggered-scheduling.md) |
| `0156` | Agent session workspace isolation | `live_applied` | [adr-0156-agent-session-workspace-isolation.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0156-agent-session-workspace-isolation.md) |
| `0157` | Per-VM concurrency budget and resource reservation | `live_applied` | [adr-0157-per-vm-concurrency-budget.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0157-per-vm-concurrency-budget.md) |
| `0158` | Conflict-free configuration merge protocol | `live_applied` | [adr-0158-config-merge-protocol.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0158-config-merge-protocol.md) |
| `0159` | Speculative parallel execution with compensating transactions | `merged` | [adr-0159-speculative-parallel-execution.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0159-speculative-parallel-execution.md) |
| `0160` | Parallel dry-run fan-out for intent batch validation | `merged` | [adr-0160-parallel-dry-run-fan-out.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0160-parallel-dry-run-fan-out.md) |
| `0161` | Real-time agent coordination map | `live_applied` | [adr-0161-real-time-agent-coordination-map.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0161-real-time-agent-coordination-map.md) |
| `0162` | Distributed deadlock detection and resolution | `live_applied` | [adr-0162-deadlock-detector.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0162-deadlock-detector.md) |
| `0163` | Platform-wide retry taxonomy and exponential backoff | `live_applied` | [adr-0163-retry-taxonomy.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0163-retry-taxonomy.md) |
| `0164` | Circuit breaker pattern for external service calls | `live_applied` | [adr-0164-circuit-breaker-pattern.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0164-circuit-breaker-pattern.md) |
| `0165` | Workflow idempotency keys and double-execution prevention | `live_applied` | [adr-0165-workflow-idempotency.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0165-workflow-idempotency.md) |
| `0166` | Canonical error response format and error code registry | `live_applied` | [adr-0166-canonical-error-response-format.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0166-canonical-error-response-format.md) |
| `0167` | Graceful degradation mode declarations | `live_applied` | [adr-0167-graceful-degradation-mode-declarations.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0167-graceful-degradation-mode-declarations.md) |
| `0168` | Ansible role idempotency CI enforcement | `merged` | [adr-0168-idempotency-ci.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0168-idempotency-ci.md) |
| `0169` | Structured log field contract | `live_applied` | [adr-0169-structured-log-field-contract.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0169-structured-log-field-contract.md) |
| `0170` | Platform-wide timeout hierarchy | `live_applied` | [adr-0170-timeout-hierarchy.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0170-timeout-hierarchy.md) |
| `0171` | Controlled fault injection for resilience validation | `live_applied` | [adr-0171-controlled-fault-injection.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0171-controlled-fault-injection.md) |
| `0172` | Watchdog escalation and stale job self-healing | `merged` | [adr-0172-watchdog-escalation-and-stale-job-self-healing.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0172-watchdog-escalation-and-stale-job-self-healing.md) |
| `0173` | Workstream surface ownership manifest | `live_applied` | [adr-0173-workstream-surface-ownership-manifest.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0173-workstream-surface-ownership-manifest.md) |
| `0174` | Integration-only canonical truth assembly | `merged` | [adr-0174-canonical-truth-assembly.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0174-canonical-truth-assembly.md) |
| `0175` | Cross-workstream interface contracts | `merged` | [adr-0175-cross-workstream-interface-contracts.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0175-cross-workstream-interface-contracts.md) |
| `0176` | Inventory sharding and host-scoped Ansible execution | `live_applied` | [adr-0176-inventory-sharding.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0176-inventory-sharding.md) |
| `0177` | Run namespace partitioning for parallel tooling | `merged` | [adr-0177-run-namespace-partitioning.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0177-run-namespace-partitioning.md) |
| `0178` | Dependency wave manifests for parallel apply | `merged` | [adr-0178-dependency-wave-manifests.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0178-dependency-wave-manifests.md) |
| `0179` | Service redundancy tier matrix | `merged` | [adr-0179-service-redundancy-tier-matrix.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0179-service-redundancy-tier-matrix.md) |
| `0181` | Off-host witness and control metadata replication | `live_applied` | [adr-0181-off-host-witness-replication.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0181-off-host-witness-replication.md) |
| `0182` | Live apply merge train and rollback bundle | `merged` | [adr-0182-live-apply-merge-train-and-rollback-bundle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0182-live-apply-merge-train-and-rollback-bundle.md) |
| `0183` | Multi-environment live lanes | `live_applied` | [adr-0183-multi-environment-live-lanes.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0183-multi-environment-live-lanes.md) |
| `0184` | Failure-domain labels and anti-affinity policy live apply | `live_applied` | [ws-0184-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0184-live-apply.md) |
| `0185` | Branch-scoped ephemeral preview environments | `merged` | [adr-0185-branch-scoped-ephemeral-preview-environments.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/docs/workstreams/adr-0185-branch-scoped-ephemeral-preview-environments.md) |
| `0186` | Live apply ADR 0186 prewarmed fixture pools and lease-based ephemeral capacity | `merged` | [ws-0186-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0186-live-apply.md) |
| `0187` | ADR 0187 live apply from latest origin/main | `live_applied` | [ws-0187-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0187-live-apply.md) |
| `0188` | Failover rehearsal gate live apply | `live_applied` | [ws-0188-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/worktree-ws-0188-live-apply/docs/workstreams/ws-0188-live-apply.md) |
| `0189` | ADR 0189 live apply from latest origin/main | `live_applied` | [ws-0189-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0189-live-apply.md) |
| `0190` | ADR 0190 live apply from latest origin/main | `merged` | [ws-0190-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0190-live-apply.md) |
| `0191` | Immutable guest replacement for stateful and edge services | `live_applied` | [ws-0191-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0191-live-apply.md) |
| `0192` | Live apply ADR 0192 capacity classes for standby, recovery, and preview workloads | `merged` | [ws-0192-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0192-live-apply.md) |
| `0193` | Plane Kanban Task Board | `merged` | [adr-0193-plane-kanban-task-board.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0193-plane-kanban-task-board.md) |
| `0193` | Integrate ADR 0193 live apply into origin/main | `live_applied` | [ws-0193-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0193-main-merge.md) |
| `0194` | Coolify PaaS deploy from repo | `merged` | [adr-0194-coolify-paas-deploy-from-repo.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0194-coolify-paas-deploy-from-repo.md) |
| `0194` | Integrate ADR 0194 live apply into origin/main | `merged` | [ws-0194-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0194-main-merge.md) |
| `0196` | ADR 0196 live apply from latest origin/main | `merged` | [ws-0196-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0196-live-apply.md) |
| `0199` | Outline living knowledge wiki | `merged` | [adr-0199-outline-living-knowledge-wiki.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0199-live-apply/docs/workstreams/adr-0199-outline-living-knowledge-wiki.md) |
| `0201` | Harbor runtime deployment, registry cutover, and repository automation replay | `live_applied` | [ws-0201-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0201-live-apply.md) |
| `0201` | Finalize ADR 0201 Harbor exact-main evidence on origin/main | `merged` | [ws-0201-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0201-main-merge.md) |
| `0202` | Excalidraw auto generated architecture diagrams | `live_applied` | [adr-0202-excalidraw-auto-generated-architecture-diagrams.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0202-excalidraw-auto-generated-architecture-diagrams.md) |
| `0204` | Architecture governance bundle for self-correction, clean boundaries, and vendor replaceability | `merged` | [adr-0204-architecture-governance.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0204-architecture-governance.md) |
| `0204` | Self-correcting automation loops live apply | `merged` | [ws-0204-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0204-live-apply.md) |
| `0206` | Live apply ADR 0206 ports and adapters for external integrations | `live_applied` | [ws-0206-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0206-live-apply.md) |
| `0206` | Integrate ADR 0206 live apply into origin/main | `merged` | [ws-0206-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0206-main-merge.md) |
| `0209` | Shared runbook use-case service with thin CLI, API gateway, Windmill, and ops portal adapters | `live_applied` | [ws-0209-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0209-live-apply.md) |
| `0210` | Live apply canonical publication models over adapter-shaped vendor fields | `merged` | [ws-0210-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0210-live-apply.md) |
| `0211` | Shared policy packs and rule registries live apply | `merged` | [adr-0211-shared-policy-packs-and-rule-registries.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0211-shared-policy-packs-and-rule-registries.md) |
| `0211` | Integrate ADR 0211 shared policy registries into origin/main | `merged` | [ws-0211-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0211-main-merge.md) |
| `0212` | Replaceability scorecards and vendor exit plans live apply | `merged` | [ws-0212-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0212-live-apply.md) |
| `0214` | HA and replication architecture bundle for production and staging | `merged` | [adr-0214-ha-replication-architecture-bundle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0214-ha-replication-architecture-bundle.md) |
| `0224` | Live apply ADR 0224 server-resident operations as the default control model | `live_applied` | [ws-0224-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0224-live-apply.md) |
| `0224` | Server-resident operations architecture bundle | `merged` | [adr-0224-server-resident-operations-architecture-bundle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0224-server-resident-operations-architecture-bundle.md) |
| `0226` | Live apply ADR 0226 systemd host-resident control-loop supervision | `live_applied` | [ws-0226-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0226-live-apply.md) |
| `0226` | Finalize ADR 0226 exact-main evidence on origin/main | `merged` | [ws-0226-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0226-main-merge.md) |
| `0228` | Integrate ADR 0228 live apply into origin/main | `live_applied` | [ws-0228-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0228-main-merge.md) |
| `0230` | Live apply policy decisions via Open Policy Agent and Conftest | `live_applied` | [ws-0230-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0230-live-apply.md) |
| `0231` | Live apply ADR 0231 local secret delivery via OpenBao Agent and systemd credentials | `live_applied` | [ws-0231-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0231-live-apply.md) |
| `0231` | Integrate ADR 0231 live apply into origin/main | `merged` | [ws-0231-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0231-main-merge.md) |
| `0232` | Live apply and verify the private Nomad scheduler | `live_applied` | [ws-0232-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0232-live-apply.md) |
| `0232` | Integrate ADR 0232 live apply into origin/main | `merged` | [ws-0232-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0232-main-merge.md) |
| `0233` | Live apply signed release bundles via Gitea Releases and Cosign | `live_applied` | [ws-0233-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0233-live-apply.md) |
| `0233` | Integrate ADR 0233 signed release bundles into origin/main | `merged` | [ws-0233-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0233-main-merge.md) |
| `0234` | Human user experience architecture bundle | `merged` | [adr-0234-human-user-experience-architecture-bundle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0234-human-user-experience-architecture-bundle.md) |
| `0234` | Live apply shared human app shell and navigation via PatternFly | `live_applied` | [ws-0234-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0234-live-apply.md) |
| `0235` | Live apply cross-application launcher and favorites in the interactive ops portal | `live_applied` | [ws-0235-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0235-live-apply.md) |
| `0235` | Integrate ADR 0235 cross-application launcher into origin/main | `merged` | [ws-0235-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0235-main-merge.md) |
| `0236` | Live apply TanStack Query server-state conventions on the Windmill operator admin app | `live_applied` | [ws-0236-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0236-live-apply.md) |
| `0236` | Integrate ADR 0236 TanStack Query server-state feedback into origin/main | `merged` | [ws-0236-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0236-main-merge.md) |
| `0237` | Live apply schema-first human forms via React Hook Form and Zod | `live_applied` | [ws-0237-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0237-live-apply.md) |
| `0237` | Integrate ADR 0237 schema-first human forms into origin/main | `merged` | [ws-0237-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0237-main-merge.md) |
| `0238` | Data-dense operator grids live apply | `live_applied` | [ws-0238-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0238-live-apply.md) |
| `0238` | Integrate ADR 0238 operator grid into origin/main | `merged` | [ws-0238-main-integration.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0238-main-integration.md) |
| `0239` | Live apply browser-local search experience via Pagefind | `live_applied` | [ws-0239-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0239-live-apply.md) |
| `0239` | Integrate ADR 0239 browser-local search into origin/main | `merged` | [ws-0239-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0239-main-merge.md) |
| `0240` | Live apply operator visualization panels via Apache ECharts | `live_applied` | [ws-0240-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0240-live-apply.md) |
| `0240` | Integrate ADR 0240 operator visualization panels into origin/main | `merged` | [ws-0240-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0240-main-merge.md) |
| `0241` | Live apply ADR 0241 rich content and inline knowledge editing via Tiptap | `live_applied` | [ws-0241-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0241-live-apply.md) |
| `0241` | Integrate ADR 0241 rich content and inline knowledge editing into origin/main | `merged` | [ws-0241-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0241-main-merge.md) |
| `0242` | Guided human onboarding live apply via Shepherd tours | `live_applied` | [ws-0242-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0242-live-apply.md) |
| `0242` | Integrate ADR 0242 guided onboarding into origin/main | `merged` | [ws-0242-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0242-main-merge.md) |
| `0244` | Live apply runtime assurance matrix per service and environment | `live_applied` | [ws-0244-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0244-live-apply.md) |
| `0244` | Integrate ADR 0244 runtime assurance matrix into origin/main | `merged` | [ws-0244-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0244-main-merge.md) |
| `0244` | Runtime assurance architecture bundle | `merged` | [adr-0244-runtime-assurance-architecture-bundle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0244-runtime-assurance-architecture-bundle.md) |
| `0245` | Declared-to-live service attestation live apply | `live_applied` | [ws-0245-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0245-live-apply.md) |
| `0246` | Live apply startup, readiness, liveness, and degraded-state semantics | `live_applied` | [ws-0246-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0246-live-apply.md) |
| `0246` | Integrate ADR 0246 runtime-state semantics into origin/main | `merged` | [ws-0246-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0246-main-merge.md) |
| `0248` | Live apply session and logout authority across Keycloak, oauth2-proxy, and app surfaces | `live_applied` | [ws-0248-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0248-live-apply.md) |
| `0248` | Integrate ADR 0248 session/logout authority into origin/main | `merged` | [ws-0248-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0248-main-merge.md) |
| `0249` | Live apply HTTPS and TLS assurance through blackbox exporter and testssl.sh | `live_applied` | [ws-0249-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0249-live-apply.md) |
| `0250` | ADR 0250 live apply from latest origin/main | `live_applied` | [ws-0250-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0250-live-apply.md) |
| `0251` | Live apply stage-scoped smoke suites and promotion gates | `live_applied` | [ws-0251-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0251-live-apply.md) |
| `0251` | Stage-scoped smoke suites and promotion-gate live apply | `live_applied` | [ws-0251-live-apply-r2.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0251-live-apply-r2.md) |
| `0251` | Integrate ADR 0251 exact-main durable verification onto current origin/main | `merged` | [ws-0251-main-integration.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0251-main-integration.md) |
| `0252` | Live apply ADR 0252 route and DNS publication assertion ledger | `live_applied` | [ws-0252-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0252-live-apply.md) |
| `0252` | Integrate ADR 0252 exact-main replay onto current origin/main | `merged` | [ws-0252-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0252-main-merge.md) |
| `0252` | Re-verify ADR 0252 from the latest origin/main and prepare final merge surfaces | `live_applied` | [ws-0252-mainline-replay.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0252-mainline-replay.md) |
| `0253` | Unified runtime assurance scoreboard live apply | `live_applied` | [ws-0253-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0253-live-apply.md) |
| `0254` | Live apply ADR 0254 ServerClaw | `live_applied` | [ws-0254-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0254-live-apply.md) |
| `0254` | Integrate ADR 0254 exact-main replay onto current origin/main | `merged` | [ws-0254-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0254-main-merge.md) |
| `0254` | ServerClaw architecture bundle | `merged` | [adr-0254-serverclaw-architecture-bundle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0254-serverclaw-architecture-bundle.md) |
| `0255` | ADR 0255 live apply from latest origin/main | `live_applied` | [ws-0255-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0255-live-apply.md) |
| `0255` | Integrate ADR 0255 exact-main replay onto current origin/main | `merged` | [ws-0255-main-integration.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0255-main-integration.md) |
| `0259` | Live apply n8n as the external app connector fabric for ServerClaw | `live_applied` | [ws-0259-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0259-live-apply.md) |
| `0259` | Integrate ADR 0259 exact-main replay onto current origin/main | `merged` | [ws-0259-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0259-main-merge.md) |
| `0260` | Live-apply ADR 0260 Nextcloud personal data plane from latest origin/main | `live_applied` | [ws-0260-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0260-live-apply.md) |
| `0263` | Integrate ADR 0263 exact-main replay onto current origin/main | `merged` | [ws-0263-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0263-main-merge.md) |
| `0263` | ServerClaw memory substrate live apply | `live_applied` | [adr-0263-serverclaw-memory-substrate.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0263-serverclaw-memory-substrate.md) |
| `0264` | Failure-domain-isolated validation lanes live apply | `live_applied` | [ws-0264-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0264-live-apply.md) |
| `0264` | Integrate ADR 0264 failure-domain-isolated validation lanes onto origin/main | `merged` | [ws-0264-main-merge.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0264-main-merge.md) |
| `0264` | Receipt-driven resilience architecture bundle | `merged` | [adr-0264-receipt-driven-resilience-architecture-bundle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0264-receipt-driven-resilience-architecture-bundle.md) |
| `0265` | Immutable validation snapshots for remote builders and schema checks | `live_applied` | [adr-0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md) |
| `0268` | Fresh-worktree bootstrap manifests live apply | `live_applied` | [ws-0268-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0268-live-apply.md) |
| `0268` | Integrate ADR 0268 exact-main replay onto current origin/main | `merged` | [ws-0268-main-integration.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0268-main-integration.md) |
| `0271` | Backup coverage assertion ledger live apply | `live_applied` | [ws-0271-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0271-live-apply.md) |
| `0272` | Restore readiness ladders and stateful warm-up verification profiles | `live_applied` | [ws-0272-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0272-live-apply.md) |
| `0273` | Live apply ADR 0273 public endpoint admission control | `live_applied` | [adr-0273-public-endpoint-admission-control.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0273-public-endpoint-admission-control.md) |
| `0278` | ADR 0278 live apply from latest origin/main | `live_applied` | [ws-0278-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0278-live-apply.md) |
| `0295` | Shared artifact cache plane and dedicated cache VM roadmap | `live_applied` | [adr-0295-artifact-cache-architecture-bundle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0295-artifact-cache-architecture-bundle.md) |
| `0295` | Live apply the shared artifact cache plane from latest origin/main | `live_applied` | [ws-0295-live-apply.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/ws-0295-live-apply.md) |
<!-- END GENERATED: merged-workstreams -->

## Planned workflow

1. Inspect disks, networking, and current Debian 13 base state.
2. Establish the steady-state operator access path with Tailscale, replacing the temporary jump-host-only flow.
3. Implement the monitoring stack on `10.10.10.40`.
4. Configure storage and backups.
5. Extend notifications beyond the host baseline where needed.
6. Commit the resulting automation and operational docs in this repo.

## Automation

The first executable automation scaffold now exists:

- [ansible.cfg](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/ansible.cfg)
- [inventory/hosts.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml)
- [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)
- [playbooks/site.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml)
- [playbooks/public-edge.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/public-edge.yml)
- [playbooks/proxmox-install.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/proxmox-install.yml)
- [playbooks/docker-runtime.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/docker-runtime.yml)
- [playbooks/backup-vm.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/backup-vm.yml)
- [playbooks/uptime-kuma.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/uptime-kuma.yml)
- [roles/proxmox_repository/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_repository/tasks/main.yml)
- [roles/proxmox_kernel/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_kernel/tasks/main.yml)
- [roles/proxmox_platform/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_platform/tasks/main.yml)
- [roles/proxmox_network/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_network/tasks/main.yml)
- [roles/proxmox_tailscale/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_tailscale/tasks/main.yml)
- [roles/nginx_edge_publication/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/nginx_edge_publication/tasks/main.yml)
- [docs/runbooks/configure-public-ingress.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md)
- [docs/runbooks/configure-edge-publication.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-edge-publication.md)
- [docs/runbooks/configure-tailscale-access.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-tailscale-access.md)
- [roles/proxmox_guests/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_guests/tasks/main.yml)
- [roles/linux_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/linux_access/tasks/main.yml)
- [roles/docker_runtime/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/docker_runtime/tasks/main.yml)
- [roles/backup_vm/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/backup_vm/tasks/main.yml)
- [roles/uptime_kuma_runtime/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/uptime_kuma_runtime/tasks/main.yml)
- [roles/proxmox_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_access/tasks/main.yml)
- [roles/proxmox_api_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_api_access/tasks/main.yml)
- [roles/proxmox_security/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_security/tasks/main.yml)
- [roles/proxmox_backups/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_backups/tasks/main.yml)
- [roles/hetzner_dns_records/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/hetzner_dns_records/tasks/main.yml)
- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile)
- [docs/runbooks/install-proxmox.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/install-proxmox.md)
- [docs/runbooks/configure-proxmox-network.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-proxmox-network.md)
- [docs/runbooks/provision-guests.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/provision-guests.md)
- [docs/runbooks/harden-access.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/harden-access.md)
- [playbooks/guest-access.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/guest-access.yml)
- [playbooks/monitoring-stack.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/monitoring-stack.yml)
- [docs/runbooks/configure-docker-runtime.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-docker-runtime.md)
- [docs/runbooks/complete-security-baseline.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/complete-security-baseline.md)
- [scripts/totp_provision.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/totp_provision.py)
- [scripts/uptime_kuma_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/uptime_kuma_tool.py)
- [docs/runbooks/monitoring-stack.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md)
- [roles/monitoring_vm/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_vm/tasks/main.yml)
- [roles/proxmox_metrics/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_metrics/tasks/main.yml)
