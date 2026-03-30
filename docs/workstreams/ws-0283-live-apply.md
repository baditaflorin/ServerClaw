# Workstream ws-0283-live-apply: Live Apply ADR 0283 From Latest `origin/main`

- ADR: [ADR 0283](../adr/0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer.md)
- Title: Deploy Plausible Analytics on `docker-runtime-lv3`, publish it at `analytics.lv3.org`, and verify privacy-first page tracking end to end
- Status: live_applied
- Included In Repo Version: 0.177.99
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0283-plausible-analytics-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0283-plausible-analytics-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.66
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0283-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0283-live-apply`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0077-compose-secret-injection`, `adr-0086-backup-and-recovery`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0283`, `docs/workstreams/ws-0283-live-apply.md`, `docs/runbooks/configure-plausible.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/plausible.yml`, `playbooks/services/plausible.yml`, `roles/plausible_runtime/`, `roles/nginx_edge_publication/`, `collections/ansible_collections/lv3/platform/plugins/filter/service_topology.py`, `config/*catalog*.json`, `config/ansible-execution-scopes.yaml`, `receipts/image-scans/`, `receipts/live-applies/`, `tests/`

## Scope

- deploy Plausible Community Edition on `docker-runtime-lv3` with repo-managed PostgreSQL, ClickHouse, and OpenBao-backed runtime secrets
- publish `analytics.lv3.org` through the shared NGINX edge with dashboard access gated by the existing edge OIDC flow while tracker and health endpoints remain public
- register a conservative set of public, non-authenticated LV3 pages as Plausible sites and inject the tracker through the shared edge publication template
- verify runtime health, bootstrap state, tracker injection, and one accepted synthetic analytics event before recording the live-apply receipt

## Non-Goals

- introducing service-native Plausible Enterprise features that are absent from Community Edition
- tracking authenticated internal operator traffic or API-only traffic
- updating protected release surfaces on this workstream branch before the final `main` integration step

## Expected Repo Surfaces

- `docs/adr/0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer.md`
- `docs/runbooks/configure-plausible.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/plausible.yml`
- `playbooks/services/plausible.yml`
- `roles/plausible_runtime/`
- `roles/nginx_edge_publication/`
- `collections/ansible_collections/lv3/platform/plugins/filter/service_topology.py`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/health-probe-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/image-catalog.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/service-completeness.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `receipts/image-scans/`
- `receipts/live-applies/`
- `tests/`
- `workstreams.yaml`

## Expected Live Surfaces

- Plausible Community Edition stack running on `docker-runtime-lv3`
- public hostname `analytics.lv3.org`
- public tracker script and event endpoints at `https://analytics.lv3.org/js/` and `https://analytics.lv3.org/api/event`
- repo-managed analytics injection on the selected public LV3 pages

## Ownership Notes

- this workstream owns the Plausible runtime, edge injection contract, and the branch-local live-apply evidence
- `docker-runtime-lv3` and `nginx-lv3` are shared live surfaces, so replay must use the governed service wrapper and a documented narrow in-place exception if ADR 0191 blocks the default path
- protected integration files remain deferred on this branch until the exact-main replay and final merge step

## Purpose

Implement ADR 0283 by making Plausible the repo-managed privacy-first web
analytics layer on `docker-runtime-lv3`, publishing `analytics.lv3.org`
through the shared edge with a public tracker and authenticated dashboard, and
leaving a clean branch-local audit trail that an exact-main replay can promote
onto the protected `main` surfaces safely.

## Branch-Local Delivery

- `6b1d7f4ec` added the Plausible runtime, tracked-site registration, tracker
  injection, workflow, and image-scan surfaces needed for the first governed
  replay.
- `0408147a2` fixed the bootstrap contract to use `bin/plausible rpc`,
  corrected the bootstrap transaction match so verification emits JSON
  cleanly, and preserved the first synchronized validation evidence after the
  branch rebased to the latest `origin/main`.
- `2b35ffca6` hardened the fresh-worktree replay path by generating the shared
  edge portal artifacts before publication, admitting `analytics.lv3.org` into
  the certificate catalog so the exposure audit stays green, refreshing the
  generated dependency and ops-portal artifacts, and preserving the successful
  synchronized replay evidence.

## Verification

- The synchronized branch-local proof is recorded in
  `receipts/live-applies/2026-03-30-adr-0283-plausible-analytics-live-apply.json`
  from committed source `2b35ffca68e0a9bc0bad8897320a37f9c53b7d2d` on top of
  repository version `0.177.97` and live platform version `0.130.64`.
- `uv run --with pytest pytest tests/test_plausible_playbook.py tests/test_edge_publication_makefile.py tests/test_plausible_runtime_role.py`
  returned `13 passed` on the synchronized latest-main tree.
- `uvx --from pyyaml python scripts/subdomain_exposure_audit.py --validate`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  and `make preflight WORKFLOW=converge-plausible` all passed after the fresh
  worktree bootstrap and certificate-admission fixes landed.
- `HETZNER_DNS_API_TOKEN=... make converge-plausible` completed successfully
  with final recap
  `docker-runtime-lv3 : ok=145 changed=4 unreachable=0 failed=0 skipped=21 rescued=0 ignored=0`,
  `localhost : ok=18 changed=0 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0`,
  and
  `nginx-lv3 : ok=40 changed=5 unreachable=0 failed=0 skipped=6 rescued=0 ignored=0`.
- Fresh guest-local verification confirmed the Plausible containers stayed up,
  `curl -fsS http://127.0.0.1:8016/api/system/health/ready` returned
  `{"sessions":"ok","postgres":"ok","clickhouse":"ok","sites_cache":"ok"}`,
  and listeners remained present on `10.10.10.20:8016` and `127.0.0.1:8016`.
- Fresh public verification confirmed
  `https://analytics.lv3.org/api/system/health/ready` returned the same ready
  payload, the `nginx.lv3.org` page now includes the
  `https://analytics.lv3.org/js/script.js` tracker snippet, the dashboard
  remains OIDC-gated with `HTTP/2 302` plus `x-robots-tag: noindex, nofollow`,
  and `analytics.lv3.org` resolves publicly to `65.108.75.123`.
- A public end-to-end analytics smoke posted to
  `https://analytics.lv3.org/api/event` with `202 Accepted`, then confirmed the
  synthetic path `/plausible-e2e-1774861457` appeared in Plausible on poll
  attempt `2`.
- The exact-main replay from committed source `f8bd6088817ecd676f9c59f17f52e9cf0dd20b56`
  also completed successfully with final recap
  `docker-runtime-lv3 : ok=145 changed=5 unreachable=0 failed=0 skipped=21 rescued=0 ignored=0`,
  `localhost : ok=18 changed=0 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0`,
  and
  `nginx-lv3 : ok=39 changed=5 unreachable=0 failed=0 skipped=7 rescued=0 ignored=0`,
  preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0283-mainline-live-apply-0.177.99.txt`.
- A fresh Proxmox host-state probe preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0283-mainline-host-state-r1-0.177.99.txt`
  confirmed the server still reports hostname `Debian-trixie-latest-amd64-base`,
  `pve-manager/9.1.6/71482d1833ded40a (running kernel: 6.17.13-2-pve)`, and
  running VMs `110` (`nginx-lv3`) plus `120` (`docker-runtime-lv3`).
- A fresh exact-main guest-state probe preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0283-mainline-post-state-r1-0.177.99.txt`
  confirmed the `plausible`, `plausible-db`, `plausible-events-db`, and
  `plausible-openbao-agent` containers remained up, the local ready endpoint
  still returned `{"sessions":"ok","postgres":"ok","clickhouse":"ok","sites_cache":"ok"}`,
  and listeners remained present on `10.10.10.20:8016` and `127.0.0.1:8016`.
- A fresh exact-main public verification preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0283-mainline-public-verify-r1-0.177.99.txt`
  reconfirmed the ready payload, the `nginx.lv3.org` tracker snippet, the OIDC
  dashboard redirect with `x-robots-tag: noindex, nofollow`, and public DNS for
  `analytics.lv3.org -> 65.108.75.123`.
- A fresh exact-main public event smoke preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0283-mainline-public-event-e2e-r1-0.177.99.txt`
  posted `202 Accepted` to `https://analytics.lv3.org/api/event` and confirmed
  the synthetic path `/plausible-e2e-1774863976` reached ClickHouse on poll
  attempt `2`.
- The final integrated validation bundle also passed on the `0.177.99` tree:
  `git diff --check`, `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  `uvx --from pyyaml python scripts/canonical_truth.py --check`, and
  `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`
  all passed, preserved in the `...-git-diff-check-r3-0.177.99.txt`,
  `...-live-apply-receipts-validate-r3-0.177.99.txt`,
  `...-validate-data-models-r3-0.177.99.txt`,
  `...-canonical-truth-check-r3-0.177.99.txt`, and
  `...-platform-manifest-check-r3-0.177.99.txt` evidence files.
- `make remote-validate` first exposed one stale generated dependency graph and
  then passed on rerun after `uv run --with jsonschema python scripts/generate_dependency_diagram.py --write`,
  preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0283-mainline-remote-validate-r1-0.177.99.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-adr-0283-mainline-remote-validate-r2-0.177.99.txt`.
- `make pre-push-gate` passed from the exact-main integration tree with
  `agent-standards`, `documentation-index`, `yaml-lint`, `schema-validation`,
  `policy-validation`, `alert-rule-validation`, `dependency-direction`,
  `generated-docs`, `generated-portals`, `dependency-graph`,
  `artifact-secret-scan`, `ansible-syntax`, `ansible-lint`, `type-check`,
  `service-completeness`, `packer-validate`, `tofu-validate`,
  `security-scan`, `integration-tests`, and `workstream-surfaces` all
  reported as `passed`, preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0283-mainline-pre-push-gate-r2-0.177.99.txt`.

## Outcome

- The branch-local latest-main replay is now live on the current integrated
  platform baseline `0.130.64`.
- The first synchronized replay needed one provider-side bridge because the
  Hetzner DNS create task did not create the `analytics` A record; the record
  was created manually through the provider API and the later governed replays
  then observed the canonical state.
- The next two synchronized replays exposed branch-proof gaps rather than live
  runtime failures: a fresh worktree needed `generate-edge-static-sites`
  before shared edge publication, and the public-endpoint admission audit
  required an `analytics-edge` certificate-catalog entry for the shared edge.
- `VERSION`, release sections in `changelog.md`, `versions/stack.yaml`,
  `build/platform-manifest.json`, the integrated `README.md` summary, and the
  canonical exact-main receipt still remain for the final merge-to-`main`
  integration step.

## Exact-Main Finalization

- The final exact-main replay from release `0.177.99` is now the canonical
  proof for ADR 0283 and advances the integrated platform version from
  `0.130.65` to `0.130.66`.
- The current server state was rechecked directly on the Proxmox host and the
  live guests after the exact-main replay, so the canonical receipt now records
  both the host baseline and the public analytics path from committed mainline
  source.
- The earlier branch-local receipt remains part of the audit trail, but the
  canonical `main` receipt for Plausible now points at the exact-main replay in
  `receipts/live-applies/2026-03-30-adr-0283-plausible-analytics-mainline-live-apply.json`.
