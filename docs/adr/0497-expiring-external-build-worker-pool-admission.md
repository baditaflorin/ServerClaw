# ADR 0497: Admit expiring external guests to shared build pools

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.179.65 (PR #705 merged; patch release pending)
- Implemented In Platform Version: Fleet Runner v0.7.776; no Proxmox platform version change
- Implemented On: 2026-11-18
- Date: 2026-11-18
- Concern: platform
- Tags: build-worker, ci, lifecycle, capacity

## Context

A short-lived provider-managed Debian guest can add useful image-build and
general CI capacity without becoming a Proxmox host. Fleet Runner, Woodpecker,
and project-specific Buildx pools are separate schedulers. Adding a worker to
one does not make it available to the others, and a worker intended to last
about a month must stop receiving new work at its sunset target.

GoURL's existing `hypervisor` Buildx rows verify a physical Proxmox host and its
RAM reserve. A provider-managed guest cannot provide that evidence. Simply
removing the check would let a guest bypass the physical-host protection for
existing workers. The guest therefore needs an explicit resource scope and a
separate admission rule based on its own live telemetry and central worker
policy. GoURL merged that guest-scoped selector in PR #4339. Kamateratmp's
inventory entry, SSH context, and cache-only Buildx canary have since been
verified live from Builder LXC 108.

## Decision

1. Keep a provider-managed guest as a directly managed Debian worker. Do not
   install Proxmox VE for a single short-lived build host.
2. Add an optional strict UTC `expires_at` to Fleet Runner worker policy. Reject
   malformed configured values. At or after the deadline, report the worker as
   expired and exclude it before Buildx or SSH probes.
3. Add the same deadline to the general Woodpecker load-controller node policy.
   At expiry, close matching agents to new work even if that crosses the
   configured minimum-open-node count. Do not cancel active workflows. A
   malformed non-empty deadline fails closed; clearing or extending a deadline
   requires an operator to deliberately reopen agents after review.
4. Cap the temporary worker at one Fleet Runner leased image build. Keep the
   general `ci.0exec.com` agent at its existing two bounded workflow slots and
   do not add an `lv3` label. `ci.example.org` remains a separate authority for
   `lv3=true` workloads.
5. Add a `guest` resource scope to GoURL's Buildx inventory. Guest admission
   still requires central policy approval, a matching Buildx SSH endpoint, live
   guest CPU/memory/disk/I/O metrics, the memory floor, existing central
   reservations, and one additional build footprint. Existing `hypervisor`
   rows retain their Proxmox identity and physical-RAM checks.
6. Treat GoURL's selector as an admission snapshot, not a lease. It observes
   Fleet Runner reservations but does not create one for its own builds. Keep
   GoURL image builds serialized with Fleet Runner and CI workloads on this
   guest. Do not add the separate sitemap-finder selector until it shares
   central admission.
7. Treat the configured deadline as an operator sunset target until the
   provider confirms its billing or termination cutoff. Confirm that cutoff and
   move the target earlier when required. The deadline does not schedule a
   reminder or delete the provider resource.
8. Upgrade the live Fleet Runner reader before copying a config containing
   `expires_at`; its strict loader rejects unknown fields and would otherwise
   fail closed for the whole pool. Verify deployed admission thresholds against
   the source and canonical policy before enabling the new entry.

## Implementation and verification

The implementation spans Fleet Runner, private `fleet-state` worker policy,
the `services-registry` Woodpecker controller, GoURL's consumer-specific
Buildx inventory, and this repository's lifecycle runbook. GoURL's guest-scope
selector source merged as PR #4339 at
`91eeb2fae9e6ff8d83ffbd47b6b7509c97c1bf38`. Fleet Runner PR #1044
(`4da231cc`, v0.7.776), services-registry PR #1212, and fleet-state PR #766
are merged. On 2026-11-18, the Tailscale-signed SSH fingerprint was verified,
the live Fleet Runner worker policy and controller expiry were applied, and
the GoURL Buildx context and builder were created on CT108. The live selectors
admit Kamateratmp, and a cache-only build completed without publishing an
image. PR #705 merged to `main` at `b1d5571dca1b26c1980f03f589444229f93be8c0`.
The release manager currently blocks a version cut because 105 repository
release blockers remain, including 12 expired pre-existing waiver failures;
the repo version remains 0.179.65 and this change is pending the next eligible
patch release. No Proxmox platform-version bump applies to this external worker.

Completion requires live status from both admission paths, a safe cache-only
Buildx canary, and a successful general Woodpecker pipeline attributed to the
worker. A pipeline assignment without a completed result is not proof of a
usable build worker. Record the merge SHAs, live config state, pipeline/build
evidence, and rollback details in the workstream receipt.

During preflight on 2026-11-18, `/root/.fleet-runner.env` overrode the source
thresholds with load/CPU `<3.0` and free disk `>=10240 MiB`. Fleet Runner's
self-update check verified the installed v0.7.776 source SHA
`4da231cc4dc96cf523beee45441a3fd2ae0c68ee`. The two non-secret overrides were
aligned to `<1.0` and `>=20000 MiB` before admission; live status confirms the
new thresholds. This excludes the 0mcp builder at its latest 19,036 MiB free
disk sample. GoURL's own selector default remains 10,240 MiB, but its required
central Fleet Runner admission enforces 20,000 MiB on CT108. The provider's
billing cutoff remains unconfirmed, so the configured expiry is an operator
sunset target rather than proof of provider termination.

## Consequences

- A guest can join a shared Buildx consumer without weakening the physical
  hypervisor check for Proxmox-backed workers.
- Expired temporary workers stop receiving new Fleet Runner builds and
  Woodpecker workflows; running jobs are left to finish and require an explicit
  sunset drain before provider deletion.
- GoURL's direct selector remains less strongly coordinated than Fleet Runner
  leases. Its use of a shared guest is therefore serialized and documented as
  an admission snapshot.
- Repository policy and operational evidence stay in GitHub; the server is not
  the only record of its own configuration or sunset.
