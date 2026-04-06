# ADR 0025 Gap Analysis Matrix

**Purpose**: Detailed breakdown of missing implementation components across ADR 0025 requirements.
**Created**: 2026-04-06
**Scope**: WS-0403 Analysis Phase

---

## Gap Matrix: Implementation Status by Requirement

| # | ADR 0025 Requirement | Gap | Current State | Missing | Impact | Effort | Phase |
|---|-----|-----|--------|---------|--------|--------|-------|
| 1 | Runtime stacks declared with Docker Compose v2 | Compose file structure | 94% complete (64/68 roles) | 4 roles lack compose templates; no compose v3+ migration path | Incomplete coverage; future-proofing unclear | Low | 1 |
| 2 | Predictable host layout (/srv/ versioning, env files, volumes explicit) | File location standardization | Partial (ADR 0373 defines convention) | No enforcement mechanism; mixed /opt/ and /srv/ usage; no validation on new roles | Layout unpredictable; data location migration risky | Low | 1 |
| 2a | Environment files declared explicitly | Env file handling | Complete | None identified | None | None | - |
| 2b | Bind mounts and named volumes declared explicitly | Volume declarations | Complete | None identified | None | None | - |
| 3 | Stack lifecycle host-managed, not shell-session-managed | **Systemd service integration** | **0% implemented** | No systemd units (service, timer, or target files) | Stacks invisible to systemd; boot recovery unreliable; no standard lifecycle management | High | 1-2 |
| 3a | Boot-time start behavior (guaranteed startup) | Boot recovery | Ad hoc (compose restart: unless-stopped) | No systemd unit to guarantee boot behavior; no dependency ordering | Services may fail to start if compose or Docker restart unexpectedly | High | 2 |
| 3b | Host-visible restart handling | Restart policy | Ad hoc (compose restart in role) | No systemd restart policy; no unified failure handling | Operators must manually `docker compose restart`; no automatic restart on failure | High | 1-2 |
| 3c | Failure handling visibility | Failure monitoring | Invisible to standard Linux monitoring | No systemd OnFailure, OnSuccess hooks | Monitoring cannot trigger alerts on service failure | High | 2 |
| 4 | Public exposure remains deliberate (no direct container exposure, mediated by NGINX edge) | Public access control | Complete (no port publication in compose; routed via API gateway) | None identified | None | None | - |
| 5 | Each stack must have an operator runbook (deployment, rollback, health, data persistence documented) | **Operator runbook standardization** | **40% coverage, no standard format** | 28 of 64 services lack runbooks; no standard structure; lifecycle (start/stop/rollback) not covered consistently | Operators lack discoverable procedures; knowledge encoded in shell history | Medium | 3 |
| 5a | Deployment procedure documented | Deployment runbook coverage | ~50% | 32 services lack deployment docs | Onboarding new operators is slow; deployment tribal knowledge | Medium | 3 |
| 5b | Rollback procedure documented | Rollback coverage | ~20% | 51 services lack rollback procedures | No standard way to revert a failed deployment; operator knowledge required | Medium | 3 |
| 5c | Health verification documented | Health check coverage | 56% (36/64 compose files have healthcheck; no runbook integration) | 28 services lack health checks; no operator guide to interpreting health state | Operators cannot diagnose service state; health checks not actionable | Medium | 2-3 |
| 5d | Data persistence locations documented | Data location coverage | ~40% | 38 services lack clear data persistence documentation | Backup, migration, and recovery procedures unsafe | Medium | 3 |

---

## Detailed Gap Breakdowns

### Gap 1: Systemd Service Integration (Critical Priority)

**ADR 0025 Requirement 3**: Stack lifecycle is host-managed, not shell-session-managed.

