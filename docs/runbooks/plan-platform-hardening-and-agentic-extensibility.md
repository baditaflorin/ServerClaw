# Platform Hardening And Agentic Extensibility Roadmap

## Purpose

This runbook ties ADRs 0062–0071 into a single operating model with two parallel tracks:

1. **Platform Hardening** — make the automation codebase more modular, DRY, production-ready, and secure so the platform can be extended confidently without accumulating hidden risk
2. **Agentic Extensibility** — expose the platform's capabilities as a governed, self-describing tool surface that agents and humans can use without direct shell access

The two tracks are designed to proceed in parallel. Hardening work does not need to be complete before agentic work starts, but several agentic features depend on hardening outputs (e.g. health probe contracts, secret rotation, image policy) as their data sources.

---

## ADR Map

### Track 1: Platform Hardening

| ADR | Title | Theme |
|-----|-------|-------|
| [ADR 0062](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0062-ansible-role-composability-and-dry-defaults.md) | Ansible Role Composability And DRY Defaults | Modularity |
| [ADR 0063](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0063-centralised-vars-and-computed-facts-library.md) | Centralised Vars And Computed Facts Library | DRY |
| [ADR 0064](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0064-health-probe-contracts-for-all-services.md) | Health Probe Contracts For All Services | Production Readiness |
| [ADR 0065](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0065-secret-rotation-automation-with-openbao.md) | Secret Rotation Automation With OpenBao | Security |
| [ADR 0066](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0066-structured-mutation-audit-log.md) | Structured Mutation Audit Log | Security / Auditability |
| [ADR 0067](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0067-guest-network-policy-enforcement.md) | Guest Network Policy Enforcement | Security |
| [ADR 0068](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0068-container-image-policy-and-supply-chain-integrity.md) | Container Image Policy And Supply Chain Integrity | Security / Production Readiness |

### Track 2: Agentic Extensibility

| ADR | Title | Theme |
|-----|-------|-------|
| [ADR 0069](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0069-agent-tool-registry-and-governed-tool-calls.md) | Agent Tool Registry And Governed Tool Calls | Agentic |
| [ADR 0070](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0070-rag-context-for-platform-queries.md) | Retrieval-Augmented Context For Platform Queries | Agentic |
| [ADR 0071](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0071-agent-observation-loop-and-drift-detection.md) | Agent Observation Loop And Autonomous Drift Detection | Agentic |

---

## Recommended Rollout Order

### Phase 1: Foundations (no live changes required)

These deliver immediate value and unblock everything else. They are repository-only changes with no live-apply risk.

1. **ADR 0062 — role composability** first
   - unlocks shared task files used by probe contracts and other roles
   - delivers the role template before new roles are written for agentic features
   - merge gate: `make validate` with new lint rule

2. **ADR 0063 — vars library** immediately after 0062
   - generated `platform.yml` becomes the canonical topology reference for agent tooling
   - no role behaviour changes; only variable resolution paths change

### Phase 2: Production Hardening (requires live apply)

Work in the order that reduces risk fastest.

3. **ADR 0064 — health probe contracts**
   - adds `verify.yml` to every service role; first live apply reveals any services that have been silently unhealthy
   - the `health-probe-catalog.json` becomes the data source for the observation loop (ADR 0071)

4. **ADR 0067 — guest network policy**
   - highest security impact; default-deny inter-guest traffic closes the largest lateral-movement gap
   - apply during a scheduled maintenance window with all guest SSH paths pre-validated
   - do this before expanding the number of internal services further

5. **ADR 0068 — container image policy**
   - audit and pin all existing images before adding new containers for agentic services
   - scan receipts establish a CVE baseline; new containers must clear the same gate

6. **ADR 0065 — secret rotation automation**
   - depends on OpenBao (ADR 0043) and Windmill (ADR 0044) being live
   - start with the postgres service password as the lowest-risk candidate
   - the `secret-catalog.json` becomes a data source for the observation loop

7. **ADR 0066 — mutation audit log**
   - depends on Loki (ADR 0052) being live for the Loki sink
   - the Ansible callback plugin can be merged to main before Loki is live; it will buffer to the local file sink

