# ADR 0387: Platform DRY Consolidation

- **Date**: 2026-04-09
- **Status**: Accepted
- **Deciders**: platform team
- **Concern**: platform, dry, maintainability
- **Tags**: ansible, dry, lifecycle, composition, topology

## Context

The platform has built strong DRY foundations over the past two weeks:

| Mechanism | ADR | Status |
|-----------|-----|--------|
| Service registry (`platform_services.yml`) | 0373 | Implemented — 73 services registered |
| Derived defaults (`derive_service_defaults`) | 0373 | Implemented — 100% adoption |
| Shared lifecycle tasks (`check_local_secrets`, `manage_service_secrets`, `docker_compose_converge`, `verify_service_health`) | 0370 | Tasks created, **partial role migration** |
| Parameterized verification (`verify_service_health`) | 0371 | Task created, **70 roles using it** |
| Playbook includes (`_includes/`) | 0372 | Includes created, **0 playbooks migrated** |
| Operator identity decoupling (`identity.yml`, `platform_domain`, `platform_topology_host`) | 0385 | Core variables extracted, **partial cleanup** |
| Compose template macros (`compose_macros.j2`) | 0368 | Macros created, **partial adoption** |

Despite this progress, **four measurable DRY gaps** remain:

### Gap 1: Hardcoded network IPs (13 roles, ~25 occurrences)

Roles directly embed `10.10.10.*` addresses in defaults files instead of using
the service topology variables that already exist (`platform_service_host`,
`platform_service_url`, `hostvars[host].ansible_host`).

| IP | Meaning | Roles affected |
|----|---------|---------------|
| `10.10.10.10` | nginx-edge | librechat, plane, ntopng |
| `10.10.10.20` | docker-runtime | api_gateway, librechat, litellm, sftpgo, repowise, plausible, plane_adr, serverclaw (main.yml) |
| `10.10.10.30` | docker-build | build_server |
| `10.10.10.40` | monitoring | main.yml (loki URL) |
| `10.10.10.92` | runtime-control | librechat |
| `10.10.10.1` | proxmox gateway | coolify, control_plane_recovery_firewall |
| `10.10.10.0/24` | platform subnet | ntopng, control_plane_recovery_firewall |

### Gap 2: Hostname literals in `hostvars[]` (4 files)

Four files still use `hostvars['docker-runtime']` or similar instead of
the `playbook_execution_host_patterns` map or `platform_topology_host`.

### Gap 3: `docker_compose_converge` underadoption (2 of ~40 eligible roles)

The shared convergence task handles image pull, Docker NAT chain recovery,
drift detection, and force-recreate. Only `directus_runtime` and
`label_studio_runtime` use it. The remaining ~38 Docker Compose roles
duplicate this logic independently.

### Gap 4: Playbook `_includes/` not used (0 of ~50 eligible playbooks)

The DNS, Postgres, Docker runtime, and NGINX edge includes exist in
`playbooks/_includes/` but no playbook has been migrated to import them.
Each playbook still carries 60-100 lines of duplicated boilerplate.

---

## Decision

This ADR serves as the **consolidation point** for DRY work. It elevates
ADRs 0370, 0371, 0372, and 0385 from Proposed to Accepted and defines
the remaining implementation work.

### Fix 1: Eliminate hardcoded network IPs

Replace literal IPs in role defaults with topology-derived variables.
The pattern depends on what the IP references:

**For service-to-service URLs** (most cases):
```yaml
# Before:
librechat_ollama_base_url: http://10.10.10.20:11434

# After — use the host's ansible_host from inventory:
librechat_ollama_base_url: "http://{{ hostvars[playbook_execution_host_patterns.docker_runtime[playbook_execution_env]].ansible_host }}:{{ ollama_host_port | default(11434) }}"
```

**For firewall rules** (control_plane_recovery, coolify):
```yaml
# Before:
control_plane_recovery_firewall_allowed_sources:
  - 10.10.10.1/32

# After — reference the Proxmox host IP from inventory:
control_plane_recovery_firewall_allowed_sources:
  - "{{ hostvars[platform_topology_host].ansible_host }}/32"
```

**For extra_hosts hairpin NAT** (librechat, serverclaw):
```yaml
# Before:
librechat_extra_hosts:
  - "sso.{{ platform_domain }}:10.10.10.10"

# After — use the nginx edge host's IP:
librechat_extra_hosts:
  - "sso.{{ platform_domain }}:{{ hostvars[playbook_execution_host_patterns.nginx_edge[playbook_execution_env]].ansible_host }}"
```

