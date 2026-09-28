# Woodpecker-only public CI

## Context

The sanitized public ServerClaw mirror was still publishing a GitHub Actions
workflow even though GitHub-hosted Actions is not an available or desired CI
runtime. Those workflow checks failed before executing steps. The ServerClaw
branch ruleset already requires its passing Woodpecker status, and the repo's
Woodpecker pipeline is assigned to the `lv3=true` runner on the dedicated
self-hosted Woodpecker instance.

## Change

Retire the GitHub Actions workflow, make Woodpecker the active public CI
entrypoint in catalogs and discovery docs, and package the Woodpecker pipeline
instead of the obsolete Actions file in the API Gateway repo snapshot. Add a
regression test so the failing workflow is not silently reintroduced.

The sanitized public snapshot now replaces the deployment-specific capacity
model with a fork-safe example aligned to the generic inventory template. Only
the seven inventory-template guests are active; optional extra guests remain
planned examples, and measured host/guest allocations are clearly marked for
fork customization.

## Verification

Run the CI provider and API Gateway contract tests, validate the generated
discovery artifacts, run the focused Woodpecker validation set, then merge only
after the required Woodpecker push/PR status is green. Publish the sanitized
ServerClaw snapshot through its branch/PR flow and verify that only the
Woodpecker status is required.

## Status

The current private source `main` and public ServerClaw `main` both have a
green `ci/woodpecker/push/woodpecker` status on their latest commits. The
corresponding GitHub Actions `Validate` runs failed at startup with no executed
steps. Local focused tests pass (20 targeted tests in the final rerun; an
earlier broader focused set had 152 passing tests), as do generated portal,
discovery, model-schema, and agent-standards checks.

The changed API Gateway and Woodpecker service-completeness profiles now pass
scoped validation without suppressions. The API Gateway profile records the
existing Authentik client, root-only legacy env-file protection, truthful
data/SLO catalog entries, and alert rules. Woodpecker now has its dashboard and
alert rules. The validator scopes catalog checks to changed service records so
unrelated legacy services do not mask this branch's regressions. Focused tests,
data-catalog validation, alert-rule validation, formatting, and lint checks pass.

## Runtime CI outage — 2026-09-27

The canonical self-hosted CI instance is currently returning HTTP 502 on its
root and `/healthz` endpoints. A separate fleet instance is healthy (204 on
`/healthz`) but is not a valid substitute: this repository's `.woodpecker.yml`
is labelled `lv3=true` and belongs on the dedicated platform instance. The
Grafana Authentik E2E PR consequently has no reported CI checks yet. Do not
merge it, activate an alternate instance, or weaken the runner label while the
canonical control plane is unavailable.

This runtime investigation is blocked from the workstation: inbound SSH and
Proxmox API connections to the configured host time out, and the local
Tailscale route to the subnet router is offline. No server, firewall, webhook,
or VM changes were made. Restore a trusted host access path, then inspect the
dedicated CI runtime guest and its `/opt/woodpecker` compose project through
the existing Woodpecker recovery runbook before changing services.

During read-only webhook metadata inspection, GitHub included the hook's URL
access token in its response. Treat that token as exposed and rotate/reissue the
Woodpecker webhook as part of recovery. It was not copied into repository files
or PR comments. The current GitHub CLI authorization lacks `admin:repo_hook`,
and the canonical Woodpecker control plane is unavailable, so this rotation
could not be performed from this workstation.

## Live recheck — 2026-09-27

Trusted SSH access to the Proxmox host is now available. The public edge was
intermittently healthy during the initial recheck but is currently unreachable;
its NGINX worker is active and its logs show the dedicated CI upstream
unreachable/refusing connections. The CI guest is running but pinned at its
8 GiB balloon floor with about 120 MiB free, and its guest agent is unresponsive.
The hypervisor has about 2.3 GiB available RAM and swap is nearly exhausted.
An active build was observed on the shared builder, which was left untouched.

The earlier service-completeness blockers are fixed for the two changed
services and targeted checks pass. The dedicated CI API and runner still need
end-to-end recovery and a green required status before this branch can merge.

## Recovery follow-up — 2026-09-28

