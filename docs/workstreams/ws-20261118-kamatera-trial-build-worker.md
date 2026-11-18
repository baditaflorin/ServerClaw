# WS-20261118: Temporary external build worker onboarding and sunset

## Status

The live onboarding and documentation closeout merged in PR #703. Follow-up
verification on 2026-11-18 confirms that Woodpecker registration 140 is online,
schedulable, and actively executing general CI workflows. In the latest 100
pipelines, its agent identity appeared in 33 pipeline records: 17 succeeded,
12 were marked killed, and 4 were running. One successful pipeline ran only on
Kamatera (`baditaflorin/michael-riedler-pilot-1-pipeline#69`); the other 32
matching records were mixed across physical workers. The report does not
establish why the killed pipelines ended. The agent has a two-workflow/5-GiB-per-step ceiling
and no `lv3` label. Services Registry PRs #1210 and #1211 now map its name and
registration ID to `kamateratmp`, preserving historical attribution after
retirement. The report proves general Woodpecker CI execution, not a separate
Buildx pool build or production image publication.

Buildx pool registration is intentionally omitted. The
`go-url-categorizer-api` selector requires physical Proxmox hypervisor
telemetry, so this provider-managed KVM guest fails its eligibility check.
Woodpecker Docker builds are the supported path for this trial; do not bypass
the Buildx selector. The provider billing cutoff is still unconfirmed. The
private host record contains an operator `expires_at` target, which does not
schedule an alert or retirement. Confirm the provider cutoff and start the
manual sunset before the earlier deadline.

## Goal

Use the 30-day external VM as disposable build and CI execution capacity while
recording a repeatable onboarding and sunset path. Keep it as a direct Debian
worker, not a nested Proxmox host.

## Decisions

- Woodpecker control planes remain where they are; the VM is an agent worker.
- Tailscale uses `tag:build-worker`. This first trial uses interactive human
  authentication, device approval when enabled, and a separate Tailnet Lock
  signature. The current admin group already owns the tag, so this flow needs
  no temporary policy change. The automated enrollment broker uses
  pre-authorized keys and is not used for this human-gated trial.
- The first capacity profile is at most two total workflows with 5-GiB step
  limits and no large-memory label.
- The exact provider identifiers and expiry stay in private runtime state.

## Evidence

- Provider task reports an 8-vCPU, 16-GiB Debian 13 instance with a 150-GB
  disk and a 30-day billing term.
- The live provider dashboard reports server creation `Success`, completed
  at 16:59:50 on 2026-11-17; the earlier `Running`/36% view was stale. The
  inspected server page does not show the billing cutoff. The private host
  record uses an operator target 30 days after that completion time, treating
  the displayed time as Europe/Bucharest; move the target earlier if billing
  confirms an earlier cutoff.
- Read-only SSH confirmed the provider-set hostname, Debian GNU/Linux 13, KVM
  virtualization, and 141 GiB available on the root filesystem.
- On 2026-11-18, the official Tailscale stable installer added the Debian
  `trixie` package source and installed Tailscale 1.104.7. `tailscaled` is
  enabled and active. The user completed browser login and confirmed that the
  device was signed under Tailnet Lock. Current tailnet status shows the node
  online as `tag:build-worker`; a ping from the Mac succeeded. No login URL,
  tailnet address, or key material is stored in this generic workstream record.
- The Fleet-state bootstrap installed Docker CE 29.10.0, Buildx 0.39.0, and
  Compose 5.8.0; `ops` has Docker access and non-interactive sudo. Bounded Docker
  log rotation and the daily seven-day image/cache prune timer are active. The
  Docker API is not exposed on TCP. The bootstrap does not install a monitoring
  agent or register a CI/build worker.
