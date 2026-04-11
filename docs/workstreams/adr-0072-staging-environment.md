# Workstream ADR 0072: Staging And Production Environment Topology

- ADR: [ADR 0072](../adr/0072-staging-and-production-environment-topology.md)
- Title: Define a disposable staging environment mirroring production topology on a separate internal bridge
- Status: ready
- Branch: `codex/adr-0072-staging-environment`
- Worktree: `../proxmox-host_server-staging-environment`
- Owner: codex
- Depends On: `adr-0063-platform-vars-library`, `adr-0042-step-ca`, `adr-0043-openbao`
- Conflicts With: any workstream that hardcodes `10.10.10.*` IPs or `example.com` hostnames in a role without env-variable resolution
- Shared Surfaces: `versions/stack.yaml`, `inventory/group_vars/platform.yml`, Proxmox network config (`vmbr20`), inventory files

## Scope

- add `environments` block to `versions/stack.yaml` (production + staging definitions)
- create `inventory/staging/` directory with hosts file pointing to `10.20.10.*` addresses
- create `vmbr20` bridge on the Proxmox host (`10.20.10.0/24`) — internal-only, NAT disabled
- provision staging intermediate CA in step-ca under `staging-intermediate` issuer
- create `staging/` mount in OpenBao with a mirrored policy hierarchy
- update `filter_plugins/platform_facts.py` to resolve env-scoped values from `stack.yaml`
- update all playbooks to accept `--extra-vars "env=staging"` and resolve hosts via platform facts
- provision staging VMs (VMIDs 210-260) from the same cloud-init template as production
- document the staging topology in `docs/runbooks/staging-environment.md`

## Non-Goals

- persistent staging data (staging state is disposable and recreatable)
- staging VM high availability or storage replication
- public DNS entries for `*.staging.example.com` (internal-only resolution)

## Expected Repo Surfaces

- `versions/stack.yaml` (environments block)
- `inventory/staging/` directory
- `inventory/group_vars/staging.yml`
- updated `filter_plugins/platform_facts.py`
- `docs/runbooks/staging-environment.md`
- `docs/adr/0072-staging-and-production-environment-topology.md`
- `docs/workstreams/adr-0072-staging-environment.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `vmbr20` bridge on Proxmox host
- staging VMs: `docker-runtime` (VMID 220), `monitoring` (VMID 240) as minimum viable staging set
- staging step-ca intermediate issuer
- staging OpenBao mount `staging/`

## Verification

- `make live-apply env=staging playbook=docker-runtime.yml` completes without error
- staging VM is reachable via SSH on `10.20.10.20`
- staging VM cannot reach production VMs on `10.10.10.0/24`
- OpenBao staging token cannot read `secret/prod/` mounts

## Merge Criteria

- at least two production playbooks run cleanly against `env=staging` without modification
- staging and production VMs cannot route to each other (firewall verification)
- `make validate` passes with the platform facts update
- staging runbook reviewed and accurate

## Notes For The Next Assistant

- start by updating `filter_plugins/platform_facts.py` — everything else depends on correct env-scoped fact resolution
- the `vmbr20` bridge requires a Proxmox host play; create it as a small targeted play in `playbooks/proxmox-staging-bridge.yml` before trying to provision staging VMs
- do not modify `inventory/group_vars/all.yml` for staging values; all staging overrides must go through the environment-scoped resolution path in the facts library
