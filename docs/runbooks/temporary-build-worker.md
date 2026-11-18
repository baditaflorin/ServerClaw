# Temporary Build Worker Lifecycle

## Purpose

Use this runbook to onboard and retire a short-lived external Debian worker for
container builds and Woodpecker jobs. The worker is execution capacity only;
existing CI controllers and their persistent state stay on their current
hosts.

## Canonical records

Versioned knowledge is split by ownership across GitHub repositories. The
server is never the canonical home for its own setup instructions or lifecycle
record. Keep live credentials in the secrets service, and store only
non-secret configuration and operational evidence in Git.

Keep the private host identity and lifecycle state in
`fleet-state/host-records/<name>.json`; this is the single host record. Its
`expires_at` field is optional and uses UTC `YYYY-MM-DDTHH:MM:SSZ`. The
`fleet-host-sunset` repository owns the schema and validator. It may hold the
provider's confirmed cutoff or an explicit operator sunset target. Record the
source and timezone basis in the free-text `provider` field, and move the
target earlier if the provider bills or terminates sooner. The field records a
deadline but does not schedule an alert or retirement.

The host record does not currently have separate `created_at`, capacity,
purpose, provider-ID, or integration-ID fields. Put provider task/resource IDs
and creation/billing evidence in its free-text `provider` field; keep each
operational fact with the system that owns it:

| Fact | Canonical home |
|---|---|
| Generic lifecycle decision, procedure, workstream, and apply evidence | This repository: `docs/adr/`, `docs/runbooks/`, `docs/workstreams/`, `workstreams/active/`, and `receipts/live-applies/` |
| Generic Tailscale enrollment policy | This repository: `config/tailscale/policy.hujson` |
| Host identity, provider reference, lifecycle state, expiry target | Private `fleet-state/host-records/<name>.json` |
| Versioned host-specific install/configuration files | Private `fleet-state/hosts/<name>/` |
| Host-record schema, validator, admission and sunset tooling | Private `fleet-host-sunset` repository |
| Buildx worker identity, SSH target, and build ceiling | Private `fleet-state/builder-pool.json` |
| Woodpecker agent IDs and scheduling/health settings | Private `fleet-state/woodpecker-load-controller-ci-0exec.json` and `...ci-0mcp.json`, one config per plane |
| Woodpecker pipeline-to-host attribution and execution report | `services-registry/ci-execution-report.json` and `bin/ci_execution_report.py` |
| Controller implementation and generic load-controller runbook | `services-registry` |
| Worker and controller credentials | Fleet Secrets, with per-consumer allowlists |
| Consumer-specific remote Buildx selection rules | That consumer's repository, for example `go-url-categorizer-api` |

The GitHub repositories above hold the procedures, schemas, automation, and
desired configuration. Woodpecker, Tailscale, and monitoring APIs expose live
state; record important changes and verification evidence in the owning repo's
workstream or receipt. Do not copy credentials into Git to make the records
look complete.

The existing dedicated build-host repository describes its own physical host
and guest; it is not a generic source of truth for unrelated workers. Its
snapshots of external registrations are evidence, not the authoritative
configs. A project-specific Buildx pool, such as the one in
`go-url-categorizer-api`, is a separate consumer and must be updated only if
that project will use this worker and its selector accepts the worker's actual
virtualization and telemetry. GoURL supports an explicit `guest` resource
scope through PR #4339 while retaining physical Proxmox checks for
`hypervisor` rows. GoURL's selector reads central Fleet Runner reservations but
does not create a lease for its own image builds, so those builds must remain
serialized with Fleet Runner and CI activity on this guest.

Do not apply the existing `lv3.platform.docker_runtime` or
`lv3.platform.build_server` roles unchanged to an external lease. The former
targets managed platform guests and carries topology/publication assumptions;
the latter manages the shared build-cache host, including apt-cacher-ng and
internal registry mappings. Neither is a generic standalone-worker profile.
Put this trial's host-specific bootstrap and daemon configuration under the
private `fleet-state/hosts/<name>/` path, and keep its Buildx and Woodpecker
registrations in their separate canonical files.

Do not put lease-specific addresses or hostnames in the generic platform
inventory or `versions/stack.yaml`.

For the first trial, the host-specific Fleet-state automation installs Docker
CE, Compose, Buildx, the `ops` account, bounded Docker logs, a daily seven-day
image/cache prune timer, and tailnet-only node-exporter monitoring. The general
Woodpecker plane has an active Docker agent with at most two concurrent
workflows, a 5-GiB per-step memory and swap ceiling, and no `lv3` label. Its
expiry-aware load-controller configuration is live. GoURL's guest selector
retains the physical-host checks for `hypervisor` rows (PR #4339, merge
`91eeb2fae9e6ff8d83ffbd47b6b7509c97c1bf38`).

On 2026-11-18, the SSH key fingerprint matched Tailscale's signed device
fingerprint. The Mac now pins the tailnet address, and CT108's existing
`HostKeyAlias` pin was verified. CT108 has Docker context
`kamateratmp-amd64-ctx` and Buildx builder `kamateratmp-amd64`. The live
Fleet Runner policy carries the one-build cap and operator expiry. Its
thresholds are `1.0` load/CPU and 20,000 MiB free disk; the 0mcp builder was
below that disk floor at the latest sample. GoURL's own selector default is
10,240 MiB, but its mandatory central Fleet Runner admission enforces the
20,000 MiB floor on CT108. The GoURL selector reported Kamateratmp eligible,
and a `FROM scratch` cache-only Buildx canary completed without publishing an
image. The verified general CI and Buildx paths are ready for use; this does
not prove production image publication.