| Aspect | Current | Missing | Why It Matters |
|--------|---------|---------|----------------|
| Service units | None | All 64 need `lv3-<service>.service` files | Services are invisible to `systemctl`; no boot-time ordering |
| Timer units | None | ~20 need `lv3-<service>-health.timer` for active monitoring | Health checks run ad hoc; no alerting on degradation |
| Target units | None | All 64 need grouping target (e.g., `lv3-runtimes.target`) | Cannot order services across host boot; no dependency declaration |
| Restart policy | Ad hoc per role (compose `restart: unless-stopped`) | Standardized `Restart=on-failure` via systemd | Systemd restart more reliable than compose; better failure recovery |
| OnFailure hooks | None | All critical services need `OnFailure=` action | Cannot integrate with platform alerting/remediation |
| ExecStop cleanup | None | All services need `ExecStop=docker compose -f ... down` | Ungraceful shutdowns; data corruption risk |
| Dependencies | Implicit (no ordering) | All 64 need `After=` and `Wants=` declarations | Service startup order undefined; race conditions possible |

**Current workaround**: Each role defines `docker compose up -d` in its convergence task; relies on compose `restart: unless-stopped` for boot recovery. This is fragile and invisible to standard systemd monitoring.

**Impact**:
- Operators cannot use `systemctl start|stop|restart lv3-grist`
- Boot recovery depends on Docker daemon behavior, not systemd policy
- Monitoring cannot integrate with standard systemd state signals
- No automatic restart on failure; only manual operator intervention

**Solution approach** (Phase 1-2):
1. Design systemd templates (service, timer, target)
2. Extend service registry with systemd metadata
3. Auto-generate units from registry
4. Deploy units via each runtime role's convergence task

---

### Gap 2: Operator Runbook Standardization (High Priority)

**ADR 0025 Requirement 5**: Each stack must have an operator runbook.

| Aspect | Current | Missing | Why It Matters |
|--------|---------|---------|----------------|
| Runbook existence | ~26 of 64 (40%) | 38 services lack any runbook | Operators cannot discover procedures |
| Runbook structure | Ad hoc (no standard) | Standard template with sections: Deployment, Config, Health, Restart, Rollback, Data, Logs | Inconsistent format; hard to scan; knowledge scattered |
| Deployment procedure | ~30 of 64 documented (47%) | Clear step-by-step deployment guide for 34 services | New operators must reverse-engineer from Ansible code |
| Configuration guide | ~40 of 64 covered (62%) | Documented configuration parameters for 24 services | Operators change wrong variables; deployments fail |
| Health verification | ~15 of 64 (23%) | Procedure to verify service health for 49 services | No way to diagnose "is service up?" without Docker CLI knowledge |
| Restart procedure | ~10 of 64 (15%) | Step-by-step restart (graceful and forced) for 54 services | Manual `docker compose restart` and hope; no standard |
| Rollback procedure | ~13 of 64 (20%) | Rollback steps (image revert, data restore) for 51 services | Failed deployments become production incidents; manual recovery |
| Data persistence | ~26 of 64 (40%) | Clear documentation of persisted data location and backup strategy for 38 services | Data loss risk; backup/restore procedures missing |
| Logs & troubleshooting | ~35 of 64 (55%) | Standardized troubleshooting guide for each service | Operators manually run `docker compose logs`; no guidance |

**Current state**:
- Runbooks exist in `docs/runbooks/configure-<service>.md` for ~40% of services
- No standard structure or required sections
- Many focus on *configuration* only, not *lifecycle operations*
- No automation to regenerate runbooks when service registry changes

**Impact**:
- Operators cannot quickly find how to deploy, restart, or diagnose a service
- Onboarding new operators takes 2-3 weeks due to knowledge fragmentation
- Manual errors in deployments (wrong paths, wrong commands)
- No recovery playbook for common failures

**Solution approach** (Phase 3):
1. Design standard runbook template with required sections
2. Auto-generate runbooks from service registry + role metadata
3. Manual review and override for special cases
4. Keep runbooks in sync with code via automation

---

### Gap 3: Health Check Coverage (Medium Priority)

**ADR 0025 Related**: Health checks are essential for "operator runbooks" requirement; enable monitoring.

