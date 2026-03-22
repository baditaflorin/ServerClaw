# ADR 0078: Service Scaffold Generator

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Adding a new service to the platform currently requires a human to manually:

1. write an ADR
2. create a workstream doc and update `workstreams.yaml`
3. create an Ansible role (copying and adapting boilerplate from an existing role)
4. write a playbook
5. write or adapt a Docker Compose file
6. register the service in `config/health-probe-catalog.json`
7. register container images in `config/image-catalog.json`
8. register secrets in `config/secret-catalog.json`
9. add the service to `config/service-capability-catalog.json` (ADR 0075)
10. add a subdomain entry to `config/subdomain-catalog.json` (ADR 0076)
11. write a runbook
12. configure the OpenBao Agent for secrets injection (ADR 0077)

This is 12 manual steps with no validation that any of them are done. Services introduced over the last year have inconsistent catalog registrations — some are missing health probes, some lack image-catalog entries, and several have no runbooks.

ADR 0062 introduced a role template. This ADR extends that concept to the full service onboarding surface.

## Decision

We will implement a service scaffold generator as a `make` target that creates the complete skeleton for a new service from a single command.

### Invocation

```bash
make scaffold-service \
  NAME=my-service \
  DESCRIPTION="One-line description" \
  CATEGORY=automation \
  VM=docker-runtime-lv3 \
  VMID=120 \
  PORT=8080 \
  SUBDOMAIN=my-service.lv3.org \
  EXPOSURE=edge-published \
  IMAGE=docker.io/vendor/image:latest
```

### Generated artifacts

The generator (`scripts/scaffold_service.py`) creates the following files, with all NAME/VMID/PORT placeholders substituted:

| File | Description |
|---|---|
| `docs/adr/XXXX-<name>.md` | ADR stub (next available number, Status: Proposed) |
| `docs/workstreams/adr-XXXX-<name>.md` | Workstream doc stub |
| `docs/runbooks/<name>.md` | Operational runbook stub |
| `roles/<name>_runtime/` | Full role directory from `roles/_template/` |
| `roles/<name>_runtime/templates/docker-compose.yml.j2` | Compose template with OpenBao agent sidecar |
| `roles/<name>_runtime/templates/openbao-agent.hcl.j2` | Pre-configured OpenBao agent |
| `playbooks/<name>.yml` | Playbook targeting the correct VM and role |

### Catalog entries appended by the generator

The generator appends structured entries to four catalog files, leaving `TODO` markers for fields requiring human input:

**`config/health-probe-catalog.json`:**
```json
{
  "id": "<name>",
  "url": "http://<vm-ip>:<port>/health",
  "method": "GET",
  "expected_status": 200,
  "timeout_seconds": 5,
  "TODO": "confirm actual health endpoint path"
}
```

**`config/image-catalog.json`:**
```json
{
  "id": "<name>",
  "image": "<IMAGE>",
  "pinned_digest": "TODO: run make pin-image IMAGE=<IMAGE>",
  "scan_receipt": null,
  "last_updated": "TODO"
}
```

**`config/secret-catalog.json`:**
```json
{
  "id": "<name>-admin",
  "description": "TODO: describe this secret",
  "openbao_path": "secret/prod/<name>/",
  "rotation_period_days": 90,
  "last_rotated": null
}
```

**`config/service-capability-catalog.json`:**
```json
{
  "id": "<name>",
  "name": "<NAME>",
  "description": "<DESCRIPTION>",
  "category": "<CATEGORY>",
  "vm": "<VM>",
  "vmid": <VMID>,
  "internal_url": "http://<vm-ip>:<PORT>",
  "subdomain": "<SUBDOMAIN>",
  "exposure": "<EXPOSURE>",
  "health_probe_id": "<name>",
  "image_catalog_ids": ["<name>"],
  "secret_catalog_ids": ["<name>-admin"],
  "adr": "XXXX",
  "runbook": "docs/runbooks/<name>.md",
  "tags": ["TODO"]
}
```

**`config/subdomain-catalog.json`** (if EXPOSURE is not `private-only`):
```json
{
  "fqdn": "<SUBDOMAIN>",
  "service_id": "<name>",
  "environment": "production",
  "exposure": "<EXPOSURE>",
  "target": "<vm-ip>",
  "target_port": <PORT>,
  "tls": { "provider": "letsencrypt", "auto_renew": true },
  "created": "<today>",
  "owner_adr": "XXXX"
}
```

### Workstreams.yaml update

The generator appends a new workstream entry to `workstreams.yaml` with `status: ready`, `live_applied: false`, and `depends_on: []` (operator fills in dependencies).

### Post-generation checklist

The generator prints a checklist of actions the developer must complete manually:

```
Scaffold created for 'my-service'. Required next steps:
  [ ] Fill in ADR context and consequences: docs/adr/XXXX-my-service.md
  [ ] Pin container image digest: make pin-image IMAGE=docker.io/vendor/image:latest
  [ ] Register secrets in OpenBao: vault kv put secret/prod/my-service/ ...
  [ ] Update TODO fields in catalog entries
  [ ] Declare workstream dependencies in workstreams.yaml
  [ ] Run make validate to confirm all catalog cross-references resolve
```

### Validation gate update

`make validate` will error if any catalog entry contains a `TODO` string value. This ensures scaffolded entries are completed before they reach main.

## Consequences

- Service onboarding is consistent and complete; missing catalog entries become a validation error, not a future discovery.
- Agent-assisted onboarding becomes feasible: an agent can run the scaffold command, fill in the TODO fields from context, and propose the resulting commit.
- The generator is itself a maintained script; it must be updated when new catalog files are introduced.
- The generated ADR stub must be substantively written by a human or agent before the workstream is considered `ready`; the scaffold creates the skeleton, not the decision.

## Boundaries

- The generator creates files and catalog entries. It does not run Ansible, provision DNS, or interact with OpenBao. Those happen in the normal live-apply flow.
- Infrastructure-level additions (new VMs, new bridges) are not covered by this scaffold; they require host-level ADRs and playbooks that are not service-scoped.
- The generator assumes Docker Compose deployment on `docker-runtime-lv3`. Services deployed as native systemd units or as Proxmox VMs use the existing role template (ADR 0062) without the Compose-specific artifacts.
