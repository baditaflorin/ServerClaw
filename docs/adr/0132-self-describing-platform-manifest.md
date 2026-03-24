# ADR 0132: Self-Describing Platform Manifest

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Every component in the ADR 0123–0131 series — the session bootstrap, the event taxonomy, the capability policy, the closure loop, the conflict detector, the health index, the runbook executor, the state store, the handoff protocol — is individually well-specified. But an agent starting a new session still faces a discovery problem: it must call multiple APIs to understand what the platform is, what state it is in, what it can do, and what is currently broken.

The session bootstrap (ADR 0123) provides a `SessionContext` with health, mutations, incidents, and maintenance windows. But an agent that has not operated on this platform before — or a new automation tool being onboarded — also needs to know:

- What services exist and what their SLOs are.
- What workflows are available and what their capability requirements are.
- What agents are currently registered and what they are authorised to do.
- What runbooks are available and which are automation-eligible.
- What the current platform version is and what changed in the last release.
- What the overall agentic architecture is: which components exist, how they connect, what each does.

This information is scattered across `config/service-capability-catalog.json`, `config/workflow-catalog.json`, `config/agent-policies.yaml`, `docs/runbooks/`, `docs/adr/`, and the world-state materializer. There is no single document an agent can fetch to bootstrap its understanding of the entire platform.

The absence of a self-describing manifest means:
- New agent implementations require significant discovery work before they can act safely.
- Agents operating across a version boundary (ADR 0110) have no mechanism to detect that the platform changed since their last session.
- External tools (Claude Code, monitoring integrations, audit systems) that want to understand the platform's current state must know the internal API structure before they can ask a meaningful question.

## Decision

We will generate and continuously publish a **self-describing platform manifest** as a structured JSON document, refreshed on every platform version increment and on significant state changes. The manifest is served at a canonical endpoint and is the first document any new agent or tool should fetch.

### Manifest structure

