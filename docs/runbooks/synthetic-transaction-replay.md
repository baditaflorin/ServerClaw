# Synthetic Transaction Replay

ADR 0190 adds a privacy-safe replay harness for capacity, recovery, and failover validation. The first live target is the restored `docker-runtime-lv3` rehearsal path used by ADR 0099.

## Entry Points

- standalone dry run: `make synthetic-transaction-replay SYNTHETIC_REPLAY_ARGS='--target restore-docker-runtime --dry-run'`
- standalone execution: `make synthetic-transaction-replay SYNTHETIC_REPLAY_ARGS='--target restore-docker-runtime --print-report-json'`
- governed recovery path: `make restore-verification`
- catalog: `config/synthetic-transaction-catalog.json`

## Current Target

`restore-docker-runtime` replays representative control-plane reads against the isolated restored guest after boot and warm-up complete:

- Keycloak OIDC discovery
- NetBox login page render
- Windmill API version
- OpenBao active-health probe as a non-blocking observation

Each scenario runs multiple times so the report captures request success rate and a latency distribution instead of a single yes or no probe.

## Verification

- `python3 scripts/synthetic_transaction_replay.py --target restore-docker-runtime --dry-run`
- `uv run --with pytest --with pyyaml pytest tests/test_synthetic_transaction_replay.py -q`

## Recovery Integration

`scripts/restore_verification.py` now runs this replay automatically for the restored `docker-runtime-lv3` guest after the smoke suite passes SSH readiness and warm-up.

The restore-verification receipt records:

- per-scenario success counts and per-request observations
- aggregate success rate and latency distribution
- queue or backlog status when a target profile declares one
- the validation window description for the replayed recovery target
