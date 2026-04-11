# Workstream ws-0289-live-apply: Live Apply ADR 0289 From Latest `origin/main`

- ADR: [ADR 0289](../adr/0289-directus-as-the-rest-graphql-data-api-layer-over-postgres.md)
- Title: Deploy Directus on `docker-runtime`, back it with managed Postgres, publish `data.example.com`, and verify REST and GraphQL access end to end
- Status: live_applied
- Included In Repo Version: 0.177.109
- Exact-Main Replay Source Version: 0.177.108
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0289-directus-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0289-directus-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.72
- Observed Platform Baseline During Replay: 0.130.71
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0289-main-release`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0289-main-release`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secrets-injection`, `adr-0086-backup-and-recovery`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0289-live-apply.md`, `docs/adr/0289-directus-as-the-rest-graphql-data-api-layer-over-postgres.md`, `docs/runbooks/configure-directus.md`, `inventory/host_vars/proxmox-host.yml`, `inventory/group_vars/platform.yml`, `roles/directus_postgres/`, `roles/directus_runtime/`, `roles/keycloak_runtime/`, `playbooks/directus.yml`, `playbooks/services/directus.yml`, `config/*catalog*.json`, `Makefile`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/`, `versions/stack.yaml`, `build/platform-manifest.json`, `receipts/ops-portal-snapshot.html`, and `receipts/live-applies/`

## Scope

- replace the placeholder Directus scaffold with a repo-managed Postgres, runtime, Keycloak, bootstrap, and verification implementation
- replay ADR 0289 from the exact `0.177.108` `origin/main` baseline, then carry the protected release and canonical-truth surfaces on top of that mainline proof
- leave a canonical receipt and enough exact-main evidence that the pushed `origin/main` truth is self-contained

## Expected Live Surfaces

- a running Directus stack on `docker-runtime`
- a managed PostgreSQL database and role for Directus on `postgres`
- public publication at `https://data.example.com`
- public REST and GraphQL verification using repo-managed scoped credentials
- Keycloak-backed human sign-in for the Directus operator path

## Ownership Notes

- this workstream owns the Directus runtime, bootstrap automation, and the final exact-main receipt bundle
- `docker-runtime`, `postgres`, and `nginx-edge` are shared live surfaces, so replay must stay narrow and documented
- the protected integration files are now refreshed from the exact-main replay in this release worktree

## Verification

- Release automation is preserved in `receipts/live-applies/evidence/2026-03-30-adr-0289-release-status-r1-0.177.109.txt`, `receipts/live-applies/evidence/2026-03-30-adr-0289-release-dry-run-r1-0.177.109.txt`, and `receipts/live-applies/evidence/2026-03-30-adr-0289-release-write-r1-0.177.109.txt`; the write run cut repository release `0.177.109` from the exact-main `0.177.108` baseline with the ADR 0289 changelog entry.
- The first exact-main converge attempt is preserved in `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-live-apply-r1-0.177.109.txt` and failed only because `quay.io` returned `502 Bad Gateway` while pulling `quay.io/keycloak/keycloak:26.5.4`; the committed retry hardening in the Keycloak runtime role then carried the second replay through successfully.
- The successful exact-main replay is preserved in `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-live-apply-r2-0.177.109.txt` with final recap `docker-runtime : ok=275 changed=3 unreachable=0 failed=0 skipped=87`, `postgres : ok=69 changed=2 unreachable=0 failed=0 skipped=23`, `nginx-edge : ok=40 changed=5 unreachable=0 failed=0 skipped=6`, and `localhost : ok=23 changed=0 unreachable=0 failed=0 skipped=7`.
- Guest-local runtime verification is preserved in `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-compose-ps-r1-0.177.109.txt`, `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-local-health-r1-0.177.109.txt`, and `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-local-ping-r1-0.177.109.txt`; `docker compose ps` shows both `directus` and `directus-openbao-agent` healthy, `curl -fsS http://127.0.0.1:8055/server/health` returned `{"status":"ok"}`, and `curl -fsS http://127.0.0.1:8055/server/ping` returned `pong`.
- Public publication verification is preserved in `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-dns-r1-0.177.109.txt`, `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-public-health-r1-0.177.109.txt`, `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-verify-public-r1-0.177.109.txt`, and `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-mainline-openapi-r1-0.177.109.json`; `data.example.com` resolves to `203.0.113.1`, public health returned `{"status":"ok"}`, and the token-authenticated REST plus GraphQL verification returned `{"status": "ok", "collection": "service_registry", "service_name": "directus", "rest_items": 1, "graphql_items": 1}`.
- The protected exact-main status surfaces were refreshed in `receipts/live-applies/evidence/2026-03-30-adr-0289-generate-adr-index-r1-0.177.109.txt`, `receipts/live-applies/evidence/2026-03-30-adr-0289-generate-status-docs-r1-0.177.109.txt`, `receipts/live-applies/evidence/2026-03-30-adr-0289-generate-platform-manifest-r1-0.177.109.txt`, and `receipts/live-applies/evidence/2026-03-30-adr-0289-generate-ops-portal-r1-0.177.109.txt`, which brought `README.md`, `build/platform-manifest.json`, and `receipts/ops-portal-snapshot.html` onto the exact-main `0.177.109 / 0.130.72` truth.

## Results

- ADR 0289 is now integrated in repository release `0.177.109`.
- The first verified exact-main Directus replay advanced the tracked platform baseline from `0.130.71` to `0.130.72`.
- `receipts/live-applies/2026-03-30-adr-0289-directus-mainline-live-apply.json` is the canonical receipt for the merged-main Directus rollout.
- The committed Keycloak pull retry hardening preserves the successful replay path against transient upstream registry outages that are outside repo control.
- No repo-local merge work remains for ADR 0289 beyond the `origin/main` push of this exact receipt-bearing branch.

## Notes

- A manual Hetzner DNS bridge was required during the brownout window for the legacy DNS write API. The temporary provider-side record was `data.example.com -> 203.0.113.1` with record id `644d501af8a99d37d91f388ac4585349`; later governed replays observed the canonical state.
- The first exact-main replay failure was external to the repo: `quay.io` returned `502 Bad Gateway` during the Keycloak image pull. The committed bounded retry loop preserves the successful replay contract without widening the mutation surface.
