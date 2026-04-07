# WS-0216-0219: Data & Replication Strategy Implementation

**Status**: Ready for Review
**Owner**: claude
**Branch**: `claude/ws-0216-0219-data-replication`
**Worktree**: `.claude/worktrees/ws-0216-0219-data-replication`
**Date**: 2026-04-07
**Related ADRs**: 0216, 0217, 0218, 0219

## Objective

Implement a comprehensive data classification and replication strategy that defines:

1. Criticality ring taxonomy for service classification
2. One-way environment data flow authority
3. Single-writer relational database HA policy
4. Per-data-class replication rules

## Deliverables

This workstream delivers four key architecture documents:

### 1. Service Criticality Rings (`docs/architecture/criticality-rings.yaml`)

**Purpose**: Classify all platform services into criticality rings that express recovery and dependency priority.

**Key Definitions**:
- **Foundation Ring**: Keycloak, Step-CA, OpenBao, PostgreSQL, API Gateway
  - Required to establish trust, operator control, and data recovery
  - Must be operationally independent
  - Cannot depend on core, supporting, or peripheral services

- **Core Ring**: NATS JetStream, Gitea, Docker Runtime, Harbor, Nomad, Temporal
  - Required for normal platform control and production-facing operation
  - May depend on foundation services
  - Enable application delivery and workload scheduling

- **Supporting Ring**: Grafana, Alertmanager, Uptime Kuma, Backup PBS, MinIO, Redpanda
  - Materially improve operations but not required to restore foundation/core
  - May depend on core or foundation
  - Enable observability, backup, and operational convenience

- **Peripheral Ring**: Open WebUI, Dify, Woodpecker, Grist, Nextcloud, Mattermost, N8N, Label Studio, etc.
  - Convenience, experimental, or low-blast-radius services
  - Can be deferred during restore and failover
  - May depend on any ring

**Dependency Rule**: Dependencies are inward-only. Peripheral may depend on any ring; supporting on core or foundation; core on foundation; foundation on nothing else.

**Current Platform Coverage**: All 73 services classified.

### 2. Environment Data Policy (`docs/architecture/environment-data-policy.yaml`)

**Purpose**: Enforce one-way data authority between production and staging environments.

**Core Principle**: Production is the sole authority for live mutable data. Staging is a validation environment that must never write upstream into production.

**Allowed Cross-Environment Data Patterns**:

1. **Synthetic Seed**: Fully generated, non-production test data
   - Source: staging-generated
   - Used for: realistic test scenarios with no production data exposure

2. **Sanitized Snapshot**: Masked snapshot exported from production
   - Source: production
   - Transformation: PII removal, credential redaction, encryption key rotation
   - Frequency: on-demand after approval

3. **Logical Subset**: Filtered and approved subset of production data
   - Source: production
   - Filter: explicit allow-list of tables/rows/schemas
   - Example: public configuration only, no user data

4. **Event Replay**: Bounded replay of approved events from production
   - Source: production event log
   - Bounds: time window, event types, source systems
   - Scrubbing: credentials and PII removed

**Forbidden Patterns**:
- Bidirectional database replication
- Staging members in production quorum
- Staging as automatic production failover
- Staging-mutated records flowing back to production

**Enforcement Mechanisms**:
- Network isolation separates production and staging cells
- PostgreSQL endpoint contracts (rw_endpoint, ro_endpoint, admin_endpoint)
- Environment-local secret authorities (separate OpenBao per environment)
- Event consumers declare environment membership
- All exports logged and audited

### 3. Replication Policies (`docs/architecture/replication-policies.yaml`)

**Purpose**: Define replication rules by data class, not by product name alone.

**Data Classes and Rules**:

| Data Class | Intra-Env HA | Cross-Env Replication | Rule |
|------------|--------------|----------------------|------|
| Relational Databases | Single-writer + replicas | One-way snapshot/export only | ADR 0218 |
| Queues & Streams | Cluster quorum | Forbidden (use event replay) | ADR 0219 |
| Object Stores | Erasure coding or replication | Versioned approved prefixes only | ADR 0219 |
| Search & Indexes | Coordinator + replicas | Forbidden (rebuild from source) | ADR 0219 |
| Cache & Sessions | Cluster or partitioned | Forbidden (rebuild on miss) | ADR 0219 |
| Secrets & Keys | Distributed authority | Only bootstrap trust anchors | ADR 0219 |
| Time-Series & Observability | Time-window retention | Downsampled forwarding only | ADR 0219 |

**Key Insights**:

1. **Relational Databases** (PostgreSQL)
   - Single writer per environment
   - Staging gets data via snapshot/logical export, never bidirectional sync
   - Each environment owns separate cluster

2. **Queues and Streams** (NATS, Redpanda)
   - Intra-environment clustering only
   - Staging consumers are completely separate from production
   - Bounded event replay for testing (with scrubbed data)

3. **Object Stores** (MinIO, S3)
   - Production and staging buckets are isolated
   - Approved prefixes can be versioned-replicated
   - Staging writes stay in staging namespace

4. **Search and Vector Indexes** (Qdrant, Typesense)
   - Treated as derived/cache state
   - Rebuild from canonical upstream source preferred
   - No cross-environment synchronization

5. **Cache and Sessions** (Redis)
   - Completely environment-local
   - Loss acceptable; rebuilt on demand
   - Never replicated across environments

6. **Secrets and Keys** (OpenBao, Step-CA)
   - Each environment has its own authority and sealing boundary
   - Only narrow bootstrap trust anchors exported
   - Prevents staging breach from compromising production

7. **Time-Series and Observability** (Prometheus, Grafana, Logs, Traces)
   - Metrics downsampled before forwarding to shared analysis
   - Logs filtered to remove sensitive data
   - Traces sampled to reduce volume
   - Raw production detail stays local

## Current Platform State

### Foundation Ring (Active)
- **Keycloak**: OIDC authority, running
- **Step-CA**: Short-lived certificate authority, running
- **OpenBao**: Secret authority, running (single instance)
- **PostgreSQL**: Relational authority (10.10.10.60), running, no HA standby yet
- **API Gateway**: Unified operator access, running

### Core Ring (Active)
- **NATS JetStream**: Event bus, running, cluster mode active
- **Gitea**: Source control, running
- **Docker Runtime**: Service execution, running
- **Harbor**: Image registry, running
- **Nomad**: Scheduler, running
- **Temporal**: Workflow engine, running

### Supporting Ring (Active)
- **Grafana**: Dashboards and alerts, running
- **Alertmanager**: Alert routing, running
- **Uptime Kuma**: Health monitoring, running
- **Backup PBS**: VM snapshots, running
- **MinIO**: Object storage, running (single instance, no erasure coding)
- **Redpanda**: Message streaming, running (single-broker)

### Peripheral Ring (Active)
- All 40+ remaining services deployed and operational

## Implementation Decisions and Rationale

### 1. Ring Classification Approach

**Decision**: Use four-ring taxonomy (foundation, core, supporting, peripheral) instead of flat redundancy tiers.

**Rationale**:
- Redundancy tier (R0-R3) answers "how many copies?" but not "what order to bring up?"
- Criticality rings directly answer recovery priority and dependency direction
- Rings provide operational clarity for disaster recovery and failover rehearsal

**Trade-off**: Some services require reclassification discussions (e.g., is Headscale core or supporting?).

### 2. One-Way Authority Enforcement

**Decision**: Production is sole authority; staging never writes back.

**Rationale**:
- Production is the system of record for all mutable business data
- Staging must remain testable without risk of corrupting production
- Separates code/config promotion (can go both ways) from data (one-way)

**Trade-off**: Staging realism now depends on explicit export pipelines; some real-time shadowing becomes harder.

### 3. Data-Class Approach Over Product-Name

**Decision**: Define replication by data class (queues, objects, search, cache, secrets, time-series) rather than product (NATS, Redis, Qdrant, etc.).

**Rationale**:
- Different data types have fundamentally different replication guarantees
- Cache loss is acceptable; secrets loss is critical—they need different rules
- Queues need consumer isolation; relational needs ACID—they need different models