- SSH hardening was verified at 2026-11-18 00:35:03 UTC. `sshd -T` reports only
  the current Tailscale IPv4 listener, `PermitRootLogin no`,
  `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, and
  `AllowUsers ops`; `ss -ltnH` shows only that tailnet listener. SSH, Tailscale,
  Docker, and the prune timer are active, and the `ops` key plus sudo check pass.
- The provider image differed from the assumed SSH layout: active listen, root,
  and password directives were in the main `sshd_config`, and the drop-in
  include was commented. Earlier hardening revisions exposed a temporary-file
  collision and then two recovery-guard errors; each stopped before losing the
  working `ops` path. Fleet-state PRs #759 and #760 fixed marked partial-state
  recovery and empty-directory detection. The merged automation was applied
  successfully and final listener/effective-policy checks passed. The
  provider's original SSH config is preserved for rollback; bootstrap staging
  files were removed from `/root` after verification.
- A read-only comparison found pre-existing drift between the live general
  Woodpecker controller and its private configuration mirror: one active
  builder node was missing from the mirror and several agent names differed.
  The mirror was reconciled in Fleet-state PR #762 before registering the new
  agent. The other CI plane matched. The worker agent is active on the general
  plane and has no `lv3` label; route `lv3=true` work only through its
  designated plane.
- `fleet-host-sunset` PR #37 added and validated optional UTC `expires_at`
  metadata. Fleet-state PR #763 records the active worker, operator sunset
  target, and bounded registration; PR #762 contains the controller-mirror
  reconciliation and fail-closed worker configuration.
- Node exporter 1.9.0 is active only on the tailnet, and the controller-side
  metrics fetch returned HTTP 200. The Woodpecker agent uses a per-agent token
  held by Fleet Secrets; it is not stored in this repository.
- On 2026-11-18 at 07:29:46 UTC, the `ci.0exec.com` agent API reported
  registration 140 with a current contact, `no_schedule=false`, Docker backend,
  and capacity 2. Its container was healthy; Tailscale, Docker, and node exporter
  were active, and the root filesystem had 134 GiB free.
- A live `ci-execution-report` query on CT108 verified the `WOODPECKER_HOST`
  points to `ci.0exec.com`. Among the latest 100 pipelines ending at
  2026-11-18 07:29:27 UTC, 33 included the Kamatera agent: 17 succeeded, 12 were
  marked killed, and 4 were running. The one single-host success was
  `baditaflorin/michael-riedler-pilot-1-pipeline#69`. All 12 killed records were
  `go-url-categorizer-api` push or pull-request events; their cause was not
  investigated. The 32 remaining matching pipelines were classified as mixed
  because workflows also ran on other physical workers.
- The initial live execution-report configuration had two attribution drifts:
  it classified registration 98 and its historical pve01-named agent as `pve01`,
  while the source runbook assigns that worker to CT108 (`0docker`). After
  Services Registry PR #1210, the CT108 report configuration was atomically
  aligned with the merged source and the stale classifications were corrected.
  PR #1211 then added registration ID 140 so historical runs remain attributed
  after the worker is retired. The final configuration from merged Services
  Registry commit `b506fac095918c38607545a79dbea5aaccfbc76a` was applied
  atomically to CT108; backups of both prior configurations are kept there
  under `/root/ci-execution-report-config.before-kamateratmp-*.json`.
- The successful pipeline evidence is for general Woodpecker CI only. The
  provider-managed KVM host remains excluded from the project's specialized
  Buildx client pool, and no production image publication has been verified.
- The project's remote Buildx selector requires live memory telemetry from a
  physical Proxmox hypervisor. The provider VM is KVM and therefore fails the
  selector's fail-closed virtualization check. The trial is deliberately not
  added to that pool; use the Woodpecker Docker agent for its build jobs.
- The provider's billing cutoff is not visible in the inspected dashboard.
  `fleet-state` records the 30-day operator sunset target in `expires_at`, but
  the field is metadata only and creates no alert or automatic retirement.
- The existing PFS `docker_runtime` and `build_server` roles are not generic
  standalone-worker automation: they assume managed platform guest topology,
  publication wiring, and the shared build-cache host's apt-cacher/registry
  setup. This gap is recorded; do not apply those roles to the external lease
  unchanged. Host-specific bootstrap belongs under private
  `fleet-state/hosts/<name>/`.
- The generated README platform snapshot still reports an observed check date
  of 2026-04-03. This trial did not include a full platform audit, so that
  snapshot was not refreshed and must not be read as current fleet-wide
  verification.
- The initial onboarding change merged in PFS PR #702. Its focused ownership,
  agent-standard, generated-document, topology, and whitespace checks passed.
  The full YAML gate reported pre-existing indentation and blank-line findings
  in files outside this workstream, including a network-policy file owned by
  another workstream. Those findings were left untouched; they are not evidence
  that this follow-up branch has passed its own validation.

## Scope

- `docs/adr/0496-temporary-external-build-worker-lifecycle.md`
- `docs/runbooks/temporary-build-worker.md`
- `workstreams/active/ws-20261118-kamatera-trial-build-worker.yaml`
- `receipts/live-applies/ws-20261118-kamatera-trial-build-worker-apply-receipt.yaml`

## Handoff

No Tailscale approval is pending: login and Tailnet Lock signing are complete.
The direct Debian baseline, tailnet-only SSH, monitoring scrape, and general
Woodpecker agent are active; successful general CI use is now verified. Confirm
the provider billing cutoff, then drain and retire the worker before the earlier
of that cutoff and the operator target in the private host record. Preserve the
agent ID mapping for historical CI attribution when retiring it. No Proxmox or
project-specific Buildx pool registration is part of this trial.