| Aspect | Current | Missing | Why It Matters |
|--------|---------|---------|----------------|
| Compose healthcheck directives | 36 of 64 (56%) | 28 services lack healthcheck blocks | 44% of services have no automated health signal |
| Health check diversity | HTTP GET, TCP, shell commands | Standardization; consistency across similar services | Some services have overly strict checks; false positives |
| Health check integration with runbooks | None | Link health checks to runbook "Health Verification" section | Operators don't know what `compose ps` output means |
| Health monitoring automation | None | Timer-based periodic verification; alerting on degradation | Health checks run on convergence only; no ongoing monitoring |
| Recovery automation | None | Automatic restart or alert when health check fails | Degraded service may run undetected for hours |

**Example gaps** (services without health checks):
- `directus_runtime` (critical data service)
- `harbor_runtime` (container registry)
- `keycloak_runtime` (auth service)
- `matrix_synapse_runtime` (messaging platform)
- `mattermost_runtime` (team chat)
- `ollama_runtime` (LLM service)

**Impact**:
- Operators cannot quickly determine if a service is healthy
- No automated alerting on service degradation
- Silent failures; services appear "running" but may be broken

**Solution approach** (Phase 2-3):
1. Add healthcheck directives to all 28 services without them
2. Document health checks in runbooks
3. Implement health check timer units (Phase 2 systemd)
4. Integrate with monitoring (future phase)

---

### Gap 4: File Location Standardization Enforcement (Low Priority)

**ADR 0025 Requirement 2**: Predictable host layout, with versioned `/srv/` paths.

| Aspect | Current | Missing | Why It Matters |
|--------|---------|---------|----------------|
| Path convention definition | Defined in ADR 0373 service registry | Enforcement mechanism (linting, pre-commit hook) | New roles may deviate; inconsistent layout |
| `/opt/` vs. `/srv/` usage | Mixed (older roles use `/opt/`, newer use `/srv/`) | Migration plan; all future roles use `/srv/` only | Host layout unpredictable; refactoring risky |
| Validation on role creation | None | Pre-commit hook: all roles use ADR 0373 derived variables for paths | Developers hardcode paths instead of deriving them |
| Path documentation | Some (in role defaults comments) | Central location documenting all service paths | Operators must read 64 different roles to understand layout |

**Example deviations**:
- Some roles use `{{ <service>_site_dir }}` (correct, derived)
- Others hardcode `/opt/<service>` in tasks (incorrect, brittle)

**Impact**:
- Layout not truly predictable; operators cannot safely assume paths
- Migration from `/opt/` to `/srv/` requires manual updates across multiple roles
- Refactoring (e.g., changing site directory) becomes fragile

**Solution approach** (Phase 1, validation only):
1. Add pre-commit hook to validate all runtime roles use ADR 0373 derived variables
2. Document standard paths in central location
3. Migration plan for older `/opt/` deployments (future phase)

---

### Gap 5: Service Registry Integration (Medium Priority)

**ADR 0025 Related**: Service registry (ADR 0373) is the foundation; needs systemd metadata.

| Aspect | Current | Missing | Why It Matters |
|--------|---------|---------|----------------|
| Registry existence | ✓ (inventory/group_vars/platform_services.yml) | None | Foundation exists |
| Service metadata schema | Basic (name, image, ports, internal_port) | Systemd fields: restart_policy, restart_sec, dependencies, health_timer | Cannot auto-generate systemd units |
| Systemd unit fields | None | `systemd_restart_policy`, `systemd_restart_sec`, `systemd_after`, `systemd_wants`, `systemd_on_failure` | Registry cannot inform unit generation |
| Health check metadata | Partial (in compose file templates) | Structured metadata: `health_test`, `health_interval`, `health_retries` | Cannot auto-generate health timer units |
| Role migration to registry | ~60% (roles using derived defaults) | Remaining 4 roles need to adopt registry pattern | Inconsistent schema usage |
| Documentation of registry | Basic (ADR 0373 text) | Usage guide, schema reference, extension examples | New services hard to add correctly |

