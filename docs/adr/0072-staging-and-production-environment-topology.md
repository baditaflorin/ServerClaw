# ADR 0072: Staging And Production Environment Topology

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Every service on this platform runs in a single environment: production. When a new service is deployed or an existing one changed, the first target is live. There is no environment where a configuration change, a new container image, or a new NGINX route can be validated before it hits real traffic.

This creates several practical problems:

- operator errors during service bring-up (bad env vars, wrong port mappings, missing secrets) cause production outages
- NGINX routing changes for new subdomains cannot be tested without publishing to the live edge
- Ansible playbook changes against real VMs risk leaving services in a half-applied state if a task fails midway
- there is no safe surface for agent-initiated changes pending approval; agents currently must either act live or not at all

The platform is now orchestrating enough services (step-ca, OpenBao, Windmill, mail, Grafana, Keycloak, NATS, Mattermost, Open WebUI) that the cost of a bad live-apply is high. A staging environment that mirrors production topology allows changes to be validated before promotion.

## Decision

We will define a two-environment topology: **staging** and **production**.

### Environment definitions

**Production** — the current platform (`lv3.org`):
- all currently-running VMs on `10.10.10.0/24`
- public subdomains under `lv3.org`
- live credentials, real mail delivery, real PKI
- changes reach production only after passing through staging or through the explicit operator promotion gate

**Staging** — a lightweight parallel environment (`staging.lv3.org`):
- same guest topology, provisioned on a second internal bridge `vmbr20` (`10.20.10.0/24`)
- staging subdomains under `staging.lv3.org` (e.g. `grafana.staging.lv3.org`, `uptime.staging.lv3.org`)
- separate OpenBao mount prefix (`staging/`)
- separate step-ca intermediate issuing staging certificates
- no real mail delivery (Stalwart in test mode, captured by a mailhog-compatible sink)
- all services share the same Ansible roles and Compose stacks as production — no staging-specific code

### Stack.yaml encoding

`versions/stack.yaml` is extended with an `environments` key:

```yaml
environments:
  production:
    bridge: vmbr10
    subnet: 10.10.10.0/24
    gateway: 10.10.10.1
    domain: lv3.org
    openbao_prefix: prod/
    step_ca_intermediate: production-intermediate
  staging:
    bridge: vmbr20
    subnet: 10.20.10.0/24
    gateway: 10.20.10.1
    domain: staging.lv3.org
    openbao_prefix: staging/
    step_ca_intermediate: staging-intermediate
```

### Ansible targeting

All playbooks accept an `--extra-vars "env=staging"` flag. The `platform.yml` computed facts library (ADR 0063) resolves VM IPs, subdomains, and secret paths from the active environment definition.

### Subdomain strategy

- `<service>.lv3.org` — production endpoint (public where appropriate)
- `<service>.staging.lv3.org` — staging endpoint (private-only; not published to public DNS)
- staging subdomains resolve via internal DNS on `vmbr20` only

### VM VMID allocation

Staging VMs use VMIDs in the 200–299 range (production uses 100–199). Staging VMs carry the hostname suffix `-staging` (e.g. `docker-runtime-staging-lv3`).

## Consequences

- Every playbook and role must accept an `env` variable and resolve all environment-specific values through the facts library rather than hardcoding `10.10.10.*` addresses or `lv3.org` names.
- The staging environment can be torn down and recreated from scratch at any time without affecting production — its state is entirely disposable.
- Staging doubles the VM count when fully provisioned; it does not need to run continuously. Staging VMs can be shut down between validation runs.
- The staging bridge (`vmbr20`) is internal-only; staging services are never routed through the public NGINX edge.
- Secret isolation requires that staging OpenBao tokens cannot read production mounts, enforced by separate OpenBao policies per environment prefix.

## Boundaries

- Staging mirrors production topology but does not replicate production data. Database contents, email history, and audit logs are not copied to staging.
- The staging environment does not need high availability or persistent storage; it is a validation surface, not a second production.
- This ADR defines topology only. The promotion workflow (how a validated change moves from staging to production) is addressed in ADR 0073.