**Scope:** 13 roles + 3 entries in `inventory/group_vars/all/main.yml`.

### Fix 2: Eliminate remaining hostname literals

Replace the 4 remaining `hostvars['<hostname>']` references with
`playbook_execution_host_patterns` or `platform_topology_host`.

### Fix 3: Migrate `docker_compose_converge` (future, phased)

Migrate Docker Compose roles to use `common/tasks/docker_compose_converge.yml`
following the pattern established by `directus_runtime`:

**Phase A** (simplest, 5 roles): label_studio, langfuse, outline, grist, flagsmith
**Phase B** (medium, 8 roles): gitea, keycloak, mattermost, nextcloud, n8n, plausible, superset, windmill
**Phase C** (complex, 5 roles): dify, plane, api_gateway, openbao, mail_platform
**Phase D** (remaining): all other Docker Compose roles

Each phase: migrate roles → validate with `--check --diff` → commit.

### Fix 4: Migrate playbooks to use `_includes/` (future, phased)

Follow the plan in ADR 0372. Priority order:
1. Playbooks with all 4 standard plays (DNS + Postgres + Docker + NGINX): 8 playbooks
2. Playbooks with Docker + NGINX: 4 playbooks
3. Docker-only playbooks: 3 playbooks
4. Remaining custom compositions

---

## Implementation Order

| Step | Scope | Risk | Effort |
|------|-------|------|--------|
| **1. Fix hardcoded IPs** | 13 roles + main.yml | Low — variable indirection | 2-3 hours |
| **2. Fix hostname literals** | 4 files | Low — same pattern | 30 min |
| **3. Update ADR statuses** | 4 ADR files | None | 15 min |
| **4. Migrate docker_compose_converge** (Phase A) | 5 roles | Medium — behavior must match | 2-3 hours |
| **5. Migrate playbooks** (Phase 1) | 8 playbooks | Medium — test each | 3-4 hours |

Steps 1-3 are done in this ADR's implementation commit.
Steps 4-5 are planned as follow-up workstreams.

---

## What NOT to Do

- **Don't migrate all roles/playbooks at once.** Phased rollout with
  verification after each batch.
- **Don't change behavior.** Every fix is a pure indirection — the
  resolved values must be identical.
- **Don't remove role-specific `tasks/main.yml` files.** They remain as
  orchestration layers; shared includes handle only generic phases.
- **Don't abstract the provider layer.** The topology variables
  (`playbook_execution_host_patterns`) already handle staging vs production
  host selection — that's sufficient indirection.

---

## Success Criteria

After this ADR's immediate implementation (Steps 1-3):

- [ ] Zero `10.10.10.*` literals in role `defaults/main.yml` files
- [ ] Zero `hostvars['<literal-hostname>']` outside of inventory files
- [ ] ADRs 0370, 0371, 0372, 0385 status updated to Accepted
- [ ] All topology references use `playbook_execution_host_patterns` or
      `platform_topology_host`

After follow-up work (Steps 4-5):

- [ ] All Docker Compose roles use `docker_compose_converge`
- [ ] All standard playbooks use `_includes/` fragments
- [ ] New service onboarding requires ~50 lines of role-specific config
      (down from ~150-200)

---

## Consequences

**Positive:**
- Single change point for network topology — fork operators change
  `inventory/hosts.yml` and all roles pick up the new IPs automatically.
- Docker NAT chain recovery propagates to all services via
  `docker_compose_converge`, not just the 2 roles that currently have it.
- Playbook fixes (e.g., preflight check changes) edit 4 include files
  instead of 50 playbooks.
- Clear audit trail: `grep` for hardcoded values returns zero hits.

**Negative:**
- More indirection in defaults files — debugging requires following
  variable chains through `hostvars` and `playbook_execution_host_patterns`.
- Phased migration means the codebase has two patterns temporarily
  (direct includes vs boilerplate) until all roles are migrated.

---

## Related ADRs

- **ADR 0370** — Service Lifecycle Task Includes (Proposed → Accepted)
- **ADR 0371** — Parameterized Verify Tasks (Proposed → Accepted)
- **ADR 0372** — Data-Driven Playbook Composition (Proposed → Accepted)
- **ADR 0373** — Service Registry and Derived Defaults (Implemented)
- **ADR 0385** — Decouple Platform from Operator Identity (Proposed → Accepted)
