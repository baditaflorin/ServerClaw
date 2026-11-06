# 0infer CI worker onboarding

## Goal

Connect the new 0infer builder to the 0exec Woodpecker fleet with per-agent
credentials, private Tailscale access, and host capacity telemetry. Keep
database access limited to the PostgreSQL service port.

## Current state

- VM702 (`infer-builder-ci`) is Debian 13 with Docker, 20 active vCPUs, a
  20-core ceiling, and 24 GiB configured RAM with a 16 GiB balloon floor.
- Tailscale address is `100.64.0.23`; the node exporter listens on that
  address at port 9100.
- Woodpecker agent ID 101 is registered on `ci.0exec.com`, has six slots, and
  is schedulable. The controller has the VM702 metrics endpoint. A CI pipeline
  has completed on this agent.
- The production database is the existing 0database Proxmox guest VM100
  `pg-primary` at `10.50.0.10` / Tailscale `100.64.0.10` (PostgreSQL 18.6).
  The new 0infer PostgreSQL guest at `10.70.10.10` is a separate database and
  is not the production primary.
- VM702 and runtime VM703 currently have the narrowly scoped grant to
  `10.70.10.10:5432`. This work adds TCP 5432 access to `100.64.0.10` for
  those two tagged guests. PostgreSQL still requires valid database credentials
  and grants.
- VM703 (`infer-runtime`, `10.70.10.30` / Tailscale `100.64.0.24`) now has
  Docker Engine, Buildx, and Compose installed. Its daemon uses 10 MiB / five
  file JSON log rotation and non-overlapping default address pools. It has no
  application containers or production database credentials configured yet.

## Completion checks

1. Policy changes pass CI, merge, and apply with ACL tests green.
2. Agent 101 is registered with its per-agent Fleet Secrets consumer, six job
   slots, Docker backend labels, and scheduling enabled after metrics checks.
3. Verify TCP reachability from VM702 to the production primary at
   `100.64.0.10:5432`; confirm authentication only through an approved
   application or CI credential.

## Live apply — 2026-10-14

Merged as PR [#397](https://github.com/baditaflorin/platform_server/pull/397),
commit `4df519653d7d5af7c9f9cbd31bd111aaaa815e25`, and applied through the
managed Tailscale policy workflow. The policy grants VM702 (`tag:infer-builder-ci`)
and VM703 (`tag:infer-runtime`) TCP 5432 to `pg-primary` at `100.64.0.10`;
SSH and Proxmox management ports remain denied by policy tests. The sync tool
saved rollback copy
`/var/lib/tailscale-policy-sync/rollback/policy.20261014T084826Z.1cf3be20c041.hujson`.

From VM702, `nc -vz -w 5 100.64.0.10 5432` succeeded. PostgreSQL accepts
tailnet clients with SCRAM authentication, but this probe did not authenticate
to a database or validate a CI secret. The operator SSH key was not accepted by
VM703, so its probe ran through the active Proxmox QEMU guest agent instead:
`qm guest exec 703 --timeout 15 -- nc -vz -w 5 100.64.0.10 5432` succeeded
inside the guest. Both VM702 and VM703 now have verified TCP reachability;
database authentication remains untested.

## Runtime baseline — 2026-10-14

Installed Docker Engine `29.9.0`, Compose `5.6.0`, and Buildx `0.38.0` on VM703
from Docker's Debian 13 apt repository. The daemon is enabled and active; the
guest has zero running containers. VM703 still reaches both PostgreSQL
endpoints on TCP 5432 after Docker startup. These are network checks only and
do not authenticate to either database. No VM restart or database mutation
occurred. The apply receipt is
`ws-0528-0infer-runtime-docker-apply-receipt`.
