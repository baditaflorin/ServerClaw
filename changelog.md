# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- ADR 0473 + ws-0474: Phase 11 ships four CPU-only automation primitives that take LLM round-trips out of routine view-rendering. `scripts/generate_service_cards.py` writes one Markdown card per service to `build/service-cards/<svc>.md` (78 services). `scripts/build_workstream_db.py` indexes `workstreams.yaml` into `build/workstreams.sqlite3` so agents query "what's in flight for service X" in 50 ms instead of parsing 2.7 MB of YAML. `scripts/generate_pr_body.py` drafts the five recurring sections of a release PR from real artifacts. `scripts/generate_context_packs.py` materialises `build/context-packs/<ws-id>.md` per active workstream — cold-start agents read one file. New `make refresh-cpu-views` umbrella target. 61 new tests.
- ADR 0472 + ws-0473: Phase 10 fixes the ADR-collision loop that hit Phase 9 four times. `make reserve-adr-pr reason="<X>"` opens a tiny single-commit reservation PR + auto-merges it; the number is canonical on origin/main within seconds. `scripts/validate_adr_reservation.py` rejects PRs adding an unreserved ADR (advisory through rollout). `scripts/reserve_adr.py --release N` clears the entry once the ADR lands. 38 new tests.
- ADR 0470 + ws-0472: per-deployment fixture inventory + matrix CI. Three synthetic deployments (`minimal` / `multi-host` / `host-pinned`) under `tests/fixtures/deployments/<slug>/` exercise every deployment-v1 contract (`identity.yml` + `topology.yml` + `profile.yml` + `connection.yml`). Parametrised matrix asserts schema validity and cross-file invariants (CIDR membership, unique vmids). Closes the "schema bump breaks deployment X but unit tests still pass" regression class. 28 new tests. Concludes the 2026-04-29 reliability-improvement sweep (10 of 10 landed).
- ADR 0469 + ws-0471: connection.yml SSH key pull from OpenBao. `proxmox_host.key` and `guest_ssh.key` in `.local/deployments/<slug>/connection.yml` now accept `{vault: <path>, field?: <name>}` in addition to a literal path string. `_materialize_vault_key()` shells `openbao read -field` and writes the secret to a mode-0600 tempfile for the duration of the SSH command. Closes the "ship every operator a private-key file" friction in the multi-deployment bootstrap path. Schema enforces `additionalProperties: false` on the dict form so typos fail at validation. 11 new tests.
- ADR 0465 + ws-0465: Phase 9 self-running automation primitives. Four CPU-only swaps that take LLM round-trips out of the loop: `scripts/doctor.py --snapshot` writes `build/doctor-snapshot.json` (cached view agents read instead of re-running 9 probes); new `probe_doctor_snapshot_freshness` reports cache-vs-HEAD staleness. `scripts/apply_promotion.py` consumes `promotion_tracker --json` and rewrites `validate_repo.sh` advisory→required for ALLOWED_GATES. `scripts/doctor_regression_watch.py` diffs live doctor against the latest baseline under `receipts/doctor-baselines/` (exit 1 on regression). Two committed Windmill schedule templates: hourly regression watcher + daily `make heal --apply`. `make doctor` now surfaces 10 signals (was 9). 63 new tests.
- ADR 0460 + ws-0460: Phase 8 cross-deploy doctor + advisory auto-promotion. `scripts/promotion_tracker.py` classifies gates as eligible/streaking/unstable/promoted from `receipts/gate-runs/<gate>/*.yaml`. `scripts/cross_deployment_doctor.py` reads `.local/deployments/<slug>/state/` and reports per-receipt presence/skew drift. Both wired into `make doctor` (now 9 signals, still 1/9 non-zero). 38 new tests.

- Fix education_wemeshup API routing: add Traefik dynamic config to route `/api/` to `catalog-api` backend; add `coolify_traefik_extra_dynamic_configs` for persistent IaC
- ADR 0456 + ws-0456: deployment-aware certificate validation. `scripts/certificate_validator.py --deployment <slug>` reads identity from `.local/deployments/<slug>/identity.yml`. New `cross_deployment_drift` reason code in `config/gate-bypass-waiver-catalog.json`. 11 new tests. Closes follow-up #2 from the ws-0448 postmortem.
- ADR 0457 + ws-0457: host-pinning Phase 1. New optional `deployment_owner` field on `proxmox_guests[*]` in the deployment-v1 topology schema. New `scripts/host_pinning_check.py` audit primitive (`--all`, `--host`, `--cross`, `--json`). Closes Slice D from the ws-0448 postmortem (lv3 ↔ 0fork `oauth2-proxy@4180` port-collision class of bug). 12 new tests. Phase 2 (role-side enforcement) deferred.
- ws-0458: wire ADR 0457 audit into `scripts/validate_repo.sh` as advisory `host-pinning` lane. Promotes the audit from operator-on-demand to pre-push-gate visibility; skips silently when `.local/deployments/` is absent.
- ADR 0457 Phase 2 + ws-0459: role-side enforcement. New `lv3.platform.host_pinning_guard` role refuses converge when the host's `deployment_owner` mismatches the active deployment slug. Wired into `playbooks/public-edge.yml`. Closes the `oauth2-proxy@4180` collision class of bug at converge time. 9 new tests.
- ws-0460: sweep host_pinning_guard across every service playbook by including it in the shared `playbooks/tasks/preflight.yml` surface. 52 service playbooks (ops-portal, keycloak, gitea, mail-platform, openbao, dify, etc.) inherit the guard automatically. Single edit; opt-out via `host_pinning_guard_skip_in_preflight: true`.

