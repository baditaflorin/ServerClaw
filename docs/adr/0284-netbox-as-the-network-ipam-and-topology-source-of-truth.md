# ADR 0284: Netbox As The Network IPAM And Topology Source Of Truth

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform allocates IP addresses, VLANs, and subnets as services are
provisioned. At present this allocation lives in Ansible variable files and
in operator memory. There is no authoritative, queryable registry of:

- which prefixes are in use and which are free
- which VLAN ID is assigned to which network segment
- which VM or container owns which IP address
- what the rack topology and physical-to-logical mapping looks like

This means provisioning workflows in Windmill and n8n must hard-code IP
assumptions or parse YAML files. When an operator needs a free address, they
grep variable files rather than calling an API. When a service is
decommissioned, its address record lives only in the operator's head until
the next Ansible converge corrects the drift.

Netbox is a CPU-only, open-source IP Address Management (IPAM) and Data
Centre Infrastructure Management (DCIM) platform. It exposes a fully
documented REST API and a GraphQL endpoint generated from the same schema.
Every object type—prefix, IP address, VLAN, device, virtual machine,
interface—is a first-class REST resource with a stable URL. The OpenAPI
specification is served at `/api/schema/` and can be imported directly into
Postman, Insomnia, or auto-generated into Windmill resources.

## Decision

We will deploy **Netbox** as the single authoritative source of truth for
network topology, IP address allocation, and VLAN management.

### Deployment rules

- Netbox runs as a Docker Compose service on the docker-runtime VM using the
  official `netboxcommunity/netbox` image
- Authentication is delegated to Keycloak via OIDC (ADR 0063); local accounts
  are disabled except for the break-glass service account whose password is
  stored in OpenBao (ADR 0077)
- The service is published under the platform subdomain model (ADR 0021) at
  `netbox.<domain>`; the API endpoint is `netbox.<domain>/api/`
- Netbox uses the shared PostgreSQL cluster (ADR 0042) with a dedicated
  `netbox` database; Redis is deployed as a sidecar container in the same
  Compose stack for caching and task queuing
- All persistent data is stored on named Docker volumes included in the backup
  scope (ADR 0086)
- Secrets (database password, secret key, OIDC client credentials) are
  injected from OpenBao following ADR 0077

### API-first operation rules

- All IP address allocations, prefix assignments, and VLAN registrations are
  performed via the Netbox REST API; direct database writes and GUI-only
  operations are prohibited
- Windmill workflows that provision VMs or containers call the Netbox API to
  claim a free IP from the designated prefix before passing the address to the
  Ansible provisioning step
- The Netbox API token for automation is scoped per workflow and stored in
  OpenBao; it is never embedded in Windmill scripts as a literal
- The Netbox GraphQL endpoint (`/graphql/`) is used for complex cross-object
  queries (e.g. "all IPs in prefix X that are assigned to VMs in cluster Y")
  from n8n and Windmill
- The OpenAPI schema at `/api/schema/` is fetched during CI and diffed against
  the pinned version; a schema change triggers an operator review before the
  Netbox image version is promoted

### Data governance rules

- Every IP address record includes a `description` field referencing the
  service or VM it belongs to and a `status` field (`active`, `reserved`,
  `deprecated`)
- Prefixes are tagged by network segment role: `management`, `guest`,
  `services`, `storage`
- When a service is decommissioned, its IP record is set to `deprecated` via
  API before the Ansible role removes the VM; addresses are not deleted for
  12 months to prevent accidental reuse

## Consequences

**Positive**

- Provisioning workflows have a single, typed HTTP call to answer "give me
  the next free IP in the services prefix" instead of parsing YAML files.
- Network drift becomes visible: if Ansible registers a new VM without
  updating Netbox, the discrepancy is immediately visible in the prefix
  utilisation view.
- The OpenAPI schema provides a machine-readable contract; Windmill can
  auto-generate resource types from it.
- Netbox custom fields and tags allow the data model to be extended without
  schema migrations.

**Negative / Trade-offs**

- Netbox becomes a dependency of provisioning workflows; if it is unavailable,
  automated IP allocation is blocked. A fallback static prefix map in Ansible
  must exist for break-glass provisioning.
- Keeping Netbox in sync with actual infrastructure requires disciplined
  hygiene; stale records accumulate if decommission workflows skip the
  Netbox update step.

## Boundaries

- Netbox is the source of truth for IP and VLAN assignments; it does not
  replace Prometheus or Grafana for traffic metrics, nor Uptime Kuma for
  availability monitoring.
- Netbox does not manage DNS records; that responsibility remains with the
  platform's DNS service.
- The DCIM (rack and device tracking) feature is used only for physical hosts;
  virtual machine topology is tracked at the VM/interface level, not modelled
  as rack units.
- Netbox Webhooks may be configured to push change events to NATS JetStream
  (ADR 0276) for downstream automation; this is optional and not required for
  initial deployment.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0276: NATS JetStream as the platform event bus

## References

- <https://netbox.readthedocs.io/en/stable/rest-api/overview/>
- <https://netbox.readthedocs.io/en/stable/graphql-api/overview/>
