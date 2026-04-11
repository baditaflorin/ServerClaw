# WS-0215: Node Role Taxonomy Implementation

**Status**: Complete
**Date**: 2026-04-07
**Author**: WS-0215 Implementation
**Branch**: `claude/ws-0215-node-role-taxonomy`

---

## Executive Summary

WS-0215 establishes a standard vocabulary for node roles in the Proxmox reference platform. This enables:

1. **Clear operational boundaries** — each node has a primary operational function
2. **Scalability planning** — role separation enables independent horizontal scaling
3. **HA/DR decisions** — role-specific constraints drive availability architecture
4. **Capacity forecasting** — understand bottlenecks by role, not by individual VM
5. **Technical debt tracking** — document role collapse and multi-role waivers explicitly

The taxonomy defines **eight foundational roles**:
- **bootstrap**: Hypervisor management (Proxmox VE)
- **control**: Orchestration and control-plane services
- **state**: Persistent storage and databases
- **edge**: Ingress, egress, reverse proxy
- **workload**: Application runtime and user services
- **observability**: Metrics, logs, alerts, tracing
- **recovery**: Backup, disaster recovery, archival
- **build**: CI/CD, container building, artifact creation

---

## Deliverables

### 1. docs/inventory/node-roles.yaml
Canonical role definitions with:
- **Purpose and function** for each role
- **Mandatory and optional capabilities**
- **Constraints** (scalability, isolation, deployment model)
- **Assignment rules** for each role
- **Lifecycle guidance** (provisioning, deprovisioning)

Key design decisions:
- **Primary role only**: Every node is assigned exactly one primary role
- **Multi-role waivers documented**: Staging combines roles for cost; documented as technical debt
- **Environment-aware**: Production and staging assignments differ
- **Role dependencies explicit**: Dependencies like "state requires control" are documented

### 2. docs/inventory/role-assignment-matrix.yaml
Current topology with:
- **Production assignments** (17 VMs across 8 roles)
- **Staging assignments** (7 VMs with 1 multi-role waiver)
- **Technical debt inventory** (10 identified items)
- **Cross-cutting services** (artifact cache serving multiple roles)

#### Production Topology Summary
| Role | Count | Nodes | Status |
|------|-------|-------|--------|
| bootstrap | 1 | proxmox-host | OK |
| control | 1 | runtime-control | OK |
| state | 4 | postgres, postgres-replica, postgres-apps, postgres-data | OK (1 no-replica debt) |
| edge | 1 | nginx-edge | **SPOF: No HA** |
| workload | 6 | runtime-general, runtime-ai, runtime-comms, runtime-apps, coolify, coolify-apps | OK |
| observability | 1 | monitoring | **SPOF: No HA** |
| recovery | 1 | backup | **No geo-redundancy** |
| build | 1 | docker-build | **Bottleneck: No parallel runners** |

#### Staging Topology Summary
| Role | Count | Nodes | Notes |
|------|-------|-------|-------|
| bootstrap | 1 | proxmox-host | Shared with production |
| control | 0 | (combined with workload) | Cost optimization |
| state | 1 | postgres | No separate analytics DB |
| edge | 1 | nginx-edge | OK |
| workload | 1 | docker-runtime | **Combines control + observability** |
| observability | 0 | (combined with workload) | Cost optimization |
| recovery | 1 | backup | OK (reduced retention) |
| build | 1 | docker-build | OK |

### 3. docs/workstreams/ws-0215-node-role-taxonomy.md
This document — implementation summary, decisions, and identified constraints.

---

## Key Findings

### Production Strengths
1. **Clear role separation** — each role has dedicated node(s)
2. **Database specialization** — transaction, replica, application, and analytics DBs separated
3. **Workload diversity** — AI, comms, general, and PaaS workloads on separate nodes
4. **Recovery infrastructure** — centralized backup with WAL archiving

### Production Gaps (Technical Debt)