**Current state**:
- ADR 0373 service registry exists and is partially adopted
- Registry lacks systemd metadata needed for Phase 2
- Some legacy roles still define their own paths instead of deriving them

**Impact**:
- Cannot auto-generate systemd units until registry is extended
- Registry improvements require coordination across multiple roles
- Schema changes may break existing role integrations

**Solution approach** (Phase 2):
1. Extend registry schema with systemd fields
2. Migrate all roles to use registry (complete the 40% gap)
3. Document registry schema and extension process

---

### Gap 6: Playbook Consolidation & Orchestration (Medium-High Priority)

**ADR 0025 Related**: Enables "repeatable and inspectable" platform-wide operations.

| Aspect | Current | Missing | Why It Matters |
|--------|---------|---------|----------------|
| Per-service convergence playbooks | ✓ (64 independent playbooks) | Unified convergence playbook respecting service dependency order | Operators run 64 separate `make converge-*` commands; error-prone |
| Service dependency declaration | Implicit (ADR 0373 has `requires_services` concept) | Explicit dependency graph in registry; playbook uses it | Service startup order undefined; race conditions |
| Health check after convergence | Per-role (inconsistent) | Unified health check playbook for all 64 services | No signal that convergence succeeded end-to-end |
| Rollback orchestration | None | Unified rollback playbook with rollback order (reverse of dependencies) | Failed deployments require manual intervention; risky |
| Boot-time service ordering | Implicit (systemd will handle once units exist) | Systemd `After=` and `Wants=` declarations capture dependency graph | Services may start out of order; race conditions |
| Monitoring integration | Ad hoc (per role) | Unified playbook output integrates with platform monitoring (Plane, OpenBao, etc.) | No signal of platform convergence state |

**Current state**:
- Each runtime role has its own convergence task
- `make converge-<service> env=production` runs per-service
- No unified "converge all runtimes" workflow
- Dependency ordering is implicit and fragile

**Impact**:
- Platform-wide deployment requires 64 manual steps
- Service startup order unpredictable; hidden race conditions
- No unified health check post-deployment
- Recovery from failed deployment is manual and error-prone

**Solution approach** (Phase 4):
1. Extend service registry with explicit dependency graph
2. Generate unified convergence/health-check/rollback playbooks
3. Integrate with Plane (ADR 0360) for task tracking
4. Document playbook orchestration contract

---

## Summary of Implementation Completeness

| Category | Complete | Partial | Missing | % Complete |
|----------|----------|---------|---------|-----------|
| Compose deployment | 64 | 4 | 0 | 94% |
| Health checks | 36 | 0 | 28 | 56% |
| Systemd integration | 0 | 0 | 64 | 0% |
| Operator runbooks | 26 | 38 | 0 | 40% |
| File location standardization | Enforced in registry | Manual adherence | No validation | 60% |
| Service registry integration | Deployed | Partial schema | Systemd metadata missing | 70% |
| Playbook consolidation | None | Per-role | Unified orchestration missing | 0% |

**Overall ADR 0025 completion**: ~52% (meets requirements 1, 2a, 2b, 4; gaps in 3, 5, and orchestration)

---

## Priority & Sequencing

**Critical** (block production readiness):
1. Systemd integration (Phase 1-2)
2. Health check completion + runbook integration (Phase 2-3)

**High** (needed for operability):
3. Operator runbook standardization (Phase 3)
4. Service registry systemd metadata (Phase 2)

**Medium** (quality & future-proofing):
5. File location validation (Phase 1)
6. Playbook consolidation (Phase 4)

---

## References

- ADR 0025: Compose-Managed Runtime Stacks
- ADR 0373: Service Registry and Derived Defaults
- ADR 0360: Plane as Agent Task HQ (for orchestration integration)
- Service registry: `inventory/group_vars/platform_services.yml`
- Runtime roles: `collections/ansible_collections/lv3/platform/roles/*_runtime/`
- Existing runbooks: `docs/runbooks/configure-*.md`
