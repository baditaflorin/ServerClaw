# ADR 0439: Deployment Profiles — Subset-of-Services Selection for Forks

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Not Started
- Date: 2026-04-27
- Concern: forkability, operator-onboarding, scope-control, iac-end-to-end
- Tags: profiles, fork-clone, subset-selection, ansible-native, adr-0410-complement, adr-0438-prerequisite
- Relates to / extends:
  - ADR 0223 (HA automation profiles) — defines *topology-pattern* profiles
    (stateless edge, control-plane standby). This ADR introduces a separate
    axis: *which services exist in this deployment at all*.
  - ADR 0410 (Docker isolation testing) — defines `micro / minimal /
    standard / extended` profiles for the **test loop**. This ADR lifts the
    profile idea into **production deploys**.
  - ADR 0407 (generic-by-default `.local/` overlay) — substrate.
  - ADR 0424 (example.org clone) — first fork; took the full 73-service stack
    because no smaller shape was defined.
  - ADR 0431 (0fork full-day deployment) — single-command entry point;
    profiles slot in here as the selector.
  - ADR 0438 (generic-by-construction) — content-correctness layer; this
    ADR is the **scope-selection** layer above it.

---

## Context

The platform has ~73 services. A new fork (ADR 0424) inherits all of them
by default — there is no first-class way to say "I only want Coolify +
SSO" or "I only want the AI stack." Operators either run everything
(wasteful: ~17 VMs, 64+ GB RAM), hand-edit `playbooks/site.yml` (drifts
from upstream), or comment out roles in their fork (one-way door).

The platform already speaks two non-deployment dialects of "profile":

- **HA pattern profiles** (ADR 0223): how a service is structured for HA.
- **Test profiles** (ADR 0410): which subset boots in Docker for fast feedback.

What is missing is a **deployment profile**: a named subset of the service
catalog that a fork selects at bootstrap time and the platform honors
end-to-end (playbooks, manifest, DNS, edge, monitoring scrape targets).

### Worked example — what an operator wants to say

> "I want a fork that runs Coolify behind public SSO. Nothing else."

Today this requires manual surgery. Under this ADR it becomes:

```bash
ansible-playbook playbooks/profiles/coolify-public-sso.yml
# or via the existing wrapper:
make site profile=coolify-public-sso
```

…which deploys exactly 5 VMs and 9 roles (see Appendix A).

---

## Decision

**Reuse Ansible's existing primitives. Do not invent a new DSL.**

The platform already composes the full deploy via `import_playbook` in
[playbooks/site.yml](../../playbooks/site.yml), which chains group
meta-playbooks under [playbooks/groups/](../../playbooks/groups/) (access,
data, security, observability, automation, communication, platform-apps).
A deployment profile is **another tier of meta-playbook** in the same
shape. No new file format, no new selector engine, no new concept for LLMs
or new operators to learn.

### What we add

1. **`playbooks/profiles/`** — directory of profile meta-playbooks. Each is
   a thin `import_playbook` composition (10–30 lines).