The provider's billing cutoff has not been confirmed. The current private host
record carries an operator sunset target in `expires_at`; it does not create a
reminder or retire the host. Confirm the provider deadline and schedule the
manual sunset review early enough to drain jobs. The provider Debian image had
active SSH directives in the main config and a commented `sshd_config.d`
include; inspect the live layout before hardening instead of assuming a
distribution default. The host-specific hardening script verifies the
effective policy and listener and rolls back to its preserved provider config
on failure.

## First-trial status

On 2026-11-18, Woodpecker registration 140 was online, schedulable, and had a
fresh heartbeat with capacity for two workflows. The latest 100-pipeline report
included the Kamatera agent in 33 records: 17 succeeded, 12 were marked killed,
and 4 were running. One successful pipeline ran entirely on Kamatera; the other
matching records were mixed across physical workers. The report does not show
why the killed pipelines ended. The `ci.0exec.com` execution report maps both
the active agent name and registration ID to `kamateratmp`, preserving
historical attribution. This confirms general Woodpecker CI use. The separate
GoURL selector status and cache-only Buildx canary now confirm standalone
Buildx admission. Monitoring also fetched the tailnet-only exporter
successfully. The provider billing cutoff remains unconfirmed; the recorded
expiry is the owner-directed sunset target and does not schedule deletion.

## Onboarding

1. Confirm the provider image is Debian 13, record its resource ID and expiry,
   and verify SSH host identity before first login.
2. Add the worker's management SSH key and a named non-root operator account.
   Verify key login and non-interactive sudo over Tailscale before changing SSH.
   Then disable password and root login, bind SSH to the tailnet address, and
   confirm the effective `sshd -T` policy plus the actual listener set. Match
   the live provider config layout: a drop-in-only change is insufficient when
   active settings remain in the main file. Keep provider-console recovery
   available until the new path is verified. Do not keep the provider bootstrap
   password as a runtime secret.
3. Apply the worker baseline: security updates, Docker CE, Compose and Buildx,
   log rotation, node exporter, time synchronization, and bounded Docker cache
   cleanup. Keep the worker's Docker data and caches disposable. Do not use
   the platform `build_server` role unless it has been deliberately generalized
   and validated for this standalone worker.
4. Install the official Tailscale client and start an interactive enrollment
   with `tailscale up --hostname=<host-name> --advertise-tags=tag:build-worker`.
   Complete the browser login as an authorized tailnet administrator. If
   device approval is enabled, stop while the machine shows **Needs approval**
   in the admin console's Machines page; an Owner, Admin, or IT admin must
   approve it. Tailnet Lock is a separate gate: an already trusted signing
   device must sign the new node key. Confirm the machine is approved, signed,
   and online before relying on tailnet access. Do not enable Tailscale SSH
   unless its access policy is reviewed separately.

   This first trial uses the human-approved path so the operator can review
   the new device. The automated enrollment broker is a separate path: it
   issues tagged, pre-authorized keys and therefore does not pause for manual
   device approval. Use that broker only for explicitly unattended enrollment.
5. Add only the Woodpecker agent(s) required by the worker's job labels. Keep
   each agent's token in the fleet secrets service and deliver it through the
   existing server-side loading path. Create agents paused, install the agent
   configuration, and let the load controller open them after health checks.
6. Add the worker to a consumer's Buildx availability pool only if that
   consumer's selector supports the worker's virtualization and can obtain its
   required telemetry, then verify SSH, Docker, CPU, memory, and disk checks.
   Keep all eligibility checks fail-closed; do not relax a selector to force a
   provider-managed KVM guest into a physical-hypervisor pool.
7. Verify a safe pipeline on each assigned Woodpecker plane. If a consumer is
   explicitly configured in a Buildx pool, also run one standalone Buildx build
   through that consumer's selector. Check the active agent IDs,
   load-controller state, disk cleanup timer, and metrics scrape before marking
   the lease `ready`.

For a 16-GiB worker, start with at most two total workflow slots, a 5-GiB
per-step memory limit, and no large-memory label. Route `lv3=true` pipelines
only to the CI plane whose agent advertises that label; keep general fleet
repositories on the general CI plane.

## Sunset

Start the sunset before the provider deadline, with time to handle a failed
drain:

1. Set the lease to `draining` and close every assigned Woodpecker agent to new
   jobs. Remove the worker from Buildx selection.
2. Wait until both CI planes report no active tasks on the worker. Do not stop
   Docker or delete the provider resource while a pipeline is running.
3. Before deleting the Woodpecker agent registrations, add each registration
   ID and physical host to `services-registry/ci-execution-report.json` under
   `agent_id_hosts`. Keep those ID mappings for historical pipeline reports.
   Then delete the registrations, revoke their individual tokens in the fleet
   secrets service, remove their IDs from load-controller configuration, and
   remove their active names from `agent_hosts` once they no longer run jobs.
4. Remove the Buildx worker and its SSH alias, metrics scrape target, dashboards
   or alerts, and any temporary DNS or firewall entries.
5. Remove the Tailscale device and any worker-specific policy entry. Confirm
   that no grants or temporary tag ownership remain.
6. Delete the provider resource. Record the deletion time, final pipeline
   status, and any intentionally retained artifacts in a live-apply receipt.
   Mark the lease `retired` only after the provider confirms deletion.

If a drain cannot complete before expiry, stop new scheduling and preserve the
provider resource until active work is settled or explicitly abandoned. A
provider deadline does not justify silently killing a running build.

## Rollback

If onboarding fails, close any partially created agents, revoke any issued
tokens, remove the Tailscale device, restore the previous pool configuration,
and leave the provider resource reachable for repair. Record each completed
cleanup step in the lease. Do not mark a failed onboarding as ready.
