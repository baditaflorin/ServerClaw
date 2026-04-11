# Staging And Production Topology

## Purpose

This runbook records how the repository models the two named platform environments:

- `production`
- `staging`

The current platform is still a single-node Proxmox estate, so this runbook is about **naming, publication, and isolation rules**, not about a separate live staging cluster.

## Canonical Files

- `config/environment-topology.json`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`

These three files must stay aligned:

- environment-wide rules belong in `environment-topology.json`
- per-service environment URLs belong in `service-capability-catalog.json`
- DNS publication intent belongs in `subdomain-catalog.json`

## Current Topology Contract

### Production

- status: `active`
- public hostname pattern: `*.example.com`
- edge path: shared NGINX edge on `nginx-edge`
- purpose: live operator and platform surfaces

### Staging

- status: `planned`
- public hostname pattern: `*.staging.example.com`
- edge path: same shared NGINX edge on `nginx-edge`
- purpose: pre-production validation for selected services

## Isolation Rules

Staging must not reuse production mutable state by default.

When a service adds a staging surface, give staging separate:

- DNS names
- client credentials and secrets
- persistent volumes
- databases, schemas, buckets, or queues

Allowed shared infrastructure in the current topology:

- Proxmox host
- NGINX edge VM
- operator private-access path over Tailscale

## Adding A New Staged Service

1. Add or update the service in `config/service-capability-catalog.json`.
2. Add a `staging` binding under `service.environments`.
3. Add the staged hostname to `config/subdomain-catalog.json` with `environment: staging`.
4. Keep the staged hostname under `*.staging.example.com`.
5. If the service needs different environment-wide rules, update `config/environment-topology.json`.
6. Run:

```bash
uvx --from pyyaml python scripts/environment_topology.py --validate
uvx --from pyyaml python scripts/service_catalog.py --validate
uvx --from pyyaml python scripts/subdomain_catalog.py --validate
uvx --from pyyaml python scripts/generate_ops_portal.py --check
```

## Operator Notes

- Do not claim a staging surface is live just because it exists in repo metadata.
- A staged hostname should stay `planned` in the subdomain catalog until the owning service rollout applies it from `main`.
- If staging ever moves to dedicated VMs or a separate node, update ADR 0072 and `config/environment-topology.json` first so later service changes inherit the right topology contract.