```json
{
  "manifest_version": "1.0",
  "platform_version": "0.110.0",
  "generated_at": "2026-03-24T14:32:01Z",
  "next_refresh_at": "2026-03-24T15:32:01Z",
  "environment": "production",

  "identity": {
    "platform_name": "lv3.org",
    "operator": "live",
    "description": "Single-node Proxmox homelab with agentic operations automation"
  },

  "health": {
    "summary": "healthy",          // 'healthy' | 'degraded' | 'critical'
    "services": {
      "netbox":   {"status": "healthy",  "score": 0.94, "safe_to_act": true},
      "postgres": {"status": "healthy",  "score": 0.97, "safe_to_act": true},
      "step-ca":  {"status": "degraded", "score": 0.61, "safe_to_act": false,
                   "reason": "SLO error budget 38% remaining"}
    }
  },

  "incidents": {
    "open_count": 1,
    "items": [
      {
        "incident_id": "inc-2026-03-24-step-ca-001",
        "service": "step-ca",
        "top_hypothesis": "TLS certificate near expiry",
        "confidence": 0.92,
        "loop_state": "PROPOSING",
        "ts_fired": "2026-03-24T13:55:00Z"
      }
    ]
  },

  "maintenance": {
    "active_windows": [],
    "upcoming_windows": [
      {"window_id": "mw-2026-03-25-001", "description": "Step-CA upgrade", "starts_at": "2026-03-25T02:00Z", "duration_minutes": 60}
    ]
  },

  "capabilities": {
    "available_workflows": [
      {
        "id": "converge-netbox",
        "description": "Deploy or converge the NetBox service",
        "tags": ["converge", "mutation"],
        "risk_class": "MEDIUM",
        "automation_eligible": true,
        "agent_trust_required": "T2",
        "budget": {"max_duration_seconds": 300, "max_concurrent_instances": 1}
      }
    ],
    "automation_eligible_runbooks": [
      {
        "id": "renew-tls-certificate",
        "title": "Renew an expiring TLS certificate",
        "agent_trust_required": "T2",
        "steps": 4
      }
    ]
  },

  "agents": {
    "registered": [
      {
        "agent_id": "agent/triage-loop",
        "trust_tier": "T2",
        "description": "Automated triage triggered on every alert",
        "status": "active"
      },
      {
        "agent_id": "agent/observation-loop",
        "trust_tier": "T2",
        "description": "Scheduled 4-hourly drift and health observation",
        "status": "active"
      }
    ]
  },

  "recent_changes": {
    "last_version": "0.109.0",
    "deployed_at": "2026-03-20T09:00Z",
    "summary": "Implemented ADR 0114 incident triage engine",
    "release_notes_url": "docs/release-notes/0.110.0.md"
  },

  "agentic_architecture": {
    "overview": "Intent-driven mutation with pre-execution diff, risk scoring, health gating, and budget enforcement",
    "entry_points": [
      {"component": "Platform CLI", "endpoint": "lv3 <instruction>", "adr": "0090"},
      {"component": "Ops portal", "endpoint": "https://ops.lv3.org", "adr": "0093"},
      {"component": "NATS subscription", "topic": "platform.>", "adr": "0124"}
    ],
    "pipeline": [
      "Bootstrap (ADR 0123) → Goal compiler (ADR 0112) → Conflict check (ADR 0127) → Health check (ADR 0128) → Risk scorer (ADR 0116) → Approval gate (ADR 0048) → Scheduler (ADR 0119) → Windmill → Ledger (ADR 0115)"
    ],
    "autonomous_loop": [
      "Observation (ADR 0071) → Triage (ADR 0114) → Closure loop (ADR 0126) → Runbook executor (ADR 0129) → Case library (ADR 0118)"
    ]
  },

  "data_sources": {
    "world_state_api": "platform.WorldStateClient (ADR 0113)",
    "ledger_api": "platform.LedgerReader (ADR 0115)",
    "search_api": "platform.SearchClient (ADR 0121)",
    "health_api": "platform.HealthCompositeClient (ADR 0128)",
    "bootstrap_api": "platform.BootstrapClient (ADR 0123)"
  },

  "known_gaps": [
    "ADR 0121 (search fabric): Not yet implemented in platform",
    "ADR 0126 (closure loop): Not yet implemented in platform"
  ]
}
```

### Generation

The manifest is generated by a Windmill workflow `generate-platform-manifest` that runs:
- On every successful platform version increment (post-deploy hook).
- Every 60 minutes (heartbeat refresh for dynamic sections: health, incidents, maintenance).
- On demand via `lv3 manifest refresh`.

The workflow assembles the manifest from:
- Static sections (`identity`, `agentic_architecture`, `data_sources`): from `config/manifest-static.yaml`, updated only on version changes.
- Dynamic sections (`health`, `incidents`, `maintenance`, `recent_changes`): from the session bootstrap (ADR 0123), health composite index (ADR 0128), and closure loop state.
- Capability sections (`capabilities`, `agents`): from the workflow catalog (ADR 0048) and agent policies (ADR 0125).
- Known gaps: automatically derived by diffing the ADR implementation status fields against deployed components.

### Serving

The manifest is published to three locations:

1. **Postgres `manifest.current`**: single-row table with the latest manifest JSON. All platform components that need the manifest read from here.
2. **Platform API gateway** (ADR 0092): `GET /v1/manifest` returns the current manifest with a `Cache-Control: max-age=60` header.
3. **Static file**: `build/platform-manifest.json`, generated during CI and committed, for tooling that cannot reach the live API.

### Version change detection

Every manifest includes `platform_version` and `generated_at`. An agent that persists the manifest across sessions (using the state store, ADR 0130) can detect platform version changes by comparing:

