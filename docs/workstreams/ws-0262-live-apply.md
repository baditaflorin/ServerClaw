# Workstream ws-0262-live-apply: ADR 0262 Live Apply From Latest `origin/main`

- ADR: [ADR 0262](../adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md)
- Title: OpenFGA and Keycloak delegated authorization live apply from latest `origin/main`
- Status: `live_applied`
- Branch: `codex/ws-0262-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0262-main-merge`
- Owner: codex
- Included In Repo Version: 0.177.95
- Platform Version Before Exact-Main Replay: 0.130.62
- Live Applied In Platform Version: 0.130.63
- Live Applied On: 2026-03-30
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0262-openfga-keycloak-mainline-live-apply.json`
- Depends On: `adr-0056-keycloak-for-operator-and-agent-sso`, `adr-0043-openbao-for-secrets-transit-and-dynamic-credentials`, `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`
- Conflicts With: none

## Purpose

Carry ADR 0262 onto the newest available `origin/main`, refresh the protected
release and platform-truth surfaces from that synchronized baseline, replay the
delegated-authorization stack from the exact merged tree, and record the
canonical mainline receipt that makes the earlier branch-local proof
authoritative on `main`.

## Exact-Main Replay

- `git fetch origin --prune` confirmed the newest available baseline for the
  final replay remained `origin/main` commit
  `626c1a76b920c12f977b3edc031862cbd22376e8`, which already carried release
  `0.177.94` and platform version `0.130.62`.
- `e192b74456edaf759c1bcb9d0db9912d48289ab4` refreshed the ADR 0262 work onto
  that latest mainline baseline, and `3ba87344f15a5bd2cecba546dfc6b66de7620f43`
  cut the synchronized release `0.177.95`.
- `a6d327e73c210137b0f6ede8e202b560d3335ebc` restored the
  `serverclaw-runtime` Keycloak client contract that drifted during the
  latest-main merge and became the authoritative source commit for the exact-
  main replay.
- The earlier branch-local receipt
  `receipts/live-applies/2026-03-29-adr-0262-openfga-keycloak-live-apply.json`
  remains preserved as the first proof, but it is superseded by the
  2026-03-30 mainline receipt because `origin/main` advanced after that first
  replay.

## Verification

- `make converge-mail-platform env=production` completed successfully from the
  synchronized tree with final recap
  `docker-runtime-lv3 ok=190 changed=8 failed=0 skipped=36`,
  `monitoring-lv3 ok=154 changed=0 failed=0 skipped=20`, and
  `proxmox_florin ok=73 changed=0 failed=0 skipped=33`.
- `make converge-keycloak env=production` completed successfully with final
  recap `docker-runtime-lv3 ok=175 changed=0 failed=0 skipped=38`,
  `monitoring-lv3 ok=17 changed=0 failed=0 skipped=1`,
  `nginx-lv3 ok=39 changed=3 failed=0 skipped=7`,
  `postgres-lv3 ok=51 changed=0 failed=0 skipped=14`, and
  `proxmox_florin ok=219 changed=0 failed=0 skipped=105`.
- `make converge-openfga env=production` completed successfully with final
  recap `docker-runtime-lv3 ok=256 changed=5 failed=0 skipped=69`,
  `localhost ok=2 changed=1 failed=0`,
  `postgres-lv3 ok=51 changed=0 failed=0 skipped=14`, and
  `proxmox_florin ok=41 changed=4 failed=0 skipped=16`.
- `make converge-api-gateway env=production` completed successfully with final
  recap `docker-runtime-lv3 ok=285 changed=111 failed=0 skipped=39`.
- Direct verification after the replay confirmed
  `http://100.64.0.1:8014/stores` still returned the delegated authorization
  store `serverclaw-authz`, and
  `python3 scripts/serverclaw_authz.py verify --config config/serverclaw-authz/bootstrap.json --openfga-url http://100.64.0.1:8014 --openfga-preshared-key-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openfga/preshared-key.txt --keycloak-url http://10.10.10.20:8091`
  returned `verification_passed: true` with the declared principals, tuples,
  and checks satisfied.
- Public and authenticated gateway verification also passed: `curl -fsS
  https://api.lv3.org/healthz` returned `{"status":"ok"}`,
  `https://api.lv3.org/v1/platform/services` listed the `openfga` service with
  `gateway_prefix: /v1/openfga`, and `https://api.lv3.org/v1/openfga/healthz`
  returned the canonical `AUTH_INSUFFICIENT_ROLE` envelope with `HTTP_STATUS=403`
  for the `lv3-agent-hub` bearer token, proving the route is live and
  correctly role-gated.

## Outcome

- ADR 0262 is now implemented on integrated repo version `0.177.95` and live
  platform version `0.130.63`.
- `receipts/live-applies/2026-03-30-adr-0262-openfga-keycloak-mainline-live-apply.json`
  is the canonical exact-main proof for the private OpenFGA runtime, the
  repo-managed Keycloak runtime clients used by delegated authorization, and
  the shared API gateway publication of `/v1/openfga`.
- No additional merge-to-main work remains for ADR 0262; this document is the
  audit trail for the synchronized replay that landed on `main`.
