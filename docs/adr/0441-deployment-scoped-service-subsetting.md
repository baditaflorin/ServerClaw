# ADR 0441: Deployment-Scoped Service Subsetting via Service Profiles

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Not Started
- Date: 2026-04-27
- Concern: forkability, multi-tenancy, service-catalog, opt-in
- Tags: multi-deployment, service-profile, allowlist, registry, refactor
- Implements: ADR 0439 (Multi-Deployment Repo Architecture)
- Depends on:
  - ADR 0373 (Declarative service registry & `derive_service_defaults`)
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation)
- Relates to:
  - ADR 0359 (Declarative PostgreSQL client registry)
  - ADR 0416 (Topology-derived pg_hba)

---

## Context

Today the platform service catalog
(`inventory/group_vars/all/platform_services.yml`) is binary: a service
either has an entry (and runs) or doesn't (and is absent). There is no
mechanism to say "deployment A runs ten services, deployment B runs
fifteen, deployment C runs all twenty". The operator's stated goal:

> One server with 10 services, one with 15, one with 20 — pure IaC, give
> me three domains and the right things deploy automatically.

A deployment must be able to:

1. Pick a subset of the platform service catalog to enable.
2. Override per-service settings (image tag, resource limits, enabled
   integrations) without forking the role.
3. Disable a service that's listed in a profile tier, without removing
   the tier.
4. Express dependencies cleanly: enabling `outline` implies enabling
   `postgres`, `minio`, `keycloak` — not by forcing the operator to list
   them, but by inheriting the closure.

We also want sensible **profiles** so operators don't have to hand-craft
twenty allowlist entries. A profile is a named bundle (like an Ansible
import); deployments compose profiles plus per-service overrides.

---

## Decision

### `profile.yml` schema (per-deployment)

Each deployment owns a `profile.yml` under
`.local/deployments/<slug>/profile.yml`. Schema:

```yaml
# .local/deployments/<slug>/profile.yml
---
# Compose one or more named profiles. Resolved depth-first; later
# profiles override earlier ones. Profiles live in
# inventory/group_vars/all/service_profiles.yml (committed).
profiles:
  - core              # always required: postgres, openbao, keycloak, traefik/nginx, monitoring
  - identity          # adds gitea, harbor, oauth2-proxy
  - knowledge         # adds outline, langfuse, plane
  - observability     # adds grafana, prometheus, loki, alertmanager

# Explicit allowlist (after profile expansion). Listed services run.
# A service must appear in the union of the profile closures OR in
# `extra_services` to be enabled. This is intentionally restrictive —
# typo'd names fail loudly rather than silently disabling a service.
extra_services:
  - changedetection   # not in any profile, but this deployment wants it

# Hard disable list. Removes services that profile expansion would
# otherwise have enabled. Use sparingly.
disabled_services:
  - alertmanager      # this deployment doesn't run paging

# Per-service overrides, applied on top of the catalog defaults.
service_overrides:
  outline:
    container_image: "outlinewiki/outline:0.81.0"  # pin a version
    resource_limits:
      memory: 2G
  gitea:
    enable_actions: false                          # opt out of a feature
  postgres:
    shared_buffers: 1GB
```

### `inventory/group_vars/all/service_profiles.yml` (committed, generic)

Defines the profile names operators reference. Generic and shared across
all deployments.

```yaml
# inventory/group_vars/all/service_profiles.yml
---
service_profiles:
  core:
    description: |
      Minimum runnable platform: shared postgres, openbao, keycloak,
      edge proxy, basic monitoring. Required by every other profile.
    services:
      - postgres
      - openbao
      - keycloak
      - nginx_edge
      - prometheus
      - uptime_kuma

  identity:
    extends: [core]
    description: |
      Source-control + container registry + OAuth proxy.
    services:
      - gitea
      - harbor
      - oauth2_proxy

  knowledge:
    extends: [core, identity]
    description: |
      Knowledge management + observability for AI workflows.
    services:
      - outline
      - langfuse
      - plane
      - minio

  observability:
    extends: [core]
    description: |
      Full Grafana stack: dashboards, log aggregation, paging.
    services:
      - grafana
      - loki
      - alertmanager
      - tempo

  ai_lab:
    extends: [core, identity, knowledge]
    description: |
      Full AI development stack — Dify, LibreChat, embeddings, etc.
    services:
      - dify
      - librechat
      - litellm
      - qdrant
      - repowise
      # ... full ai service list
```

Profiles compose. Resolution algorithm (in `scripts/deployment.py`):

```
def resolve_enabled_services(deployment):
    enabled = set()
    for p in deployment.profile["profiles"]:
        enabled |= closure_of(p)        # follows `extends`
    enabled |= set(deployment.profile.get("extra_services", []))
    enabled -= set(deployment.profile.get("disabled_services", []))
    enabled |= implicit_dependencies(enabled)  # see below
    return enabled
```

### Implicit dependencies

Services declare hard dependencies in the catalog:

```yaml
# inventory/group_vars/all/platform_services.yml (existing file, new key)
platform_service_registry:
  outline:
    service_type: docker_app
    internal_port: 3000
    host_group: docker_runtime
    requires_services: [postgres, minio, keycloak]   # NEW
    needs_openbao: true
    # ...
  gitea:
    requires_services: [postgres, openbao]
    # ...
```

`implicit_dependencies(enabled)` walks the `requires_services` graph
until a fixed point is reached. If a service A requires B and B is in
`disabled_services`, the resolver fails fast with:

> Service `outline` requires `minio`, but `minio` is in
> `disabled_services` for deployment `acme`. Either enable `minio` or
> remove `outline` from the profile.

### Service-runtime gating

Every service playbook today starts with `roles: [<service>]`. We add a
single guard at the top of every service play:

```yaml
# playbooks/<service>.yml
- name: Converge <service>
  hosts: "{{ playbook_execution_host_patterns.<service>[playbook_execution_env] }}"
  vars:
    _enabled: "{{ '<service>' in platform_enabled_services }}"
  tasks:
    - name: Skip — <service> not enabled in deployment {{ platform_deployment_slug }}
      ansible.builtin.meta: end_play
      when: not _enabled
  roles:
    - <service>
```

`platform_enabled_services` is the resolved enabled set, computed by
`generate_platform_vars.py` and written into the per-deployment
`platform.yml`. Implementation note: this guard should be added by a
mechanical pass over all `playbooks/*.yml`, not hand-edited per service.

### Per-service overrides

`service_overrides` in `profile.yml` are merged onto the catalog defaults
inside `derive_service_defaults` (ADR 0373). The merge precedence,
lowest to highest:

1. Catalog default (`platform_service_registry[svc]`).
2. Profile-level override (none today; reserved for future profile-tier
   tuning).
3. Per-deployment `service_overrides[svc]`.

Overrides are deep-merged for dicts, replaced wholesale for lists and
scalars.

### Catalog vs profile vs override — division of authority

| Concern | Lives in | Authority |
|---------|----------|-----------|
| Service exists, what type it is, default port | Catalog (`platform_services.yml`) | Repo maintainers — generic |
| Service runs in this deployment | Profile + extras + disabled | Operator |
| Service tuning (image tag, resource caps) | `service_overrides` | Operator |
| Service-internal logic | Role | Repo maintainers |

This means a deployment's `profile.yml` is small (≤ 50 lines for a
typical 10-15 service deployment) and humanly auditable, while the
shared catalog stays comprehensive.

---

## Consequences

### Positive

- Operator gets the IaC story they asked for: three deployments, three
  short `profile.yml` files, no role edits.
- Profiles compose, so common bundles ("core", "ai_lab") don't get
  copy-pasted across deployments.
- Implicit dependencies prevent the foot-gun where a deployment lists
  Outline but forgets MinIO.
- `disabled_services` is the explicit dial for opting out of a profile
  member without forking the profile.
- `platform_enabled_services` is computed once and threaded into every
  play, so service gating is a single contract.

### Negative

- Every existing playbook gains a 4-line guard. ~60 playbooks. This is
  done by a one-time mechanical pass, but it is a large diff.
- Operators must learn the profile/override vocabulary. Mitigation:
  the existing prod deployment's profile is auto-generated by the
  migration in ADR 0440 from the live topology, so day-zero behaviour
  is unchanged.
- A service that exists in the catalog but in *no* profile is reachable
  only via `extra_services`. This is intentional but could surprise an
  operator who adds a new service entry expecting it to "just run".
  Mitigation: lint rule that warns on catalog entries not referenced
  by any profile.

### Neutral

- The catalog file (`platform_services.yml`) does not shrink — it gains
  a `requires_services` key per service but loses no existing fields.
- `derive_service_defaults` (ADR 0373) gains a deep-merge step for
  `service_overrides` but its public contract is unchanged.

---

## Migration plan

Implementation Phase 1:

1. Add `service_profiles.yml` with three baseline profiles: `core`,
   `identity`, `observability`. Hand-curated from current catalog
   knowledge.
2. Add `requires_services` to every existing `platform_service_registry`
   entry. (~73 services; one PR doing the whole sweep.)
3. Add resolver to `scripts/deployment.py`.
4. Add unit tests for resolver: profile composition, `disabled_services`
   conflict detection, dependency closure, override deep-merge.

Phase 2:

5. Mechanical pass adding the `_enabled` guard to every
   `playbooks/<service>.yml`.
6. Migration script (from ADR 0440) generates
   `.local/deployments/prod/profile.yml` from the currently-running
   service set. Verify converging prod with the new profile is a no-op.

Phase 3:

7. Author profiles for known fork archetypes: `ai_lab`, `knowledge`,
   `minimal_blog`. Driven by the 0fork deployment's needs.
8. Run a fresh converge against an empty `.local/deployments/test/` with
   a 10-service `profile.yml` to validate the small-deployment story.

### Rollback

Phase 1 changes are pure additions — revertible. Phase 2 (`_enabled`
guards) is reverted by removing the guard tasks; service runs
unconditionally as today.

---

## Open Questions

1. **Multi-tier profile overrides.** Should profiles themselves support
   `service_overrides`? E.g. the `ai_lab` profile pinning Outline to a
   specific version. *Tentative*: yes, but defer until a concrete need
   appears — for now, profiles list services only and per-deployment
   overrides handle pinning.

2. **Sensitivity of `requires_services` to environment.** Outline
   requires MinIO in production but in staging maybe an embedded MinIO
   suffices. *Tentative*: no — `requires_services` is a property of the
   service, not the environment. Variant tuning belongs in
   `service_overrides`.

3. **Profile inheritance loops.** The resolver must detect cycles
   (`profile A extends B extends A`). *Tentative*: yes, raise a
   `ProfileCycleError`. Trivial to implement during topo-sort.

4. **Discovery: which deployments use which services?** We want
   `make list-deployments-using svc=outline` for ops reasoning. The
   resolver makes this trivial — list every deployment whose
   resolved enabled set contains `outline`. Tracked as a follow-up
   tooling task.
