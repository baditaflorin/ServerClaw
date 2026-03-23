# Scaffold A New Service

`make scaffold-service` creates the repo skeleton for a new service on the current mainline contracts.

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
  - `workstreams.yaml`
- placeholder Trivy receipt under `receipts/image-scans/`

## Validation Model

The generator writes a *planned* service contract with explicit scaffold placeholders.

`make validate-data-models` and `make validate` now fail if any scaffolded catalog or topology value still contains `TODO`.

That means the expected flow is:

1. run `make scaffold-service`
2. refine the generated role, playbook, ADR, workstream, and runbook
3. replace every scaffold placeholder in topology and catalogs
4. run `make validate`

## Common Follow-Up

1. Pin the runtime image digest:

```bash
make pin-image IMAGE=docker.io/vendor/image:tag
```

2. Replace the placeholder digest, receipt metadata, and any scaffold notes in `config/image-catalog.json`.
3. Replace the scaffolded health endpoint and monitor descriptions in `config/health-probe-catalog.json`.
4. Review `inventory/host_vars/proxmox_florin.yml` and adjust DNS or edge publication details.
5. Finish the ADR and runbook content before merge.
