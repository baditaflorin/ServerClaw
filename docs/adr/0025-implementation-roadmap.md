# ADR 0025 Implementation Roadmap: Compose-Managed Runtime Stacks

**Status**: Deep Dive & Roadmap
**Created**: 2026-04-06
**Roadmap Scope**: WS-0403 Analysis Phase
**Target Completion**: 4 phases over next 6-8 weeks

---

## Executive Summary

ADR 0025 declared the principle that runtime services on `docker-runtime-lv3` must be **compose-managed, declarative, and systemd-integrated**. Today, **64 of 68 runtime roles** (94%) have Docker Compose templates and deploy via `docker compose up`, but the integration is **incomplete**:

- **Compose deployment**: 94% implemented (64 roles)
- **Health checks**: 56% implemented (36 of 64 roles with healthcheck directives)
- **Systemd integration**: 0% implemented (no systemd units exist)
- **Operator runbooks**: ~40% coverage (some service-specific docs exist; none follow a standard pattern)
- **File location standardization**: Partially done via ADR 0373 (service registry); paths still inconsistent at `/opt/` and `/srv/`

This roadmap identifies the critical gaps and phases required to complete the ADR 0025 contract, leveraging ADR 0373 (service registry) as the foundation.

---

## Current State: What Works

### 1. Compose File Deployment (94% Complete)

**Status**: 64 of 68 runtime roles define docker-compose.yml.j2 templates.

**What's implemented**:
- All role defaults derive `compose_file` from the service registry (ADR 0373)
- Compose templates use Jinja2 to inject role-specific config (images, ports, env files, volumes)
- Each stack specifies explicit environment files and bind mounts
- Convergence task pulls images and runs `docker compose up -d` on change

**Example** (grist_runtime):
```
grist_compose_file: "{{ grist_site_dir }}/docker-compose.yml"
# Template: roles/grist_runtime/templates/docker-compose.yml.j2
# Deployment: ansible.builtin.command "docker compose -f {{ grist_compose_file }} up -d"
```

**Reference implementations**:
- `directus_runtime`, `grist_runtime`, `api_gateway_runtime` (representative of pattern)
- Compose projects live in `/opt/<service>/` or `/srv/<service>/` depending on role

### 2. Health Checks (56% Complete)

**Status**: 36 of 64 roles with compose files include `healthcheck` directives in templates.

**What's implemented**:
- Service-specific HTTP endpoints (e.g., Grist: `GET /status`, Open WebUI: `GET /health`)
- Standard compose healthcheck schema with interval/timeout/retries
- Some roles (neko_runtime, windmill_runtime, step_ca_runtime) have extensive health definitions across multiple services

**Example** (grist_runtime):
```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -f http://127.0.0.1:8484/status || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 24
```

**Gap**: 28 roles (44%) lack healthchecks, creating blind spots for operator visibility.

### 3. Directory Structure Conventions (Partially Standardized)

**Status**: ADR 0373 unifies path conventions; roles follow them inconsistently.

**Current convention** (via ADR 0373 service registry):
```yaml
<service>_site_dir: /opt/<service>  # or /srv/<service> for newer deployments
<service>_compose_file: "{{ <service>_site_dir }}/docker-compose.yml"
<service>_env_file: "{{ compose_runtime_secret_root }}/<service>/runtime.env"
<service>_secret_dir: /etc/lv3/<service>
```

**Issue**: Mixed `/opt/` and `/srv/` usage; ADR 0025 recommends versioned `/srv/` paths but enforcement is absent.

### 4. Convergence Logic (Implemented; Ad Hoc Cleanup)

**Status**: Roles handle convergence but lack standardized start/stop/rollback procedures.

**What's implemented**:
- `docker compose pull` before deployment
- `docker compose up -d` on config change
- Some roles check iptables, networking, or prerequisite services
- No standardized cleanup, restart, or health verification sequence

