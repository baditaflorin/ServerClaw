# Kamatera shared build-pool expansion

## Objective

Extend the temporary worker from general Woodpecker execution to the shared
fleet image-build pool and the GoURL project Buildx pool, while retaining live
capacity admission and making the 30-day sunset target effective for new work.

## Current live state

- The VM is a provider-managed Debian 13 KVM guest with 8 vCPU, 16 GiB RAM, and
  a 150 GB root disk. It is not a Proxmox host or managed Proxmox guest.
- The SSH host key was checked against Tailscale's signed device fingerprint:
  `SHA256:N/Sbii1MvUIpSuAFLysG/c2AC8Fjr2PWSPxt4rhcCt8`. The key fetched over
  the tailnet address matched. It is pinned on the Mac; CT108 already had the
  same ED25519 key pinned under its configured `HostKeyAlias`. CT108's `ops`
  SSH login and Docker server version were verified over its managed Tailscale
  SOCKS route.
- A `ci.0exec.com` Woodpecker Docker agent is online with capacity two and
  per-step memory limits. It is general CI capacity and does not carry `lv3`.
- The canonical `fleet-state/builder-pool.json` record is live on CT108 with
  Buildx name `kamateratmp-amd64`, a one-build lease cap, and
  `expires_at: 2026-12-17T14:59:50Z`. Fleet Runner reports it enabled,
  reachable, eligible, and admissible. The applied file came from canonical
  `fleet-state`; its previous live copy is at
  `/root/fleet-state/builder-pool.json.bak-pre-kamateratmp-20261118T`.
- GoURL merged guest-scoped Buildx admission in PR #4339
  (`91eeb2fae9e6ff8d83ffbd47b6b7509c97c1bf38`), preserving physical-host
  checks for `hypervisor` rows. Its current `origin/main` inventory contains
  the Kamateratmp guest row. On CT108, the documented setup script created
  Docker context `kamateratmp-amd64-ctx` and Buildx builder
  `kamateratmp-amd64`. The live GoURL status reports the guest eligible with
  5,120 MiB required memory; a `FROM scratch` cache-only build passed through
  the GoURL selector with only Kamateratmp eligible.
- The separate sitemap-finder selector does not use the central build lease
  ledger. It remains excluded until it can share admission safely.
- The host record has an owner-directed expiry target of
  `2026-12-17T14:59:50Z`. The provider billing cutoff remains unconfirmed.
- GoURL's project selector will observe central Fleet Runner leases and guest
  telemetry, but it does not create a Fleet Runner lease for its own builds.
  Keep GoURL builds serialized with Fleet Runner and Woodpecker work on the
  guest until a shared external lease API exists.
- Initial Fleet Runner thresholds were `3.0` load/CPU and 10,240 MiB free disk
  because `/root/.fleet-runner.env` overrode source defaults. The binary's
  self-update check confirmed source SHA
  `4da231cc4dc96cf523beee45441a3fd2ae0c68ee`; the two non-secret overrides are
  now `1.0` and 20,000 MiB. Live status confirms those thresholds and still
  admits Kamateratmp. The 0mcp Buildx worker is below the new disk floor at the
  latest sample (19,036 MiB) and is excluded. GoURL's own selector defaults to
  10,240 MiB, but its mandatory central Fleet Runner admission now enforces
  20,000 MiB on CT108.
- The PFS repository currently has two ADR files numbered `0496`: the
  temporary-worker lifecycle ADR and the Tailscale endpoint-filter ADR. The
  generated index includes both. This workstream records the collision but
  leaves historical ADR renumbering for a separate reference-cleanup change.

## Implementation plan

1. Fleet Runner's optional UTC expiry is merged and its reader is live. Expired
   workers are excluded before SSH or Buildx probes; malformed values fail
   closed.
2. Kamateratmp is in Fleet Runner with one leased build at a time and the
   host-record expiry target. GoURL's guest-scoped telemetry and reservation
   checks are merged; its physical-hypervisor checks remain intact.
