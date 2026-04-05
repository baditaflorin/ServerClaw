# ADR 0346: Centralized Port Registry

- Status: Accepted
- Implementation Status: In Progress
- Implemented In Repo Version: not applicable
- Implemented In Platform Version: not applicable
- Implemented On: not applicable
- Date: 2026-04-05
- Tags: platform, ports, configuration, dry, contracts

## Context

Port numbers for platform services are currently scattered across at least
three locations:

1. **`inventory/host_vars/proxmox_florin.yml` — `platform_port_assignments`**:
   The canonical registry of ~110 port numbers, keyed by name.

2. **`scripts/generate_platform_vars.py`** — `PORT_KEYS` tuple and
   `build_service_urls()`: The generator that resolves these ports into the
   `platform_service_topology` block emitted to
   `inventory/group_vars/platform.yml`.

3. **Role `defaults/main.yml` files**: ~40 roles hardcode port numbers
   directly, duplicating values already in `platform_port_assignments` and
   diverging silently when the registry changes.

This has caused real incidents. The Keycloak SSO login failure on Gitea
(2026-04-05) was rooted in `gitea_root_url` falling back to
`gitea_controller_url` — the internal host-proxy port `3009` — instead of
the HTTPS public URL. The immediate trigger was `gitea_service_topology.urls.public`
not being set in the raw topology, but the underlying condition was that the
role default encoded a port-bearing fallback at all. Had `gitea_root_url`
referenced `platform_service_port('gitea', 'public')` no fallback could have
leaked a wrong port.

Additional structural issues found during investigation:

- `PORT_KEYS` in the generator had `headscale_http_port` listed twice.
- `mail_platform_internal_submission_port` existed in `platform_port_assignments`
  but was absent from `PORT_KEYS`, so it was silently dropped from the
  generated output.
- Keycloak ports (`8091`, `18080`, `19000`) were absent from
  `platform_port_assignments` entirely, forcing every consumer to hardcode
  them.
- No collision detection existed; duplicate values in `_host_proxy_port` keys
  (all bound on the same controller host) could not be caught at generation
  time.

## Decision

### 1. `platform_port_assignments` is the single source of truth for all platform-managed port numbers

A port is "platform-managed" if it is:
- A service's listen port on a platform VM (e.g. `gitea_http_port: 3003`)
- A host-proxy/controller forwarding port on the Proxmox host
  (e.g. `gitea_host_proxy_port: 3009`)
- Any other port whose number is assigned by this repository rather than by
  an upstream project or IANA standard

Standard protocol ports that are not platform-assigned (PostgreSQL `5432`,
Redis `6379`, SSH `22`, NATS `4222`, etcd `2379`/`2380`, SQUID `3128`,
standard HTTP `80` / HTTPS `443` **when used as fixed protocol ports inside
containers**) are exempt and may remain hardcoded.

### 2. Role defaults must not hardcode platform-managed port numbers

Role `defaults/main.yml` files **must not** contain bare integer port
assignments for platform-managed ports. The only permitted patterns are:

```yaml
# Pattern A — service topology (preferred for service internal/controller ports)
my_service_port: "{{ platform_service_topology | platform_service_port('my_service', 'internal') }}"

# Pattern B — flat assignment (acceptable for ports without a topology entry)
my_service_port: "{{ hostvars['proxmox_florin'].platform_port_assignments.my_service_port }}"
```

Pattern A is preferred because it colocates the port with the service's full
address, preventing the controller-port-leaks-into-public-URL class of bug.

### 3. `PORT_KEYS` in `generate_platform_vars.py` must stay in sync with `platform_port_assignments`

Every key in `platform_port_assignments` that is not a Jinja2 template must
appear in `PORT_KEYS`. The generator validates this at runtime and fails with
a clear error for missing or unknown keys.

### 4. Collision detection on controller/host-proxy ports

`generate_platform_vars.py` must detect duplicate values among all
`_host_proxy_port` keys at build time. These ports all bind on the same
controller host interface; a collision causes a silent service outage.
The generator fails with a descriptive error listing the conflicting keys.

### 5. New ports follow the registry-first workflow

Adding a new platform service requires:

1. Add an entry to `platform_port_assignments` in
   `inventory/host_vars/proxmox_florin.yml`.
2. Add the key to `PORT_KEYS` in `generate_platform_vars.py`.
3. Add the service to `build_service_urls()` in the same file.
4. Run `make generate-platform-vars` to regenerate
   `inventory/group_vars/platform.yml`.
5. Reference the port in role defaults via Pattern A or B above.

## Consequences

### Positive

- Port numbers appear exactly once; consumers reference a name, not a magic
  number. Renumbering a port means changing one line in host_vars and
  regenerating.
- Collision detection catches controller-port conflicts before they reach
  production.
- The controller-port-leaks-into-public-URL bug class is eliminated: roles
  that reference `platform_service_port('x', 'internal')` can never
  accidentally receive the controller port.
- The `PORT_KEYS` / `platform_port_assignments` sync rule gives a clear
  checklist item when onboarding a new service.

### Negative / Trade-offs

- Roles that previously had self-contained defaults now depend on
  `platform_service_topology` or `platform_port_assignments` being in scope.
  This is already true for newer roles and is acceptable given this is a
  single-platform repository.
- ~40 existing role defaults require migration; this is done incrementally
  as roles are touched rather than in a single flag-day commit.
- Standard-protocol exemption requires judgment calls at the margin (e.g.
  `8080` inside a container is exempt; `8080` bound on a VM host interface
  is not). The rule of thumb: if the number is in `platform_port_assignments`,
  use it from there.

## Boundaries

- Applies only to services hosted on the `proxmox_florin` platform and its
  guest VMs.
- Does not cover ports used exclusively inside Docker Compose networks
  (container-to-container traffic) that are never exposed on a VM interface.
- Does not retroactively require migration of already-deployed services
  before their next role change; migration is opportunistic.

## Implementation Notes

The initial implementation (this ADR) includes:

1. Fix `generate_platform_vars.py`:
   - Remove the Gitea-specific `urls.public` override that generated
     `http://git.lv3.org:3009` instead of `https://git.lv3.org`.
   - Remove the duplicate `headscale_http_port` entry from `PORT_KEYS`.
   - Add `mail_platform_internal_submission_port` to `PORT_KEYS`.
   - Add `keycloak_internal_http_port` to `PORT_KEYS` and
     `build_service_urls()`.
   - Add `_host_proxy_port` collision detection.

2. Add `keycloak_internal_http_port: 8091` to `platform_port_assignments`
   and update the keycloak service topology in `host_vars` to reference it
   via template instead of the bare integer.

3. Migrate role defaults for the highest-impact services: `keycloak_runtime`,
   `alertmanager_runtime`, `monitoring_vm`, `mail_platform_runtime`,
   `directus_runtime`, `gotenberg_runtime`, `dozzle_runtime`,
   `crawl4ai_runtime`, `gitea_runtime`.

Remaining roles are tracked as a follow-up; each PR that touches a role
`defaults/main.yml` must migrate any hardcoded platform-managed port it
encounters.

## Related ADRs

- ADR 0165: Role interface contracts and defaults boundaries
- ADR 0344: Single-source environment topology