**Trade-off**: Operators must understand more than one replication mode.

### 4. Rebuild-Over-Replicate for Derived State

**Decision**: Search indexes, caches, and ephemeral state are rebuilt from source, not replicated.

**Rationale**:
- Derived state is not authoritative; loss does not compromise data integrity
- Rebuilding is simpler than maintaining cross-environment replication
- Environments stay operationally isolated

**Trade-off**: Rebuilding takes time; staging may lag production freshness.

### 5. Per-Environment Secret Authorities

**Decision**: OpenBao and Step-CA maintain separate sealing boundaries per environment.

**Rationale**:
- Staging breach cannot compromise production credentials
- Production secrets remain inaccessible from staging infrastructure
- Clear blast-radius boundaries

**Trade-off**: Bootstrapping shared trust anchors requires careful design.

## Relationship to Existing ADRs

- **ADR 0216**: Service Criticality Rings — this document operationalizes the ring model
- **ADR 0217**: One-Way Environment Data Flow — this document defines allowed patterns and enforcement
- **ADR 0218**: Relational Database Replication — this document specifies endpoint contracts and HA per environment
- **ADR 0219**: Data-Class Replication Policies — this document details rules for each data type

All three YAML files are direct implementations of the accepted decisions in ADRs 0216, 0217, 0218, and 0219.

## Scope and Boundaries

**In Scope**:
- Classification of all 73 active platform services
- Definition of allowed cross-environment data patterns
- Replication rules for each data class
- Current platform state assessment

**Out of Scope**:
- Implementation of actual backup/export automation (future workstream)
- Deployment of staging environment (future workstream)
- Change to product selection or vendor relationships
- Service-specific sizing, tuning, or schema ownership

**Not a Configuration**:
- These documents define policy and architecture, not automation or IaC
- Ansible roles, playbooks, and operational procedures remain separate
- No changes to existing deployed services

## Validation and Verification

All three YAML files have been:
- ✓ Created with valid YAML syntax
- ✓ Mapped to all services from service-capability-catalog.json
- ✓ Validated against ring dependency rules (inward-only)
- ✓ Cross-referenced with existing ADRs
- ✓ Aligned with current platform deployment state

## Next Steps (Future Workstreams)

1. **WS-????**: Implement sanitized snapshot export automation
2. **WS-????**: Deploy staging environment with separate clusters (postgres, NATS, Redpanda, MinIO)
3. **WS-????**: Implement bounded event replay system
4. **WS-????**: Build search index rebuild automation
5. **WS-????**: Audit logging for all environment-to-environment data flows
6. **WS-????**: Validate network isolation (staging cannot initiate to production)

## Files Created

1. `docs/architecture/criticality-rings.yaml` — 600+ lines, all services classified
2. `docs/architecture/environment-data-policy.yaml` — 450+ lines, allowed patterns and enforcement
3. `docs/architecture/replication-policies.yaml` — 800+ lines, per-data-class rules and current state
4. `docs/workstreams/ws-0216-0219-data-replication.md` — this implementation summary

## Commit Message

```
[adr-0216-0219] Data & replication strategy implementation

Deliver criticality-rings.yaml, environment-data-policy.yaml, and replication-policies.yaml.

- Classify all 73 services into foundation/core/supporting/peripheral rings
- Define allowed one-way environment data patterns (synthetic_seed, sanitized_snapshot, logical_subset, event_replay)
- Per-data-class replication rules for databases, queues, object stores, search, cache, secrets, time-series
- Current platform state assessment and enforcement mechanisms
- All files align with ADRs 0216, 0217, 0218, 0219

Ready for review and integration.
```

## Sign-Off

This workstream is complete and ready for review. All deliverables are in place:

- [x] `docs/architecture/criticality-rings.yaml`
- [x] `docs/architecture/environment-data-policy.yaml`
- [x] `docs/architecture/replication-policies.yaml`
- [x] `docs/workstreams/ws-0216-0219-data-replication.md`
- [x] No changes to VERSION, changelog.md, RELEASE.md
- [x] All files committed and branch pushed
