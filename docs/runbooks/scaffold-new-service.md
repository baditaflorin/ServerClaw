# Scaffold A New Service

`make scaffold-service` creates the repo skeleton for a new service on the current mainline contracts.

The ADR 0107 formal operator workflow now lives in [add-a-new-service.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-extension-model/docs/runbooks/add-a-new-service.md). Use this runbook as the lower-level reference for the generator itself.

The scaffold does not create capability contracts for you. ADR 0205 requires the capability contract to exist before a new critical shared product is selected, so update `config/capability-contract-catalog.json` first when the new service becomes the shared product for identity, workflow execution, secrets, topology, or another critical platform capability.

## Usage

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

Only `NAME` is required. The target derives defaults for the rest.

## What It Writes

- ADR stub under `docs/adr/`
- workstream stub under `docs/workstreams/`
- runbook stub under `docs/runbooks/`
- collection role scaffold under `collections/ansible_collections/lv3/platform/roles/<name>_runtime/`
- root playbook entry point under `playbooks/`
- service playbook entry point under `playbooks/services/`
- new service entries in:
  - `inventory/host_vars/proxmox_florin.yml`
  - `config/service-capability-catalog.json`
  - `config/subdomain-catalog.json` when a hostname is present
  - `config/health-probe-catalog.json`
  - `config/secret-catalog.json`
  - `config/controller-local-secrets.json`
  - `config/image-catalog.json`
  - `config/api-gateway-catalog.json`
  - `config/dependency-graph.json`
  - `config/slo-catalog.json`
  - `config/data-catalog.json`
  - `config/service-completeness.json`
  - `workstreams.yaml`
- generated dashboard and alert stubs under `config/grafana/dashboards/` and `config/alertmanager/rules/`
- placeholder Trivy receipt under `receipts/image-scans/`

## Validation Model

The generator writes a *planned* service contract with explicit scaffold placeholders.

`make validate-data-models` and `make validate` now fail if any scaffolded catalog or topology value still contains `TODO`.

That means the expected flow is:

1. run `make scaffold-service`
2. refine the generated role, playbook, ADR, workstream, runbook, dashboard, and alert rules
3. replace every scaffold placeholder in topology and catalogs
4. run `lv3 validate --service <service_id>`
5. run `make validate`

## Common Follow-Up

1. Pin the runtime image digest:

```bash
make pin-image IMAGE=docker.io/vendor/image:tag
```

2. Replace the placeholder digest, receipt metadata, and any scaffold notes in `config/image-catalog.json`.
3. Replace the scaffolded startup, liveness, and readiness descriptions in `config/health-probe-catalog.json`.
4. Add `degradation_modes` in `config/service-capability-catalog.json` if the service can stay reachable while a declared soft dependency is impaired.
5. Review `inventory/host_vars/proxmox_florin.yml` and adjust DNS or edge publication details.
6. Use an ADR 0106 ephemeral fixture for destructive or staging-like validation rather than creating an unmanaged long-lived VM.
7. Finish the ADR and runbook content before merge.