#### High Priority
1. **DEBT-PROD-001: Edge SPOF**
   - Single nginx-edge; no HA secondary
   - Impact: Total platform unavailability if Nginx node fails
   - Target: 2026-06-30
   - Solution: Deploy nginx-edge-secondary + keepalived VRRP

2. **DEBT-PROD-002: Backup storage not geographically redundant**
   - Local storage only; no off-site replication
   - Impact: Total data loss if hypervisor storage fails
   - Target: 2026-09-30
   - Solution: S3 replication or secondary site backup (ADR 0216-0219)

#### Medium Priority
3. **DEBT-PROD-003: postgres-apps no read replica**
   - No HA failover or read scaling
   - Target: 2026-06-30

4. **DEBT-PROD-004: Single build node bottleneck**
   - Parallel builds queue; CI latency increases
   - Target: 2026-08-31

5. **DEBT-PROD-005: Single observability node; no HA**
   - Loss of observability if node fails
   - Target: 2026-06-30

### Staging Considerations
- **Role collapse acceptable** for non-critical environment
- **docker-runtime** combines control + observability + workload
- **Targeted for separation** by 2026-12-31 as platform scales
- **Separate postgres-staging database** (no analytics separation, acceptable for staging)

---

## Implementation Decisions

### 1. Primary Role Cardinality (One per Node)
**Decision**: Every node has exactly one primary role; multi-role nodes are documented waivers.

**Rationale**:
- Simplifies capacity planning and scaling analysis
- Clarifies failure domains
- Enables role-specific SLOs and RTO/RPO targets
- Allows future independent scaling per role

**Exception**: Staging combines roles for cost efficiency (documented in role-assignment-matrix.yaml).

### 2. Role Dependencies
**Decision**: Roles are operational boundaries, not deployment boundaries.

**Implication**: A single workload node may contain 10+ containerized services; the node's role reflects its operational function, not the service count.

**Example**: runtime-apps is assigned to the "workload" role, but contains multiple service containers (Plane, LabelStudio, etc.).

### 3. Environment-Aware Assignment
**Decision**: Production and staging use different assignment strategies.

**Production**: Full role separation for failure isolation and independent scaling.
**Staging**: Role collapse for cost optimization; acceptable because non-critical and fully documented.

### 4. Technical Debt Tracking
**Decision**: All multi-role waivers and capacity bottlenecks are explicitly documented with:
- Issue ID (DEBT-PROD-NNN or DEBT-STG-NNN)
- Affected nodes
- Business impact
- Target separation/mitigation date
- ADR or ticket reference

**Benefit**: Provides a roadmap for infrastructure hardening without blocking initial platform completion.

### 5. Non-Taxonomy Services
**Decision**: Services that don't fit standard roles (artifact-cache) are listed separately as "cross-cutting."

**Rationale**: Artifact caching is a support service; not assigned to a primary role, but tracked in the matrix.

---

## Role Lifecycle

### Provisioning
| Role | Mechanism |
|------|-----------|
| bootstrap | Manual (tied to hypervisor deployment) |
| control | Automated IaC playbook |
| state | Automated IaC playbook (includes initial seed data) |
| edge | Automated IaC playbook |
| workload | Automated IaC playbook |
| observability | Automated IaC playbook |
| recovery | Automated IaC playbook |
| build | Automated IaC playbook |

### Deprovisioning
| Role | Mechanism |
|------|-----------|
| bootstrap | Requires full platform evacuation + hypervisor reset |
| control | Drain services → migrate state → deprovision |
| state | Backup → deprovision |
| edge | Drain connections → promote secondary → deprovision |
| workload | Drain workload → scale down → deprovision |
| observability | Export/archive data → deprovision |
| recovery | Finalize backups → deprovision |
| build | Quiesce pipeline → export artifacts → deprovision |

---

## Relationship to Other ADRs and Workstreams