**Gap**: Operators manually run `docker compose restart`, `docker compose ps`, `docker compose logs` — no lifecycle automation.

---

## Critical Gaps: What's Missing

### Gap 1: Systemd Service Units (0% Implemented)

**Why It Matters**: ADR 0025 requirement 3 — "Stack lifecycle is host-managed, not shell-session-managed."

**Current problem**:
- Services run via `docker compose up -d` but are invisible to systemd
- Boot recovery relies on compose `restart: unless-stopped` (fragile)
- Operators cannot use `systemctl start|stop|restart <service>` workflows
- No integration with standard Linux monitoring/alerting (e.g., systemd timers for health checks)
- Rollback and failure recovery are manual operator procedures

**Impact**: Without systemd units, the platform cannot:
- Guarantee service start order and dependencies across the host
- Implement unified service lifecycle (boot, restart, failure) policies
- Generate service state from `systemctl status`
- Export standard health signals to monitoring (systemd `OnFailure=`, `RestartSec=`)

**Effort to close**: **High** — requires designing and templating systemd service/timer units for all 64 stacks, testing boot scenarios.

### Gap 2: Operator Runbooks (40% Complete, No Standard Template)

**Why It Matters**: ADR 0025 requirement 5 — "Each stack must have an operator runbook."

**Current state**:
- ~40% of services have ad hoc runbooks under `docs/runbooks/` (e.g., configure-grist.md, configure-portainer.md)
- No standard runbook structure; content is inconsistent
- Many runbooks document configuration only; few cover lifecycle (start, stop, rollback, health verification)
- No automation to regenerate runbooks from templates

**Example missing coverage**:
- How to restart `plane_runtime` if health checks fail?
- Where are persistent data for `langfuse_runtime`?
- Rollback procedure for `openbao_runtime` (breaking change in secrets)?

**Impact**: Operators rely on Docker CLI knowledge and ad hoc shell history; no discoverable, standardized procedures.

**Effort to close**: **Medium** — create runbook template, bootstrap content from role metadata, iterate.

### Gap 3: File Location Standardization Enforcement (No Validation)

**Why It Matters**: ADR 0025 requirement 2 — "Each stack gets a predictable host layout."

**Current problem**:
- ADR 0373 declares the convention, but no enforcement mechanism
- New roles might hardcode `/opt/<service>` instead of using derived variables
- No linting or pre-push validation that roles conform to the convention

**Impact**: Future roles may deviate; operators cannot predict where data lives; migration/refactoring become fragile.

**Effort to close**: **Low** — add pre-commit hook to validate all roles use ADR 0373 derived variables for path definitions.

### Gap 4: Service Registry Integration (Partial)

**Why It Matters**: ADR 0373 is the foundation for unifying service metadata; ADR 0025 depends on it.

**Current state**:
- Registry exists in `inventory/group_vars/platform_services.yml` (ADR 0373)
- Not all roles have migrated to use derived defaults; some still define their own (legacy)
- Service registry does not yet capture systemd metadata (wanted units, restart policy, OnFailure hooks)

**Impact**: Cannot auto-generate systemd units or runbooks without extended registry schema.

**Effort to close**: **Medium** — extend registry schema, migrate remaining roles.

### Gap 5: Playbook Consolidation Opportunities

**Why It Matters**: ADR 0025 goal — repeatable and inspectable deployments, not shell-session-dependent.

**Current problem**:
- Each role's playbook is independent; no unified convergence orchestration
- No standard way to run all 64 stacks through a health check sequence
- Rollback requires custom per-service procedures

**Impact**: Platform-wide restart or recovery workflows are manual; no declarative ordering of service dependencies.

**Effort to close**: **Medium-High** — design playbook consolidation pattern (e.g., "converge-all-runtimes.yml" with dependency graph).

---

## Implementation Roadmap: 4 Phases

### Phase 1: Systemd Service Template Design (Weeks 1-2)