2. **`make site profile=<name>`** — Make target that maps to
   `ansible-playbook playbooks/profiles/<name>.yml`. Defaults to `full`
   (today's `site.yml`) — existing deployments unchanged.
3. **Profile validation in CI** — for each profile under
   `playbooks/profiles/`, run `ansible-playbook --syntax-check` and a
   resolved-host check. This is built on `ansible-playbook` flags that
   already exist; the only new code is a Make target that loops profiles.
4. **One narrative doc** — `docs/runbooks/select-deployment-profile.md`
   listing the catalogued profiles, their resolved VMs, and estimated RAM.

### What we explicitly do **not** add

- ❌ A `profiles/catalog.yaml` DSL. Ansible playbooks already are the DSL.
- ❌ A new selector field in `.local/identity.yml`. The selector is the
  filename you pass to `ansible-playbook`.
- ❌ A new `make profile-shape` introspection tool. `ansible-playbook
  --list-tasks --list-hosts` already does this.
- ❌ A custom Python resolver. Ansible's `import_playbook` is the resolver.

### Why this beats a custom DSL

| Concern | Custom DSL (`profiles/catalog.yaml`) | Ansible-native (`playbooks/profiles/*.yml`) |
|---|---|---|
| Familiarity | New concept, must teach LLMs and operators | Same `import_playbook` pattern as `site.yml` |
| Validation | Must build a custom validator | `ansible-playbook --syntax-check` |
| Composition | Hand-written resolver | Native `import_playbook` chains |
| Drift risk | DSL falls behind playbook reality | Profile *is* a playbook — no drift possible |
| Discoverability | Read a YAML, then map it back to playbooks | `ls playbooks/profiles/` |

### How this composes with the existing deployment

`playbooks/site.yml` becomes the canonical "full" profile. New profiles
live alongside it:

```
playbooks/
  site.yml                          # = profile "full" (unchanged)
  profiles/
    base.yml                        # identity foundation
    coolify-public-sso.yml          # extends base + Coolify
    observability.yml               # extends base + monitoring stack
    ai-stack.yml                    # extends base + LLM stack
    dev-ci.yml                      # extends base + Gitea/Woodpecker/Harbor
    collab.yml                      # extends base + Outline/Plane/Mattermost
```

Each profile is `import_playbook` of `playbooks/profiles/base.yml` plus
its incremental playbooks. No magic.

---

## Initial profile catalog

| Profile | Pulls in | VMs | Use case |
|---|---|---|---|
| `base` | nginx, keycloak, openbao, postgres, step_ca | 4 | Identity foundation; other profiles import this |
| `coolify-public-sso` | base + Coolify | 5 | Single-tenant PaaS with SSO (worked example) |
| `observability` | base + Prometheus, Loki, Tempo, Grafana, Alertmanager | 5 | Monitoring-only fork |
| `ai-stack` | base + Ollama, Dify, LiteLLM, LibreChat, Langfuse, rag_context | 6–7 | LLM platform fork |
| `dev-ci` | base + Gitea, Woodpecker, Harbor, Renovate | 5 | Source-and-CI fork |
| `collab` | base + Outline, Plane, Mattermost | 5 | Knowledge/collab fork |
| `full` | All ~73 services (today's `site.yml`) | 17 | Default; preserved |

The split mirrors the candidate buckets in
[`docs/diagrams/service-interaction-map.md`](../diagrams/service-interaction-map.md).

---

## Appendix A — Worked example: `coolify-public-sso`

```yaml
# playbooks/profiles/base.yml
---
# Identity foundation — every other profile imports this.
- import_playbook: ../proxmox-install.yml
- import_playbook: ../groups/data.yml          # postgres
- import_playbook: ../groups/security.yml      # keycloak, openbao, step-ca
- import_playbook: ../nginx.yml                # edge + oauth2-proxy
```

```yaml
# playbooks/profiles/coolify-public-sso.yml
---
# Coolify PaaS behind Keycloak public SSO.
- import_playbook: base.yml
- import_playbook: ../coolify.yml              # coolify + coolify-apps + edge publication
```

That is the entire profile definition — two files, no new tooling.

**Operator runs:**

```bash
make site profile=coolify-public-sso
# expands to:
# ansible-playbook playbooks/profiles/coolify-public-sso.yml
```

**Inspection (using existing Ansible flags, no custom tool):**

```bash
ansible-playbook playbooks/profiles/coolify-public-sso.yml \
  --list-hosts --list-tasks
```

**Resolved fork shape:**
```
VMs:    proxmox-host, nginx, runtime-control, postgres, coolify, coolify-apps
Roles:  9 (linux_guest_firewall, docker_runtime, nginx_runtime,
        public_edge_oidc_auth, nginx_edge_publication, keycloak,
        openbao, postgres, coolify_runtime)
Excluded: 67 services from full catalog
Estimated RAM: ~24 GB (vs 64+ GB for full)
```

This is the smallest shape that satisfies "Coolify + public SSO" — Coolify
ships its own Postgres / Redis / Traefik internally, so the platform
shared data plane is not pulled in.

---

## Consequences

**Positive**
- Forks become honest about scope: a "coolify fork" actually deploys 5
  VMs, not 17.
- Zero new concepts. Anyone who can read `site.yml` can read a profile.
- LLMs already trained on Ansible understand `import_playbook` — no
  custom-DSL prompt context required.
- Validation is `ansible-playbook --syntax-check` (already a CI step).
- New services don't auto-inflate every fork — they must be added to a
  profile's `import_playbook` chain.

**Negative / Trade-offs**
- Catalog maintenance: every new service needs a decision on which
  profile(s) include it.
- Cross-profile testing: CI must converge each named profile in the
  Docker test matrix (ADR 0410), otherwise profiles silently rot.
- Implicit deps: services that quietly assume `langfuse` or `prometheus`
  exist will break when those are excluded — this ADR forces those
  implicit deps to surface as missing-host errors at converge time.

---

## Boundaries

- This ADR does **not** redesign service interactions; it only
  introduces a selection mechanism over the existing playbook catalog.
- It does **not** replace ADR 0223 (HA pattern profiles) or ADR 0410
  (test profiles) — different axes.
- Profiles are **deploy-time** selection. Runtime feature flags
  (Flagsmith) are out of scope.
- A profile is **append-only** within a fork's lifetime. Switching
  profiles on a live deployment (e.g. `coolify-public-sso → full`) is
  out of scope; it requires the same migration discipline as adding any
  new service.

---

## Related ADRs

- ADR 0223: Canonical HA topology catalog and reusable automation profiles
- ADR 0407: Generic-by-default `.local/` overlay
- ADR 0410: Docker isolation testing and IoC completion
- ADR 0424: example.org clone on Hetzner AX41-NVMe
- ADR 0431: 0fork full-day deployment — single-command IaC entry point
- ADR 0438: Generic-by-construction — generative cascade IaC
