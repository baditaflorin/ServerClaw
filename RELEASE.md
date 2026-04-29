# Release 0.179.31

- Date: 2026-04-29

## Summary
- ADR 0465 + ws-0465: Phase 9 self-running automation primitives. Four CPU-only swaps that take LLM round-trips out of the loop: `scripts/doctor.py --snapshot` writes `build/doctor-snapshot.json` (cached view agents read instead of re-running 9 probes); new `probe_doctor_snapshot_freshness` reports cache-vs-HEAD staleness. `scripts/apply_promotion.py` consumes `promotion_tracker --json` and rewrites `validate_repo.sh` advisory→required for ALLOWED_GATES. `scripts/doctor_regression_watch.py` diffs live doctor against the latest baseline under `receipts/doctor-baselines/` (exit 1 on regression). Two committed Windmill schedule templates: hourly regression watcher + daily `make heal --apply`. `make doctor` now surfaces 10 signals (was 9). 63 new tests.
- ADR 0460 + ws-0460: Phase 8 cross-deploy doctor + advisory auto-promotion. `scripts/promotion_tracker.py` classifies gates as eligible/streaking/unstable/promoted from `receipts/gate-runs/<gate>/*.yaml`. `scripts/cross_deployment_doctor.py` reads `.local/deployments/<slug>/state/` and reports per-receipt presence/skew drift. Both wired into `make doctor` (now 9 signals, still 1/9 non-zero). 38 new tests.
- Fix education_wemeshup API routing: add Traefik dynamic config to route `/api/` to `catalog-api` backend; add `coolify_traefik_extra_dynamic_configs` for persistent IaC
- ADR 0456 + ws-0456: deployment-aware certificate validation. `scripts/certificate_validator.py --deployment <slug>` reads identity from `.local/deployments/<slug>/identity.yml`. New `cross_deployment_drift` reason code in `config/gate-bypass-waiver-catalog.json`. 11 new tests. Closes follow-up #2 from the ws-0448 postmortem.
- ADR 0457 + ws-0457: host-pinning Phase 1. New optional `deployment_owner` field on `proxmox_guests[*]` in the deployment-v1 topology schema. New `scripts/host_pinning_check.py` audit primitive (`--all`, `--host`, `--cross`, `--json`). Closes Slice D from the ws-0448 postmortem (lv3 ↔ 0fork `oauth2-proxy@4180` port-collision class of bug). 12 new tests. Phase 2 (role-side enforcement) deferred.
- ws-0458: wire ADR 0457 audit into `scripts/validate_repo.sh` as advisory `host-pinning` lane. Promotes the audit from operator-on-demand to pre-push-gate visibility; skips silently when `.local/deployments/` is absent.
- ADR 0457 Phase 2 + ws-0459: role-side enforcement. New `lv3.platform.host_pinning_guard` role refuses converge when the host's `deployment_owner` mismatches the active deployment slug. Wired into `playbooks/public-edge.yml`. Closes the `oauth2-proxy@4180` collision class of bug at converge time. 9 new tests.
- ws-0460: sweep host_pinning_guard across every service playbook by including it in the shared `playbooks/tasks/preflight.yml` surface. 52 service playbooks (ops-portal, keycloak, gitea, mail-platform, openbao, dify, etc.) inherit the guard automatically. Single edit; opt-out via `host_pinning_guard_skip_in_preflight: true`.
- ADR 0452 + ws-0452: Phase 7 drives doctor signals from 3/7 → 1/7
- ADR 0451 + ws-0451: Phase 6 self-healing actions. Three primitives
- ADR 0450 + ws-0450: Phase 5 self-healing aggregator + post-merge
- ADR 0449 + ws-0449: Phase 4 self-healing primitives. Three new
- ADR 0458 + ws-0461: cert validator multi-deployment auto-detect. New `--all-deployments` flag walks every slug; auto-triggers when no slug passed AND multiple deployments exist. The pre-push gate's all-lane runner now covers every deployment in a multi-deployment install. 6 new tests.
- ADR 0459 + ws-0462: deployment lifecycle CLI parity. New `use`/`new`/`bind` subcommands on `scripts/deployment.py` mirror the existing `make use-deployment`/`make new-deployment`/`make bind-worktree` targets so agents and scripts can drive the deployment lifecycle programmatically without shelling out to Make. 9 new tests.
- ADR 0461 + ws-0463: atomic receipt write + dangling-receipt gate flag. `write_receipt_atomic()` helper eliminates half-written receipts on crash. `--check-files` detects `latest_receipts` entries with no matching `receipts/live-applies/<slug>.json` file — closes the PR #71 dangling-receipt class of bug. Live signal: 2 pre-existing dangling receipts surfaced (preview_environment, staging_environment). 10 new tests.
- ADR 0462 + ws-0464: topology pre-commit schema hook. `scripts/validate_topology_schema.py` + `validate-topology-schema` pre-commit hook reject malformed `proxmox_guests` topology at commit time (the 2026-04-28 class of bug ws-0448's runtime auto-fill papered over). 11 new tests.
- ADR 0463 + ws-0466: post-converge / on-demand health-probe runner. `scripts/run_health_probes.py` reads `catalog/services/<svc>/service.yaml::health.liveness` and runs HTTP/TCP probes, writing per-probe receipts to `receipts/health-probes/`. Closes the "converge succeeded but the service didn't actually come up" class of bug. 8 new tests.
- ADR 0464 + ws-0467: SSH retry with backoff + failure classification. `scripts/ssh_with_retry.py` retries ssh up to N times with exponential backoff + jitter, classifies stderr into 7 failure types, and writes receipts to `receipts/ssh-failures/`. 21 new tests.
- ws-0465: regression test that locks in the ws-0460 host_pinning_guard sweep. Catches the "someone refactored shared preflight" class of bug. 10 new tests; no code change.

## Platform Impact
- no live platform version bump; this release updates repository automation, release metadata, and operator tooling only

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