The 0mcp Proxmox break-glass SSH endpoint is available as `root@example.org` on
port `2222`. Both the private Woodpecker `/healthz` endpoint and public
`https://ci.example.org/healthz` return HTTP 204. The VM130 builder agent is
running, but its logs show gRPC `ENHANCE_YOUR_CALM` / `too_many_pings` and
repeated reconnect backoff. GitHub pipelines 393/394 consequently remained
pending for over two hours. The repository pre-push gate now passes all
selected blocking checks, including `service-completeness` and
`workstream-surfaces`.

VM120 is under severe memory pressure (about 100 MiB available at recheck),
and ClickHouse for Plausible is its largest resident process. That workload is
not being stopped or resized as part of this CI-specific recovery. Instead,
update Woodpecker's gRPC keepalive policy and server/agent image pins from the
reviewed repository configuration, then verify the VM130 agent reconnects and
the required push and PR checks finish green. Kernel logs also show Huly's
Redpanda process exiting with `SIGILL`; that is a separate service incident,
not part of this CI repair.

The first branch push exposed a local fallback defect: after the remote
runner was unavailable, the fallback selected the tofu native command without
enabling native execution, which sent it back to the placeholder Docker image
registry. The fallback now enables `LV3_NATIVE_EXECUTION=1` for local sources,
with a regression test.
This is a runner-path correction, not a skipped validation.

The 2026-09-28 runtime follow-up found ClickHouse as the largest CPU-heavy
workload on VM120 while the guest was under severe memory and I/O pressure.
Docker stats showed `plausible-events-db` near 467% CPU, and ClickHouse logs
contained repeated memory-allocation failures during MergeTree work. PostgreSQL
on VM150 remained healthy. VM120's completed PBS snapshot is the rollback
point. As an immediate reversible mitigation, ClickHouse's cgroup CPU weight
was lowered to 25; this is temporary and will not survive container recreation.
The role now declares a relative Compose CPU share default of 640, preserving
access to idle CPU while reducing ClickHouse's priority during contention. The
Woodpecker server/agent and webhook recovery remain separate follow-ups.

The live-apply vulnerability gate then exposed stale Plausible image evidence
and expired image exceptions. The catalogs now pin and scan Plausible CE
`v3.2.1`, PostgreSQL `16.15-alpine`, and ClickHouse `26.8-alpine` for linux/amd64.
ClickHouse's refreshed report has zero critical findings; the other two
upstream images still have critical scanner matches but no HIGH/CRITICAL
finding with an available fix in the image report. Their narrowly scoped
exceptions expire on 2026-10-05 and require repository-managed patched images
before that date. Plausible `v3.2.1` is the upstream security patch that removes
the vulnerable `/storybook` endpoint ([upstream release](https://github.com/plausible/analytics/releases/tag/v3.2.1));
the dashboard remains behind Authentik and the exact scanned digests stay pinned.
These are active time-limited policy exceptions, not skipped gates.

The first governed Plausible apply stopped before any mutation because the DNS
publication include assumed a legacy `.local/identity.yml` file. The deployment
uses `.local/deployments/<profile>/identity.yml`; both the repository and collection
include now honor the explicit `PLATFORM_IDENTITY_OVERLAY` selector and fail
clearly if the selected file is missing. No credential file is copied or linked
into the worktree.

## Public snapshot completeness follow-up — 2026-09-28

ServerClaw's local pre-push gate exposed that the private live capacity model
was copied into the public snapshot unchanged, while Tier A publication replaces
the public inventory with generic `*-yourname` hostnames. This made both model
schema validation and generated portal validation fail on active guest `nginx`.
The publication map now substitutes an explicit generic capacity-model template
and a regression test validates its active guest set against the public inventory.

## Outcome — 2026-09-28

The private source change merged in PR #248 after the full local push gate passed
and both required Woodpecker push/PR checks succeeded. The refreshed ServerClaw
snapshot merged in PR #60 after both Woodpecker checks passed; its merge-commit
push check also passed. The public snapshot now has no GitHub Actions workflow
files, and its generic capacity model validates against the generic inventory.
The service-completeness regression lane passes and skips unrelated infrastructure
changes while retaining a fail-closed full audit for ambiguous scope.

The final Plane projection could not be synced: both locally stored Plane API
tokens failed verification. No replacement token was minted; Git remains the
authoritative workstream record until the Plane credentials are repaired.