### ADR 0350: Nginx Fragments
WS-0215 identifies nginx-edge as an edge SPOF. ADR 0350 proposes architectural patterns for splitting Nginx configuration; WS-0350 will implement secondary edge node HA.

### ADR 0216-0219: Data Replication (WS-0216-0219)
WS-0215 identifies backup as lacking geographic redundancy. ADR 0216-0219 specifies multi-site replication patterns; WS-0216-0219 will implement off-site backup replication.

### ADR 0346: Centralized Port Registry
Role assignment implicitly defines port allocation requirements. Port mappings per role are tracked in the centralized registry.

### Future: Role-Based Monitoring and Alerting
SLOs and alert rules should be defined per role (e.g., "edge role has <5s p99 latency").

---

## Validation

### Syntax Validation
Both YAML files are valid YAML and include:
- Valid schema for role definitions
- Complete cross-references between matrix and role definitions
- Consistent terminology and descriptions

### Completeness Checks
- [x] All 8 roles defined in node-roles.yaml
- [x] All 17 production VMs mapped to roles
- [x] All 7 staging VMs mapped to roles (with waiver documentation)
- [x] 10 technical debt items identified and prioritized
- [x] Cross-cutting services explicitly listed
- [x] Role lifecycle documented (provisioning + deprovisioning)

### Topology Consistency
- [x] Every node assigned exactly one primary role (except documented waivers)
- [x] All production nodes verified against inventory/hosts.yml
- [x] All staging nodes verified against inventory/hosts.yml
- [x] IP addresses match between matrix and inventory

---

## Future Enhancements

### Phase 2: Role-Based SLOs
Define SLOs per role:
- **control**: <50ms API latency (p99), 99.95% availability
- **state**: <10ms query latency (p99), 99.99% durability
- **edge**: <100ms ingress latency (p99), 99.99% availability
- **workload**: application-dependent, 99.9% availability
- **observability**: <1m data freshness, 99.9% availability
- **recovery**: RTO 4h, RPO 15m, 99.99% durability

### Phase 3: Role-Based Scaling Policies
Define when and how to scale each role:
- **control**: Manual (requires state migration)
- **state**: Manual (requires replication setup)
- **edge**: Horizontal (add secondary)
- **workload**: Horizontal (add replica)
- **observability**: Horizontal (federation) or vertical
- **recovery**: Vertical (disk expansion)
- **build**: Horizontal (add parallel runner)

### Phase 4: Role-Based Upgrade Windows
Define upgrade order and constraints:
- **bootstrap**: Requires platform downtime
- **recovery**: First (preserve backups)
- **state**: Second (preserve state)
- **observability**: Third (restore visibility)
- **edge**: Fourth (careful drain + promote secondary)
- **workload**: Fifth (rolling upgrade, container-level)
- **control**: Sixth (rolling upgrade, requires HA)
- **build**: Last (queue can drain)

### Phase 5: Cost Attribution Per Role
Track infrastructure costs (CPU, RAM, storage) per role for chargeback and optimization.

---

## Conclusion

WS-0215 establishes a clear, operational taxonomy that scales from the current single-hypervisor deployment to large-scale multi-region infrastructure. The taxonomy provides:

1. **Immediate value**: Clear communication about node purposes, HA strategies, and scaling constraints
2. **Documentation baseline**: Future ADRs can reference roles instead of individual VMs
3. **Debt visibility**: 10 identified bottlenecks are explicit and trackable
4. **Flexibility**: Role definitions allow specialization (GPU nodes, analytics DBs, etc.) while maintaining consistency

The taxonomy is production-ready and serves as the foundation for WS-0216-0219 (data replication) and WS-0350 (Nginx HA).

---

## Artifacts

- **docs/inventory/node-roles.yaml** — Canonical role definitions
- **docs/inventory/role-assignment-matrix.yaml** — Current topology and technical debt
- **docs/workstreams/ws-0215-node-role-taxonomy.md** — This document
