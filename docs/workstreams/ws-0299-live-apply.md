# Workstream ws-0299-live-apply: Live Apply ADR 0299 From Latest `origin/main`

- ADR: [ADR 0299](../adr/0299-ntfy-as-the-self-hosted-push-notification-channel-for-programmatic-alert-delivery.md)
- Title: Live apply ntfy as the self-hosted push notification channel from the latest realistic `origin/main`
- Status: merged
- Included In Repo Version: 0.177.152
- Branch-Local Evidence: `receipts/live-applies/evidence/2026-04-03-ws-0299-branch-verification.txt`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-03-adr-0299-ntfy-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.95
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Exact-Main Replay Baseline: repo `0.177.151`, platform `0.130.94`
- Workstream Branch: `codex/ws-0299-live-apply`
- Integrated Branch: `main`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0299-live-apply`
- Owner: codex
- Depends On: `adr-0043-openbao-for-platform-secrets-and-dynamic-credentials`, `adr-0068-container-image-publication-and-pinning-policy`, `adr-0077-compose-runtime-secret-injection`, `adr-0087-repository-validation-gate`, `adr-0095-edge-ingress-and-publication-model`, `adr-0172-watchdog-escalation-and-stale-job-self-healing`, `adr-0204-self-correcting-automation-loops`, `adr-0276-nats-jetstream-as-the-platform-event-bus`, `adr-0280-changedetection-io-for-external-content-and-api-change-monitoring`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0299-live-apply.md`, `docs/adr/0299-ntfy-as-the-self-hosted-push-notification-channel-for-programmatic-alert-delivery.md`, `docs/runbooks/configure-ntfy.md`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `scripts/ntfy_publish.py`, `scripts/restic_config_backup.py`, `tests/test_ntfy_publish.py`, `tests/test_restic_config_backup.py`, `receipts/live-applies/2026-04-03-adr-0299-ntfy-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-03-adr-0299-*`, `receipts/live-applies/evidence/2026-04-03-ws-0299-*`, `receipts/restic-backups/20260403T080214Z.json`, `receipts/restic-snapshots-latest.json`, `receipts/sbom/host-docker-runtime-2026-04-03.cdx.json`

## Scope

- promote ntfy from the private paging gateway into the governed public `ntfy.example.com` push surface described by ADR 0299
- wire the topic registry, credential contracts, edge publication, OpenBao seeding, and downstream publishers onto the governed ntfy contract
- prove both the direct ntfy converge path and the generic `live-apply-service` path from the latest realistic `origin/main`
- leave exact-main receipts, validation evidence, and merge-safe metadata behind for the canonical repository history

## Non-Goals

- rewriting unrelated release-manager integrations beyond the bounded evidence recorded here
- hiding shared wrapper failures behind a false-green service receipt
- rewriting the broader immutable-guest live-apply policy for `edge_and_stateful` services

## Ownership Notes

- this workstream owns the ADR 0299 implementation surfaces, the ntfy topic and token contract updates, and the exact-main replay evidence
- the protected release and canonical-truth files were intentionally deferred until the exact-main integration step, then written on `main` as repository version `0.177.152` and platform version `0.130.95`
- the `live-apply-service` wrapper for `ntfy` legitimately requires `ALLOW_IN_PLACE_MUTATION=true` because the service remains classified as `edge_and_stateful`; the blocked run is preserved as evidence rather than bypassed silently
- the post-live-apply restic backup hook exposed a real contract bug on exact main: the backup script required `ntfy_token` even for `--live-apply-trigger` runs that never emit ntfy notifications; this workstream fixed that bug and reran the wrapper to green

## Branch-Local Verification