**Objective**: Design and test systemd service/timer templates for compose stacks; establish unit naming convention.

**Deliverables**:
1. **Systemd template design**:
   - `lv3-<service>.service` — standard service unit that runs `docker compose up`
   - `lv3-<service>-health.timer` — periodic health verification (optional)
   - `lv3-<service>.target` — ordering/grouping target for boot dependencies
   - Use `ExecStart=`, `ExecStop=`, `ExecReload=` to wrap compose commands
   - Set `Restart=on-failure`, `RestartSec=5`, `Type=simple` for stability

2. **Documentation**:
   - ADR amendment: Service unit requirements (naming, restart policy, dependency declaration)
   - Systemd template reference (parameter expansion, variable injection via EnvironmentFile)

3. **Reference implementation**: Design template for `directus_runtime` and `grist_runtime`; test boot and restart scenarios.

**Acceptance criteria**:
- Systemd units boot stacks on host restart
- `systemctl restart lv3-grist` restarts the compose stack
- Health check timer (if defined) integrates with monitoring

**Effort**: 40-50 hours

---

### Phase 2: Service Registry Extension & Systemd Unit Generation (Weeks 2-4)

**Objective**: Extend ADR 0373 service registry to capture systemd metadata; auto-generate units from registry.

**Deliverables**:
1. **Service registry schema extension**:
   - Add `systemd_restart_policy`, `systemd_restart_sec`, `systemd_dependencies` to each service entry
   - Add `health_check_timer` (interval, timeout) for services with active health monitoring

2. **Template-based unit generation**:
   - Create `templates/systemd_service.j2` and `templates/systemd_timer.j2` in a new common role (or existing `common` role)
   - Ansible playbook to generate units from registry + service-specific overrides
   - Script to validate generated units before deployment

3. **Integration with existing roles**:
   - Add task to each runtime role (via `include_role`) to copy systemd units to `/etc/systemd/system/`
   - Call `systemctl daemon-reload` and `systemctl enable lv3-<service>.service` on deployment

**Acceptance criteria**:
- Systemd units are generated from registry, not manually created
- All 64 runtime roles copy units to systemd
- `systemctl status lv3-<service>` works for all services

**Effort**: 60-80 hours

---

### Phase 3: Operator Runbook Generation Automation (Weeks 4-5)

**Objective**: Design runbook template and auto-generate runbooks from service registry + role metadata.

**Deliverables**:
1. **Runbook template** (`docs/runbooks/_templates/service-lifecycle-template.md`):
   - Sections: Deployment, Configuration, Health Verification, Restart, Rollback, Data Persistence, Logs
   - Service-specific content injected from registry + role variables
   - Example: `DEPLOYMENT_CMD="docker compose -f {{ service_compose_file }} up -d"`

2. **Auto-generation script**:
   - Python script that reads service registry and role metadata
   - Generates `docs/runbooks/operate-<service>.md` for each service
   - Manual override mechanism for special cases (e.g., role-specific procedures)

3. **Content bootstrap**:
   - Iterate on ~5 reference services; finalize template structure
   - Generate full set of runbooks; review for accuracy

**Acceptance criteria**:
- All 64 services have runbooks following standard structure
- Runbooks contain correct paths, commands, and service topology
- Operators can discover and follow procedures without shell knowledge

**Effort**: 50-70 hours

---

### Phase 4: Ansible Playbook Consolidation (Weeks 5-6)

**Objective**: Consolidate runtime convergence into unified playbooks with dependency ordering.

**Deliverables**:
1. **Dependency graph**:
   - Map service dependencies (e.g., Keycloak before Grist, Postgres before Mattermost)
   - Extend service registry with `requires_services: [...]` field

2. **Unified convergence playbooks**:
   - `playbooks/converge-all-runtimes.yml` — converge all services respecting dependency order
   - `playbooks/health-check-all-runtimes.yml` — verify all services post-deployment
   - `playbooks/restart-failed-runtimes.yml` — restart services marked unhealthy