3. The same UTC deadline is in the Woodpecker controller's node policy. At
   expiry, the controller must close the worker to new pipelines, overriding
   normal minimum-open-slot rules while leaving already-running jobs to finish.
   Applied the canonical `2026-12-17T14:59:50Z` deadline to the live
   `ci.0exec.com` controller config on 2026-11-18 and restarted the controller;
   the live expiry guard is now in effect.
4. The SSH identity is verified and pinned, and the dedicated Buildx builder
   is configured on CT108. The central Fleet Runner and GoURL selectors pass;
   a cache-only Buildx canary succeeded without publishing an image.
5. Refresh this repo's ADR, runbook, and live-apply receipt with exact merge,
   registration, capacity, expiry, and pipeline evidence. Keep the trial in
   `active` until the provider resource is actually deleted.

## Safety and validation gates

- No `lv3=true` workflow is assigned to `ci.0exec.com`; those repositories
  belong to `ci.example.org`.
- Fleet Runner's leased worker cap is one. GoURL must consume the same central
  reservations and fail closed on missing, stale, expired, or fully reserved
  policy.
- Existing physical-host selectors remain unchanged unless the inventory row
  explicitly declares guest-scoped admission. Guest-scoped workers still need
  live CPU, memory, disk, I/O, endpoint identity, central lease, and expiry
  checks.
- No production image is published as a canary. The Buildx canary uses
  `FROM scratch` and cache-only output.
- The owner-directed expiry is an enforcement target, not proof of provider
  billing cutoff. Confirm provider billing and move the deadline earlier if
  necessary.

## Completion evidence

- Repository PRs and merged commit SHAs: GoURL #4339 merged at
  `91eeb2fae9e6ff8d83ffbd47b6b7509c97c1bf38`; Fleet Runner #1044 is live at
  `4da231cc` (v0.7.776); services-registry #1212 and fleet-state #766 are
  merged. PFS #705 merged to `main` at
  `b1d5571dca1b26c1980f03f589444229f93be8c0`.
- Host identity: the Tailscale fingerprint matched the SSH key. The Mac pins
  the tailnet address; CT108's existing `HostKeyAlias` pin was verified.
- Fleet Runner: live policy has Kamateratmp with `max_builds: 1` and the
  canonical expiry. Live thresholds are `1.0` load/CPU and 20,000 MiB disk.
  The worker is enabled, eligible, and admissible with about 14.7 GiB
  available memory and 131 GiB free disk at the last sample. The 0mcp worker
  was excluded because it had 19,036 MiB free disk.
- GoURL: `make remote-build-pool-status JSON=1` reports the Kamateratmp row as
  `guest` and eligible. On CT108, the automatic selector chose
  `kamateratmp-amd64` when other rows were excluded for this canary. A
  `FROM scratch` build with `--output type=cacheonly` completed; no image was
  pushed. Other inventory rows were unavailable on this client at the sample,
  so they are not counted as verified fallback capacity.
- Woodpecker: registration 140 remains online and ready to poll with two
  workflow slots. The live controller config now has the canonical expiry;
  an isolated past-deadline dry run proposed draining agent 140 with
  `apply=false`, and post-restart logs show fresh heartbeat, healthy metrics,
  and no drain proposal. The 2026-11-18 execution report recorded 17 successes
  among 33 pipeline records mentioning the agent, including one successful
  pipeline entirely on Kamateratmp.
- Expiry guard validation: installed controller source matches current
  services-registry source hash `da561878...`; expired-deadline dry run passed
  without applying changes; live controller restarted at 2026-11-18 12:37:51Z.
- Provider billing cutoff confirmation: unconfirmed; the recorded deadline is
  the operator sunset target.
- Woodpecker remains general `ci.0exec.com` capacity only; agent 140 has no
  `lv3` label. The cache-only canary proves standalone Buildx admission and
  does not publish a production image.
- Receipt path:
  `receipts/live-applies/ws-20261118-kamateratmp-build-pool-expansion-apply-receipt.yaml`
- Release integration: the repo remains at version `0.179.65`. On 2026-11-18,
  `release_manager.py status` reported 105 release blockers, including 12
  expired pre-existing waiver failures. The release manager refuses a version
  cut while these blockers remain, so this patch stays pending in the
  workstream's canonical release entry. No platform-version bump applies.