### Phase 3: Agentic Extensibility (build on stable hardened platform)

These phases require the hardening outputs as data sources and assume the visual operations ADRs (0052–0061) are at least partially live.

8. **ADR 0069 — agent tool registry**
   - seed the registry from existing workflow-catalog and command-catalog entries
   - the first `observe` tools need only Grafana and Uptime Kuma to be live
   - MCP export enables Claude Code and other MCP-capable agents to load tools natively

9. **ADR 0070 — RAG platform context**
   - depends on ADR 0069 for tool registration
   - index the corpus immediately; even a partial index over ADRs and runbooks is useful
   - wire into Open WebUI (ADR 0060) as the first integration point

10. **ADR 0071 — agent observation loop**
    - the capstone of the agentic track; requires probe catalog, image catalog, secret catalog, and NATS all active
    - start with read-only checks; add self-healing only after the finding routing is verified stable

---

## Dependency Graph

```
0062 ──► 0063
0062 ──► 0064 ──────────────────────► 0071
0067                                   │
0068 ──────────────────────────────────┤
0065 ──► (secret-catalog) ─────────────┤
0066 ──► (audit trail) ────────────────┤
                                       │
0069 ──► 0070                          │
0069 ──────────────────────────────────┤
0058 (NATS) ───────────────────────────┘
```

---

## Machine-Readable Outputs Per ADR

The following new machine-readable files are introduced by this ADR set. They become data sources for agents, operators, and future automation:

| File | Produced By | Purpose |
|------|------------|---------|
| `config/health-probe-catalog.json` | ADR 0064 | Liveness and readiness probes per service |
| `config/secret-catalog.json` | ADR 0065 | Managed secrets with rotation metadata |
| `config/image-catalog.json` | ADR 0068 | Pinned image digests with scan status |
| `config/agent-tool-registry.json` | ADR 0069 | Self-describing tool surface for agents |
| `docs/schema/mutation-audit-event.json` | ADR 0066 | Audit event schema |
| `docs/schema/platform-finding.json` | ADR 0071 | Drift finding schema |
| `inventory/group_vars/platform.yml` | ADR 0063 | Generated topology facts |
| `receipts/image-scans/` | ADR 0068 | CVE scan receipts per image |

---

## Agentic Surface After Full Rollout

When all ten ADRs are live, an agent interacting with this platform can:

- **discover** what tools are available by reading `config/agent-tool-registry.json` or loading the MCP tool export
- **query** platform topology, health, and recent history by calling `query-platform-context` (RAG) or `get-platform-status` (live probes)
- **observe** the current drift posture via the NATS `platform.findings.observation` stream or the Open WebUI daily digest
- **execute** an approved workflow by calling an `execute` category tool subject to the command approval gate
- **audit** any past mutation by querying the Loki `{job="mutation-audit"}` label stream
- **ground** its answers in repo truth via the RAG index over ADRs, runbooks, receipts, and `stack.yaml`

The combination of a governed tool registry, a grounded retrieval layer, and a proactive observation loop creates an agent that can be genuinely useful for day-to-day operations without requiring broad shell access or bespoke integration work for each new capability.

---

## Operating Principles For This ADR Set

- repository remains the design authority; every new machine-readable catalog has a committed schema and a validation gate
- no agentic mutation capability is added before its audit trail is in place
- network policy changes require a maintenance-window receipt before merge
- image pins and scan receipts are committed alongside the Compose change, not after
- agents get named tools and structured events, not generic root shells

---

## Verification Targets

Implementation is considered successful when:

- `make validate` enforces argument specs on new roles and detects missing probe contracts
- a compromised container on `docker-runtime` cannot reach `postgres` on any port outside the declared policy
- no managed container runs from an unpinned image or an image with a critical CVE
- every static secret has a rotation record in `secret-catalog.json` with a last-rotated timestamp within its declared period
- an agent can answer "what changed on the platform in the last 24 hours" by querying the mutation audit log without SSH access
- the observation loop emits findings for all six checks within 4 hours of any drift event
