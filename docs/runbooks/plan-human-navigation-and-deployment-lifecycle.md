# Plan: Human Navigation, Deployment Lifecycle, And Platform Hardening (ADRs 0072–0081)

This runbook describes the second hardening and extensibility wave for the Florin platform. It covers ten ADRs (0072–0081) that address four themes:

1. **Deployment lifecycle** — where does a change go before it goes live?
2. **Human navigation** — where does everything live, and how do I find it?
3. **DRY and modularity** — how do we stop copying and start composing?
4. **Production security** — how do we close the remaining gaps before calling this production-ready?

---

## Background

ADRs 0001–0048 built the physical and logical platform: Proxmox host, six VMs, PKI, secrets, identity, workflows, and control-plane lanes.

ADRs 0049–0071 defined the observability, operational tools (Keycloak, Mattermost, NetBox, Portainer), hardening (network policy, image policy, secret rotation, audit logging), and early agent automation.

ADRs 0072–0081 address the gaps that remain before the platform can be operated confidently by any team member or agent without institutional memory:

| Gap | ADR |
|---|---|
| No staging environment; every change hits production first | 0072 |
| No formal gate between "tested in staging" and "deployed to production" | 0073 |
| No single place to see what services exist and where they live | 0074, 0075 |
| No defined process for creating or retiring a subdomain | 0076 |
| Secrets still in .env files on disk | 0077 |
| Adding a new service requires 12 manual steps with no checklist | 0078 |
| Playbooks are not environment-aware or composable as groups | 0079 |
| Planned maintenance generates the same noise as real outages | 0080 |
| No human-readable timeline of what has been deployed and when | 0081 |

---

## ADR Map

### Theme 1: Deployment Lifecycle

```
ADR 0072 — Staging and Production Environment Topology
  └─ ADR 0073 — Environment Promotion Gate and Deployment Pipeline
       └─ ADR 0080 — Maintenance Window and Change Suppression Protocol
```

**ADR 0072** provisions a second internal bridge (`vmbr20`, `10.20.10.0/24`) with a disposable staging environment that mirrors the production VM topology. All playbooks become environment-aware via `--extra-vars "env=staging"`.

**ADR 0073** wraps the promotion in a Windmill workflow: validate → stage → health-check → gate → promote → receipt. Every production change requires a staging receipt less than 24 hours old, a clean health-check pass, and an operator approval.

**ADR 0080** closes the alert-fatigue loop: when the deploy pipeline runs, it opens a maintenance window for the affected service so the observation loop (ADR 0071) and Uptime Kuma suppress non-security findings during the change.

**Recommended delivery order:** 0072 → 0073 → 0080

---

### Theme 2: Human Navigation

```
ADR 0075 — Service Capability Catalog          (data layer)
  └─ ADR 0074 — Platform Operations Portal     (service map, runbooks, ADRs, agents)
       └─ ADR 0081 — Deployment History Portal (timeline, per-service history)
  └─ ADR 0076 — Subdomain Governance           (DNS map)
```

**ADR 0075** is the foundation: a JSON catalog (`config/service-capability-catalog.json`) with one entry per service covering URL, VM, health probe, images, secrets, ADR, and runbook.

**ADR 0074** generates a static web portal (`ops.lv3.org`) from that catalog. The portal has six views: Service Map (with live health), VM Inventory, DNS Map, Runbook Index, ADR Decision Log, and Agent Capability Surface. It is the answer to "where does everything live?"

**ADR 0081** adds the temporal layer: `changelog.lv3.org`, a generated deployment history timeline synthesised from receipts, promotion records, and the Loki mutation audit log.