- ADR 0452 + ws-0452: Phase 7 drives doctor signals from 3/7 → 1/7
  non-zero. Adds `# pending: <reason>` marker filter to
  `scripts/generate_traceability.py` (mirror of ADR 0445's
  `# late-bound-allow:` pattern). Annotates the 3 real dangling
  surfaces in ws-0377, ws-0396, ws-realtime-dynamic-children — all
  forward-looking references (generated artifact, archive forecast,
  netdata replacement TBD). Replaces `.gitkeep` substrate placeholder
  under `collections/.../molecule/` with a stub `proxmox-fixture`
  driver — `create.yml` falls back to localhost so Molecule scenarios
  load cleanly while the real Proxmox-API driver is deferred to
  ws-0446 phase 4. Live `make doctor` output: `dangling_surfaces`
  and `blocked_substrate` both flipped from `[!]` to `[ok]`. Only
  `stale_receipts` remains red — a real operator-action signal.
  10 new tests on the pending marker.
- ADR 0451 + ws-0451: Phase 6 self-healing actions. Three primitives
  that close the doctor → heal loop: registry-driven role lookup in
  `refresh_safe_receipts.py` (consults `platform_service_registry`'s
  `roles:` field before falling back to the heuristic, unblocks the
  safe_to_refresh signal); `scripts/heal.py` + `make heal` orchestrator
  over every doctor heal_command (live: 2 actionable signals);
  `scripts/heal_validator_docstrings.py` synthesises one-line docstrings
  for validators missing one and **healed all 14 in this release**.
  Live `make doctor` drift signals dropped 4/7 → 3/7 non-zero.
  55 new tests (7 + 15 + 33).
- ADR 0450 + ws-0450: Phase 5 self-healing aggregator + post-merge
  rename hook. `scripts/doctor.py` + `make doctor` aggregates every
  Phase-1/2/3/4 drift signal in one command (live: 4/7 non-zero —
  72/187 stale receipts, 3 dangling surfaces, 14 missing validator
  docstrings, 1 .gitkeep substrate placeholder).
  `scripts/heal_workstream_renames.py` + `.githooks/post-merge`
  auto-rewrites `shared_surfaces` paths after merges introduce file
  renames (used during this release to fix 2 real dangling-surface
  workstreams: ws-0377 and ws-0396).
  `config/windmill/schedules/refresh-safe-receipts.yaml` is the
  declarative template for the weekly receipt-refresh cron the next
  production session activates. 39 new tests (18 doctor + 21 rename hook).
- ADR 0449 + ws-0449: Phase 4 self-healing primitives. Three new
  scripts derived from the 2026-04-28 postmortem: `scripts/reserve_adr.py`
  (atomic ADR-number CLI eliminating the collision class that forced
  this very workstream to renumber 0448→0449 mid-session);
  `scripts/generate_validator_catalogue.py` (gate-coverage map at
  `build/validator-catalogue.yaml` — 30 validators surfaced, 18 in
  `validate_repo.sh`, 14 missing docstrings); `scripts/refresh_safe_receipts.py`
  (classifies stale receipts into safe-to-refresh vs needs-review;
  live signal: 11 needs-review against the live stack.yaml).
  Validator-catalogue freshness wired into `validate_repo.sh` as
  advisory `validate_catalogue_freshness`. 60 new tests.

## Latest Release

- [0.179.38 release notes](docs/release-notes/0.179.38.md)

## Previous Releases

- [0.179.37 release notes](docs/release-notes/0.179.37.md)
- [0.179.36 release notes](docs/release-notes/0.179.36.md)
- [0.179.35 release notes](docs/release-notes/0.179.35.md)
- [0.179.34 release notes](docs/release-notes/0.179.34.md)
- [0.179.33 release notes](docs/release-notes/0.179.33.md)
- [0.179.32 release notes](docs/release-notes/0.179.32.md)
- [0.179.28 release notes](docs/release-notes/0.179.28.md)
- [0.179.26 release notes](docs/release-notes/0.179.26.md)
- [0.179.25 release notes](docs/release-notes/0.179.25.md)
- [0.179.24 release notes](docs/release-notes/0.179.24.md)
- [0.179.23 release notes](docs/release-notes/0.179.23.md)
- [0.179.22 release notes](docs/release-notes/0.179.22.md)
- [0.179.31 release notes](docs/release-notes/0.179.31.md)
- [0.179.30 release notes](docs/release-notes/0.179.30.md)
- [0.179.29 release notes](docs/release-notes/0.179.29.md)
- [0.179.27 release notes](docs/release-notes/0.179.27.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (549 releases)](docs/release-notes/index/2026.md)