```python
ctx = BootstrapClient().hydrate(...)
manifest = ManifestClient().get()

last_known = state.read("last_manifest_version")
if last_known and manifest["platform_version"] != last_known:
    # Platform was upgraded since last session — re-read capabilities, workflows, policies
    state.write("last_manifest_version", manifest["platform_version"])
    self._reinitialise_from_manifest(manifest)
```

### `known_gaps` section

The `known_gaps` section lists ADRs that are `Proposed` but `Not Implemented`. It is generated by parsing the frontmatter of all ADR files and filtering for `Status: Proposed` + `Implementation Status: Not Implemented`. This gives any agent operating on the platform a machine-readable list of capabilities it should not assume are available, without requiring it to read all 130+ ADR documents.

### Platform CLI

```bash
$ lv3 manifest show
Platform: lv3.org (v0.110.0)  |  Health: degraded (1/6 services unsafe)
Open incidents: 1  |  Maintenance windows: 0 active, 1 upcoming

Unsafe services:
  step-ca  degraded  0.61  — SLO error budget 38% remaining

Known gaps (not yet implemented):
  ADR 0121  local-search-and-indexing-fabric
  ADR 0126  observation-to-action-closure-loop
  ADR 0129  runbook-automation-executor

$ lv3 manifest show --json > /tmp/platform.json
```

## Consequences

**Positive**

- A new agent or tool can fetch a single document and immediately understand the platform's current state, available capabilities, agentic architecture, and known limitations. No discovery work is required before acting.
- The `known_gaps` section prevents agents from attempting to use capabilities that are architecturally designed but not yet deployed, avoiding hard-to-debug failures.
- The `platform_version` field enables agents to detect version changes and reinitialise their understanding of the platform without requiring human notification.
- The manifest consolidates information that was previously spread across 7+ config files and multiple APIs into a single coherent document that is both human-readable and machine-parseable.

**Negative / Trade-offs**

- The manifest must be kept in sync with the platform's actual state. If the `generate-platform-manifest` workflow fails silently, agents will operate from a stale manifest. The manifest must itself be monitored and have a freshness alert.
- The static `build/platform-manifest.json` committed to the repository will lag the live manifest by however long the CI pipeline takes. Agents that read from the static file may miss dynamic state changes.
- The `known_gaps` auto-derivation assumes that ADR implementation status fields are kept accurate. If an ADR is implemented but its status is not updated, the gap will be incorrectly listed.

## Boundaries

- The manifest is a read-only, generated document. No component writes to it directly; it is always produced by the `generate-platform-manifest` workflow from authoritative sources.
- The manifest does not replace the individual APIs (world state, ledger, search, health). It is a discovery and orientation document, not a substitute for direct API calls.
- The manifest does not include sensitive information: no secrets, no internal IP addresses, no credentials. The `data_sources` section lists API identifiers, not connection strings.

## Related ADRs

- ADR 0046: Identity classes (agents section of manifest)
- ADR 0048: Command catalog (capabilities section sourced here)
- ADR 0071: Agent observation loop (agentic_architecture autonomous_loop)
- ADR 0090: Platform CLI (`lv3 manifest` commands)
- ADR 0092: Unified platform API gateway (`/v1/manifest` endpoint)
- ADR 0096: SLO error budget tracking (health score inputs)
- ADR 0110: Platform versioning (platform_version and recent_changes)
- ADR 0112: Deterministic goal compiler (agentic_architecture pipeline)
- ADR 0113: World-state materializer (dynamic health and incident sections)
- ADR 0114: Rule-based incident triage engine (incidents section)
- ADR 0123: Agent session bootstrap (manifest complements the SessionContext)
- ADR 0125: Agent capability bounds (agents section sourced from agent-policies.yaml)
- ADR 0126: Observation-to-action closure loop (agentic_architecture autonomous_loop)
- ADR 0128: Platform health composite index (health section sourced here)
- ADR 0129: Runbook automation executor (automation_eligible_runbooks in capabilities)
- ADR 0130: Agent state persistence (agents persist manifest version for change detection)
