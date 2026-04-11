# Workstream ADR 0072: Staging And Production Environment Topology

- ADR: [ADR 0072](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0072-staging-and-production-environment-topology.md)
- Title: Canonical production and staging topology for shared-edge single-node operations
- Status: merged
- Branch: `codex/adr-0072-staging-production-topology`
- Worktree: `../proxmox-host_server-adr-0072-staging-production-topology`
- Owner: codex
- Depends On: `adr-0074-ops-portal`, `adr-0075-service-capability-catalog`
- Conflicts With: none
- Shared Surfaces: `config/service-capability-catalog.json`, `config/subdomain-catalog.json`, `config/environment-topology.json`, `scripts/generate_ops_portal.py`, `docs/runbooks/platform-operations-portal.md`

## Scope

- define the canonical staging and production topology contract in ADR 0072
- add repo-managed environment topology metadata and validation
- extend the service capability catalog with explicit environment bindings
- extend the subdomain catalog with the missing production SSO hostname and planned staging hostnames
- render an environment view in the generated operations portal
- document how future assistants should add staged services without reusing production state

## Non-Goals

- applying a live staging rollout on the platform
- provisioning separate staging VMs or a second Proxmox node
- introducing environment-specific secrets or database automation for every service in one step

## Expected Repo Surfaces

- `docs/adr/0072-staging-and-production-environment-topology.md`
- `docs/workstreams/adr-0072-staging-production-topology.md`
- `docs/runbooks/staging-and-production-topology.md`
- `config/environment-topology.json`
- `docs/schema/environment-topology.schema.json`
- `scripts/environment_topology.py`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `scripts/service_catalog.py`
- `scripts/subdomain_catalog.py`
- `scripts/generate_ops_portal.py`
- `workstreams.yaml`

## Expected Live Surfaces

- none yet; this workstream defines and validates repo truth only

## Verification

- `uvx --from pyyaml python scripts/environment_topology.py --validate`
- `uvx --from pyyaml python scripts/service_catalog.py --validate`
- `uvx --from pyyaml python scripts/subdomain_catalog.py --validate`
- `uvx --from pyyaml python scripts/generate_ops_portal.py --check`
- `./scripts/validate_repo.sh data-models generated-portals generated-docs`

## Merge Criteria

- `production` and `staging` are both represented in committed canonical data
- every service has an explicit production environment binding
- every planned staging hostname validates against the service and environment catalogs
- the generated portal includes an environment topology view without hand-maintained content

## Repo Implementation Notes

- Repo implementation completed on `2026-03-23` for release `0.75.0`.
- No live platform change is claimed in this workstream; staging remains a repo-modeled topology until later service rollouts publish staged surfaces from `main`.