**ADR 0076** defines how subdomains are created, managed, and retired — including the catalog file, TLS provisioning rules (Let's Encrypt for public, step-ca for private), and the `make provision-subdomain` automation.

**Recommended delivery order:** 0075 → 0076 → 0074 → 0081

---

### Theme 3: DRY and Modularity

```
ADR 0078 — Service Scaffold Generator
ADR 0079 — Playbook Decomposition and Shared Execution Model
```

**ADR 0078** implements `make scaffold-service`, a single command that creates a complete new-service skeleton: ADR stub, workstream doc, role (from template), playbook, Compose stack with OpenBao sidecar, and catalog entries for health probes, images, secrets, service capability, and subdomain.

**ADR 0079** restructures playbooks into composable groups (`playbooks/groups/security.yml`, `observability.yml`, etc.), adds shared `preflight.yml` and `post-verify.yml` task files imported by every play, and makes all playbooks environment-aware through platform facts (ADR 0063).

**Recommended delivery order:** 0079 → 0078 (scaffold uses the decomposed playbook model)

---

### Theme 4: Production Security

```
ADR 0077 — Compose Runtime Secrets Injection via OpenBao Agent
```

**ADR 0077** removes the last major plaintext-on-disk surface: `.env` files in Compose directories. An OpenBao Agent sidecar fetches secrets at startup into a `tmpfs` volume and re-fetches on TTL expiry. The five priority stacks (Grafana, Windmill, Mattermost, Keycloak, Open WebUI) are migrated first.

**Recommended delivery order:** 0077 (self-contained; no dependencies from this wave beyond live-applied ADRs)

---

## Dependency Graph (Full Wave)

```
[0063 platform-vars] ──► [0072 staging]   ──► [0073 promotion] ──► [0080 windows]
[0043 openbao]       ──► [0072 staging]
[0042 step-ca]       ──► [0072 staging]

[0064 health-probes] ──► [0075 svc-catalog] ──► [0074 ops-portal] ──► [0081 changelog]
[0068 image-policy]  ──► [0075 svc-catalog]
[0065 secret-rot]    ──► [0075 svc-catalog]
                         [0075 svc-catalog] ──► [0076 subdomains]
                         [0075 svc-catalog] ──► [0078 scaffold]
[0042 step-ca]       ──► [0076 subdomains]

[0025 compose]       ──► [0077 secrets-inject]
[0043 openbao]       ──► [0077 secrets-inject]

[0062 role-composability] ──► [0079 playbook-decomp]
[0063 platform-vars]      ──► [0079 playbook-decomp]
[0072 staging]            ──► [0079 playbook-decomp]

[0079 playbook-decomp] ──► [0078 scaffold]
[0077 secrets-inject]  ──► [0078 scaffold]
```

---

## Parallel Delivery Lanes

These ten ADRs can be worked in four independent lanes:

| Lane | ADRs | Prerequisite from this wave |
|---|---|---|
| A: Deployment Lifecycle | 0072, 0073, 0080 | None (depends on already-live ADRs) |
| B: Catalog and Discovery | 0075, 0076 | None |
| C: Navigation Apps | 0074, 0081 | Lane B (0075 must exist) |
| D: Engineering Hygiene | 0077, 0079 | None |
| E: Scaffold | 0078 | Lanes B and D |

Lane A and Lane D can start immediately. Lane B can start immediately. Lane C begins after Lane B reaches `ready_to_merge`.

---

## New Subdomains This Wave

| FQDN | Service | Exposure | ADR |
|---|---|---|---|
| `ops.lv3.org` | Platform Operations Portal | edge-published (auth-gated) | 0074 |
| `changelog.lv3.org` | Deployment History Portal | edge-published (auth-gated) | 0081 |
| `ops.staging.lv3.org` | Staging Ops Portal | private-only | 0074 |

All other staging subdomains (`*.staging.lv3.org`) resolve via internal DNS only.

---

## New Make Targets This Wave

| Target | ADR | Description |
|---|---|---|
| `make live-apply env=staging` | 0072 | Run a playbook against staging inventory |
| `make promote SERVICE=<n>` | 0073 | Trigger staging → production promotion |
| `make open-maintenance-window` | 0080 | Open a maintenance window via NATS KV |
| `make close-maintenance-window` | 0080 | Close a maintenance window |
| `make generate-ops-portal` | 0074 | Render the static ops portal |
| `make generate-changelog-portal` | 0081 | Render the deployment history portal |
| `make provision-subdomain FQDN=<n>` | 0076 | DNS + TLS + NGINX for a new subdomain |
| `make scaffold-service NAME=<n>` | 0078 | Generate complete new-service skeleton |
| `make live-apply-group group=<n>` | 0079 | Run a group playbook (e.g. observability) |
| `make live-apply-service service=<n>` | 0079 | Run a single service playbook |
| `make show-service SERVICE=<n>` | 0075 | Print service catalog entry |

---

## New Configuration Files This Wave

| File | ADR | Purpose |
|---|---|---|
| `config/service-capability-catalog.json` | 0075 | All services: URL, VM, probes, images, secrets, runbook |
| `config/subdomain-catalog.json` | 0076 | All subdomains: FQDN, TLS, target, lifecycle |
| `docs/schema/service-capability-catalog.schema.json` | 0075 | JSON Schema for validation |
| `docs/schema/subdomain-catalog.schema.json` | 0076 | JSON Schema for validation |
| `docs/schema/promotion-receipt.json` | 0073 | Promotion receipt schema |
| `docs/schema/maintenance-window.json` | 0080 | Maintenance window descriptor schema |
| `receipts/live-applies/staging/` | 0073 | Staging live-apply receipts |
| `receipts/promotions/` | 0073 | Staging → production promotion records |
| `docs/release-notes/` | 0081 | Per-version release notes |

---

## Validation Gate Additions This Wave

| Check | ADR | Gate |
|---|---|---|
| No `TODO` string values in any catalog JSON | 0078 | `make validate` |
| Every NGINX route has a subdomain catalog entry | 0076 | `make validate` |
| Service catalog cross-references resolve | 0075 | `make validate` |
| No `*.env` files in compose directories on controller | 0077 | `make validate` |
| Promotion receipt is < 24 hours old at promote time | 0073 | Windmill promotion gate |

---

## Success Criteria For This Wave

- [ ] `make live-apply env=staging playbook=grafana.yml` succeeds and targets `10.20.10.*`
- [ ] A full staging → production promotion runs through the Windmill pipeline with a promotion receipt
- [ ] `https://ops.lv3.org` is live, auth-gated, and shows all services from the capability catalog
- [ ] `https://changelog.lv3.org` shows the last 30 live-apply receipts in a human-readable timeline
- [ ] No `.env` files exist in any Compose directory on `docker-runtime-lv3`
- [ ] `make scaffold-service NAME=test-echo` produces all 12 artifacts with no TODO markers after completion
- [ ] `make live-apply-group group=observability env=staging` runs cleanly
- [ ] A maintenance window suppresses observation loop findings during a grafana restart
- [ ] All new subdomains (`ops.lv3.org`, `changelog.lv3.org`) have TLS certificates issued and `make validate` passes the subdomain catalog check

---

## Related Plans

- `docs/runbooks/plan-platform-hardening-and-agentic-extensibility.md` — ADRs 0062–0071 (prior wave)
- `docs/runbooks/plan-agentic-control-plane.md` — control-plane identity and command governance
- `docs/runbooks/plan-visual-agent-operations.md` — agent workbench and observation UIs