- `make converge-ntfy env=production` completed successfully from the rebased latest-main worktree and the controller-side `https://ntfy.example.com/v1/health` verification passed
- the live host config at `/opt/ntfy/server.yml` confirmed the governed auth contract, including the expected users, bearer tokens, and ACLs for the Ansible, Gitea Actions, and Windmill publishers
- the governed public publish path accepted a direct POST to `https://ntfy.example.com/platform-ansible-info` with the Ansible token
- `uv run python3 scripts/ntfy_publish.py --publisher ansible --topic platform-ansible-info ... --sequence-id ws-0299:latest-main:verify ...` succeeded end to end after normalizing logical sequence IDs into ntfy-safe values, preserved in `receipts/live-applies/evidence/2026-04-03-ws-0299-branch-verification.txt`

## Exact-Main Verification

- `receipts/live-applies/evidence/2026-04-03-adr-0299-mainline-release-manager-r1-0.177.152.txt` shows the protected-surface cut to repository version `0.177.152`; the repo-local write succeeded, but the external Outline sync returned `502`, so the evidence preserves that external dependency failure instead of pretending the first run was clean
- `receipts/live-applies/evidence/2026-04-03-adr-0299-mainline-release-manager-r2-0.177.152.txt` confirms the rerun with `LV3_SKIP_OUTLINE_SYNC=1` found no remaining `Unreleased` bullets because the first run had already consumed the release state correctly
- `receipts/live-applies/evidence/2026-04-03-adr-0299-mainline-live-apply-r1-0.177.152.txt` records the intentional exact-main guardrail: `make live-apply-service service=ntfy env=production` stopped at the immutable-guest policy because `ntfy` is classified as `edge_and_stateful`
- `receipts/live-applies/evidence/2026-04-03-adr-0299-mainline-live-apply-r2-0.177.152.txt` records the next exact-main failure after the in-place mutation exception: the ntfy converge and public health checks passed, but the shared post-run restic hook failed because the runtime credential payload was missing `ntfy_token`
- this workstream then narrowed the restic contract so `scripts/restic_config_backup.py` still requires `ntfy_token` for scheduled backup runs but does not fail `--live-apply-trigger` backups before any ntfy notification path is even reachable; the focused guardrail tests are preserved in `tests/test_restic_config_backup.py`
- `receipts/live-applies/evidence/2026-04-03-adr-0299-mainline-live-apply-r3-0.177.152.txt` is the final exact-main green replay: `docker-runtime : ok=110 changed=2 failed=0`, `localhost : ok=19 changed=0 failed=0`, `nginx-edge : ok=49 changed=5 failed=0`, the public `https://ntfy.example.com/v1/health` probe passed, and the post-run restic hook returned `status: ok`
- the successful exact-main wrapper synced `receipts/restic-backups/20260403T080214Z.json` and refreshed `receipts/restic-snapshots-latest.json`, with the live-apply-trigger backup protecting the governed `config` and `versions_stack` sources while explicitly keeping `falco_overrides` inactive because that optional source is not present on `docker-runtime`

## Exact-Main Validation

- after the workstream/ADR metadata refresh, receipt creation, and generator reruns, the exact-main tree reran the focused ntfy and restic tests plus the repository validation bundle before the `main` push
- the canonical mainline receipt records the final successful validation suite, including the focused pytest replay, repository data-model validation, live-apply receipt validation, workstream-surface and agent-standard validation, generated-doc refresh, pre-push validation, and `git diff --check`
- `make pre-push-gate` finished green on the completed exact-main tree while preserving one shared remote-builder quirk: the remote Atlas lane timed out reaching its disposable PostgreSQL dev database, then the gate reran the unresolved `atlas-lint` check locally and merged that passing fallback result into the final gate status

## Final Notes

- ADR 0299 is now the canonical ntfy contract on `main` at repository version `0.177.152` and platform version `0.130.95`
- the remaining non-green evidence in this workstream is external and intentionally preserved: the first release-manager run hit an Outline `502`, but the protected repository surfaces were already written correctly and the exact-main service replay itself is now green
- `receipts/live-applies/2026-04-03-adr-0299-ntfy-mainline-live-apply.json` is the canonical proof for this live apply
