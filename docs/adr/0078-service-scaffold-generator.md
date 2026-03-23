# ADR 0078: Service Scaffold Generator

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.94.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

Adding a new service to the platform had become a multi-file manual process:

1. write the ADR and workstream documents
2. create the collection-backed runtime role and playbook entry points
3. register the service across topology, health, service, subdomain, image, and secret catalogs
4. remember the controller-local secret manifest and the operator runbook

The result was drift. New services were often missing one or more contracts, and the current mainline validators only caught some of those omissions after the fact.

The repository also changed shape after the original ADR draft:

- roles now live under `collections/ansible_collections/lv3/platform/roles/`
- `config/service-capability-catalog.json`, `config/subdomain-catalog.json`, and `config/health-probe-catalog.json` already enforce stronger cross-references
- `inventory/host_vars/proxmox_florin.yml.lv3_service_topology` is part of the canonical service contract
- controller-local secret storage and image scan receipts are explicit catalog surfaces

So the scaffold generator has to target the current collection layout and those stricter data models, not the older root-role layout.

## Decision

We will implement `make scaffold-service` as the canonical repo-local generator for new service skeletons.

### Invocation

```bash
make scaffold-service \
  NAME=my-service \
  DESCRIPTION="One-line description" \
  CATEGORY=automation \
  VM=docker-runtime-lv3 \
  PORT=8080 \
  SUBDOMAIN=my-service.lv3.org \
  EXPOSURE=private-only \
  IMAGE=docker.io/vendor/image:latest
```

Only `NAME` is strictly required. The target derives defaults for the other inputs so the CLI wrapper from ADR 0090 can keep using it with just a service name.

### Generated artifacts

The current implementation writes all of the repo surfaces required for a service scaffold on main:

- `docs/adr/<next>-<name>.md`
- `docs/workstreams/adr-<next>-<name>.md`
- `docs/runbooks/configure-<name>.md`
- `collections/ansible_collections/lv3/platform/roles/<name>_runtime/`
- `playbooks/<name>.yml`
- `playbooks/services/<name>.yml`
- `inventory/host_vars/proxmox_florin.yml` service-topology entry
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json` when a scaffolded hostname is declared
- `config/health-probe-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/image-catalog.json`
- placeholder image scan receipt under `receipts/image-scans/`
- `workstreams.yaml`

The runtime role scaffold is rendered from collection-backed template assets under `collections/ansible_collections/lv3/platform/roles/_template/service_scaffold/`.

### Scaffold defaults

The generator intentionally writes a *planned* service contract:

- `service-capability-catalog` entries default to `lifecycle_status: planned`
- health probes are scaffolded immediately so the probe contract exists early
- Uptime Kuma monitoring is disabled by default with a scaffold placeholder reason
- image entries use a placeholder digest-pinned ref and receipt skeleton
- controller-local secret and secret-catalog entries are created together

This keeps the new service internally consistent while still making the unfinished parts explicit.

### Validation guard

`scripts/validate_repository_data_models.py` now fails when any scaffolded catalog or topology value still contains a `TODO` placeholder marker.

That gives the desired workflow:

1. `make scaffold-service` succeeds and writes a complete skeleton
2. generated playbooks and role structure are syntactically valid
3. `make validate-data-models` fails until the operator replaces the scaffold placeholders

### Image pin helper

The scaffold checklist points at `make pin-image IMAGE=<registry/repository:tag>`, which resolves the remote digest and prints a digest-pinned image reference for catalog completion.

## Consequences

- Service onboarding is now collection-native and aligned with the current catalog schemas.
- Planned services can declare probe contracts before live rollout, which required relaxing the old service-catalog assumption that only active services could participate in the health-probe set.
- The repository has an explicit completion boundary: scaffold placeholders are allowed only immediately after generation and are blocked by validation before merge.
- The generator itself is now a maintained contract surface. When service catalogs, topology, or runtime-role expectations change, `_template/service_scaffold/` and `scripts/scaffold_service.py` must change with them.
