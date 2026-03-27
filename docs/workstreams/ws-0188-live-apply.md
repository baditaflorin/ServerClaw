# Workstream WS-0188: Failover Rehearsal Gate Live Apply

- ADR: [ADR 0188](../adr/0188-failover-rehearsal-gate-for-redundancy-tiers.md)
- Title: live apply and verification for redundancy-tier rehearsal freshness gating
- Status: live_applied
- Implemented In Repo Version: 0.177.17
- Live Applied In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Live Applied On: 2026-03-27
- Branch: `codex/ws-0188-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-ws-0188-live-apply`
- Owner: codex
- Depends On: `adr-0098-postgres-ha`, `adr-0099-restore-verification`, `adr-0179-service-redundancy-tier-matrix`
- Conflicts With: none
- Shared Surfaces: `config/service-redundancy-catalog.json`, `docs/schema/service-redundancy-catalog.schema.json`, `scripts/service_redundancy.py`, `docs/runbooks/service-redundancy-tier-matrix.md`, `docs/runbooks/postgres-failover.md`, `docs/runbooks/service-capability-catalog.md`, `tests/test_service_redundancy.py`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- extend the machine-readable redundancy catalog with rehearsal freshness policy and proof metadata
- compute declared tier separately from implemented tier so stale or failed rehearsals downgrade status reporting instead of rewriting design intent
- verify the gate against the live production PostgreSQL path from the latest `origin/main`
- record the live evidence, ADR metadata, and branch-local handoff state needed for a safe merge

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema pytest tests/test_service_redundancy.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --service postgres`
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service postgres`
- `./scripts/validate_repo.sh data-models`
- live host verification on `100.64.0.1` confirmed `qm list` contains VM `150` but not `151`
- live guest-agent verification on VM `150` confirmed `postgresql` is active, `patroni` and `keepalived` are inactive, and `/etc/patroni` only contains template inputs instead of a runnable `config.yml`
- live reachability checks from the Proxmox host confirmed `10.10.10.50:5432` is open while the expected VIP `10.10.10.55:5432` is closed

## Outcome

- ADR 0188 is now implemented in repo automation through rehearsal policy defaults, proof-aware status evaluation, and operator-visible declared-versus-implemented tier reporting
- the first live apply proved the new gate is necessary right now: `postgres` still declares `R2`, but the current production evidence only supports `R0` because the standby guest is absent and the Patroni plus VIP path is inactive
- the merged mainline truth now records that downgrade explicitly in receipts, release metadata, and canonical status surfaces without rewriting the underlying design tier

## Mainline Integration

- merged to `main` in repository version `0.177.17`
- no platform version bump was required because the verified live evidence already belongs to platform version `0.130.31`
- a separate follow-up repair workstream is still required to recreate VM `151`, restore Patroni and VIP operation, and record a fresh passing `R2` rehearsal before `postgres` can honestly regain an implemented `R2` claim