3. **Integration with Plane (ADR 0360)**:
   - Map playbook runs to Plane task lifecycle (start, in-progress, completed)
   - Capture execution logs and health state per run

**Acceptance criteria**:
- Unified playbooks run all services in correct order
- Health checks pass for all services post-convergence
- Operators can use a single command to converge/check/restart all runtimes

**Effort**: 40-50 hours

---

## Gap Analysis Summary Table

| Gap | Current State | Impact | Phase | Effort | Dependencies |
|-----|---------------|--------|-------|--------|--------------|
| Systemd Integration | 0% (no units exist) | Services not host-managed; boot recovery fragile | 1-2 | High | None |
| Runbook Standardization | 40% (inconsistent docs) | Operators lack discoverable procedures | 3 | Medium | Phases 1-2 (systemd context) |
| File Location Validation | No enforcement | Future roles may deviate; unpredictable layout | 4 | Low | ADR 0373 (completed) |
| Service Registry (Systemd Metadata) | Partial (ADR 0373 exists, no systemd schema) | Cannot auto-generate units | 2 | Medium | Phase 1 (template design) |
| Playbook Consolidation | Manual per-service | No unified recovery/restart workflows | 4 | Medium-High | Phases 1-3 |

---

## Success Metrics

### Phase 1 (Systemd Design)
- Systemd templates boot stacks correctly on host restart
- Reference implementations (grist, directus) pass systemd lifecycle tests

### Phase 2 (Registry Extension & Generation)
- 100% of runtime roles deploy systemd units
- Units are generated from registry, not hardcoded
- `systemctl status lv3-*` works for all 64 services

### Phase 3 (Runbook Automation)
- All 64 services have discoverable, standard-format runbooks
- Runbooks contain correct deployment commands and data locations
- Operator time to follow a procedure drops by 50% (estimated, vs. manual shell work)

### Phase 4 (Playbook Consolidation)
- Unified convergence playbooks respect service dependency order
- Health checks pass for 100% of services post-convergence
- Platform-wide restart/recovery runs end-to-end via single command

---

## Risk & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| Systemd units conflict with existing docker processes | Medium | Services fail to start | Phase 1 must validate against running platform; test on staging VM first |
| Service registry schema breaks existing roles | Medium | Convergence fails | Backward compatibility layer; existing roles use fallback defaults |
| Runbook automation generates incorrect commands | High | Operators follow wrong procedures | Manual review of bootstrap runbooks; iterative refinement |
| Playbook dependency graph is incomplete | Medium | Services start out of order | Build graph incrementally; validate against actual startup logs |

---

## Timeline

- **Week 1**: Phase 1 design, reference implementation (directus, grist)
- **Week 2**: Phase 1 complete; Phase 2 registry schema design
- **Weeks 3-4**: Phase 2 systemd generation & integration
- **Week 5**: Phase 3 runbook template & auto-generation
- **Week 6**: Phase 4 playbook consolidation
- **Week 6-8**: Testing, refinement, documentation

**Total Effort**: 240-300 hours (3-4 week sprints for a focused team)

---

## Next Steps

1. **Immediate (WS-0403)**: Approve this roadmap and gap analysis
2. **Phase 1 kickoff**: Schedule systemd template design session with infrastructure team
3. **Parallel tracks**: Begin Phase 2 registry schema design while Phase 1 develops templates
4. **Review gates**: Validate each phase deliverable against ADR 0025 contract before proceeding

---

## References

- ADR 0025: Compose-Managed Runtime Stacks
- ADR 0373: Service Registry and Derived Defaults
- ADR 0360: Plane as Agent Task HQ (integration point for playbook automation)
- Runbook template: `docs/runbooks/_templates/` (to be created)
- Service registry: `inventory/group_vars/platform_services.yml`
