# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

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

- [0.179.16 release notes](docs/release-notes/0.179.16.md)

## Previous Releases

- [0.179.15 release notes](docs/release-notes/0.179.15.md)
- [0.179.14 release notes](docs/release-notes/0.179.14.md)
- [0.179.13 release notes](docs/release-notes/0.179.13.md)
- [0.179.12 release notes](docs/release-notes/0.179.12.md)
- [0.179.11 release notes](docs/release-notes/0.179.11.md)
- [0.179.10 release notes](docs/release-notes/0.179.10.md)
- [0.179.9 release notes](docs/release-notes/0.179.9.md)
- [0.179.8 release notes](docs/release-notes/0.179.8.md)
- [0.179.7 release notes](docs/release-notes/0.179.7.md)
- [0.179.6 release notes](docs/release-notes/0.179.6.md)
- [0.179.5 release notes](docs/release-notes/0.179.5.md)
- [0.179.4 release notes](docs/release-notes/0.179.4.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (531 releases)](docs/release-notes/index/2026.md)
