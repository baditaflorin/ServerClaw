# ADR 0402: Remove JupyterHub from the Platform

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.95
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-10
- Date: 2026-04-10
- Concern: Service Lifecycle, Platform Simplification
- Depends on: ADR 0291 (JupyterHub as Interactive Notebook Environment), ADR 0389 (Service Decommissioning Procedure), ADR 0396 (Deterministic Service Decommissioning)
- Tags: lifecycle, decommissioning, jupyterhub, notebooks, removal

---

## Context

JupyterHub was introduced in ADR 0291 as the interactive notebook environment for
the platform (notebooks.lv3.org, port 8097). It provided multi-user Jupyter
notebook access with OIDC authentication via Keycloak.

### Reasons for removal

1. **Usage**: The service has no active users. The notebooks.lv3.org URL has not
   been used since its initial setup. There is no notebook workflow that depends
   on it.

2. **Maintenance overhead**: JupyterHub ships a full Python + Node.js stack with a
   large dependency surface. Keeping its container image pinned and updated
   carries ongoing CVE exposure with no corresponding value delivered.

3. **Resource reclamation**: Port 8097 is freed for future services. The JupyterHub
   Docker compose network, volume, and container resources are released from the
   docker-runtime-lv3 host.

4. **Keycloak client cleanup**: Removing the `jupyterhub` Keycloak OIDC client
   reduces the surface of the realm's client roster and eliminates a stale
   service account credential that would never be rotated.

5. **Platform consolidation**: The platform's interactive data work now flows
   through Grist (tabular/formula-based) and Superset (BI dashboards). No gap
   remains that JupyterHub uniquely filled.

---

## Decision

Remove JupyterHub from the platform entirely:

- Deprecate ADR 0291
- Delete the `jupyterhub_runtime` Ansible role
- Delete `playbooks/jupyterhub.yml`, `playbooks/services/jupyterhub.yml`,
  `collections/.../playbooks/jupyterhub.yml`
- Remove all catalog entries (service-capability-catalog, slo-catalog, data-catalog,
  api-gateway-catalog, health-probe-catalog, workflow-catalog, dependency-graph,
  service-completeness, service-redundancy-catalog, subdomain-exposure-registry,
  service-partitions catalog)
- Remove the `jupyterhub` Keycloak OIDC client from `keycloak_runtime/tasks/main.yml`
  and its defaults from `keycloak_runtime/defaults/main.yml`
- Remove the `jupyterhub:` block from `inventory/group_vars/all/platform_services.yml`
- Remove the `jupyterhub_port: 8097` assignment from `inventory/host_vars/proxmox_florin.yml`
- Remove JupyterHub bookmark from `config/workbench-information-architecture.json`
- Remove JupyterHub monitor from `config/uptime-kuma/monitors.json`
- Remove all test assertions referencing JupyterHub service topology,
  Keycloak client defaults, and workflow catalog entries
- Regenerate all derived artifacts (platform manifest, discovery artifacts,
  SLO config, workstreams registry)

---

## Consequences

### Positive

- Cleaner service catalog: one fewer idle service with zero active users
- Keycloak realm client count reduced by one
- Port 8097 available for future allocation
- Reduced maintenance burden: no JupyterHub image pins to track
- Smaller test surface: JupyterHub-specific test assertions removed

### Negative / Accepted Risk

- Any future notebook use case requires re-implementation from scratch
  (no partial state to resume from, since the role is deleted)
- The decommission surfaced several gaps in the ADR 0396 automation tooling
  (documented in the companion postmortem); these are tracked as improvements
  but do not block this removal

### Neutral

- ADR 0291 marked Deprecated — its context and rationale are preserved for
  historical reference
- Port 8097 collision check removed from `test_redpanda_playbook.py`
  (the constraint no longer exists, so the assertion had no value)
