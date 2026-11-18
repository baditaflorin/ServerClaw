# ADR 0496: Use a direct Debian worker for short-lived external build capacity

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.179.65
- Implemented In Platform Version: not applicable (external worker)
- Implemented On: 2026-11-18
- Date: 2026-11-18
- Concern: platform
- Tags: build-worker, temporary-host, lifecycle, ci

## Context

A provider can supply a short-lived Debian virtual machine to add build and CI
capacity. The machine is already a KVM guest and has no requirement to host
multiple independently managed virtual machines. Its useful work is container
image builds and CI jobs; the CI control plane already runs elsewhere.

The trial also provides a practical first pass at machine onboarding and
sunset. It must be possible to identify the provider resource, its expiry, and
every fleet registration that must be removed when the trial ends.

## Decision

1. Keep the provider's Debian installation and configure Docker, Buildx or
   BuildKit, monitoring, and the required Woodpecker agents directly on the
   guest. Do not install Proxmox VE for a single-host, 30-day worker. Revisit
   this only if the machine must host several independently managed guests or
   a tested Proxmox workflow is itself the trial objective.
2. Keep Woodpecker's control plane and repository registrations on the existing
   CI instances. The temporary machine is an execution worker only. Route each
   pipeline to the existing instance required by its labels; never move an
   `lv3=true` repository to the fleet CI instance.
3. Join the tailnet as `tag:build-worker` through an interactive,
   human-approved device enrollment for this first trial. A tailnet admin
   approves the device when device approval is enabled, and an already trusted
   signing device separately signs its node key under Tailnet Lock. The
   existing admin group already owns `tag:build-worker`, so this path needs no
   temporary policy-owner change. Reserve the pre-authorized enrollment
   broker for explicitly unattended server onboarding; it bypasses manual
   device approval.
4. Keep the host identity and lifecycle state in the private `fleet-state`
   `host-records/<name>.json` record. The `fleet-host-sunset` tool owns its
   schema and validator; this work adds optional `expires_at` as a UTC
   timestamp. Keep this runtime host record outside the Proxmox guest
   inventory and `versions/stack.yaml`.
5. Treat this record as the identity and lifecycle source, not a full worker
   manifest: its current schema has no separate `created_at`, capacity,
   purpose, or integration-ID fields. Keep Buildx worker limits in the private
   builder-pool configuration, each Woodpecker plane's node/agent assignments
   in that plane's load-controller configuration, and credentials in Fleet
   Secrets. The generic onboarding and sunset steps live in this repository's
   runbook; the existing dedicated build-host repository describes its own
   host and is not a generic source of truth for this worker.
6. Start an 8-vCPU, 16-GiB worker with no more than two total concurrent CI
   workflows and a 5-GiB per-step memory cap. Do not advertise a large-memory
   label. Increase capacity only after reviewing host memory and CI resource
   telemetry.
7. Treat caches as disposable. Set bounded cache cleanup and disk alerts; do
   not back up build caches as if they were unique data.
8. Sunset by first closing the worker to new jobs, draining active work,
   removing its CI and Buildx registrations, revoking its worker credentials,
   removing its Tailscale device and monitoring entries, and then deleting the
   provider resource. Record the result and any retained build artifacts in a
   live-apply receipt.

## Consequences

- The trial puts all available CPU and memory toward builds without adding a
  second hypervisor layer or creating guests that must also be maintained.
- The provider VM can be recreated from the lease and repository configuration;
  local caches and agent state are not recovery dependencies.
- The machine is deliberately small relative to the existing dedicated build
  hosts. Pipeline labels and slot caps must keep memory-heavy jobs on eligible
  workers.
- Deletion is safe only after schedulers report the worker idle and all
  external registrations and worker tokens have been removed.

## Implementation state

The first trial is active as a direct Debian 13/KVM worker. Tailscale 1.104.7
is installed and signed in as `tag:build-worker`. Docker CE 29.10.0, Buildx
0.39.0, and Compose 5.8.0 are installed for the non-root `ops` account;
bounded daemon logs and a daily cache/image prune timer are active. SSH listens
only on the tailnet address, with root and password login disabled. Node
exporter is active on the tailnet and the monitoring controller fetched its
metrics successfully.

The general Woodpecker controller mirror was reconciled before enabling the
worker. A Docker agent is active with a two-workflow ceiling, 5-GiB per-step
memory and swap limits, and no `lv3` label. The latest recorded 100-pipeline
execution report includes this agent in 33 records: 17 succeeded, 12 were
marked killed, and 4 were still running at the sample time. One successful
pipeline ran entirely on this worker; the other matching records were
distributed across multiple workers. This proves a successful general
Woodpecker pipeline completed here. The report does not establish why the
killed pipelines ended, and it does not prove a standalone Buildx pool build
or production image publication.

The guest is not yet registered in the `go-url-categorizer-api` Buildx pool.
That project's existing selector requires live telemetry from a physical
Proxmox hypervisor and fails closed for provider-managed KVM guests. Workstream
`ws-20261118-kamateratmp-build-pool-expansion` adds an explicit guest-scoped
admission path while preserving the physical-host check for existing workers.
Until that consumer change and its live context are merged and verified, this
worker provides general Docker builds through Woodpecker only. Its GoURL
selector will observe central Fleet Runner reservations but will not acquire a
Fleet Runner lease for its own build, so those builds must be serialized with
other work on the guest.

The provider's exact billing cutoff remains unconfirmed. The private
`fleet-state` host record stores an operator sunset target in `expires_at`, but
that field is metadata only and schedules no reminder or retirement. Confirm
the provider deadline and start the documented drain before the earlier date.
The host record and host-specific automation remain in private `fleet-state`;
the generic procedure is in this repository, and the schema/validator live in
`fleet-host-sunset`.

The first hardening attempts exposed a provider-image discrepancy: active SSH
settings were in the main file while the expected drop-in include was
commented. The host-specific automation and recovery behavior are documented
in private `fleet-state/hosts/<name>/`. The existing `docker_runtime` and
`build_server` roles remain scoped to managed guests and the shared build-cache
host; they are not a generic external-worker profile.

## References

- ADR 0082: Remote build execution gateway
- ADR 0287: Woodpecker CI as the API-driven continuous integration server
- ADR 0409: Zero sanitization publication
- `docs/runbooks/temporary-build-worker.md`
