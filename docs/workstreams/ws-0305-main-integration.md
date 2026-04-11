# Workstream ws-0305-main-integration

- ADR: [ADR 0305](../adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md)
- Title: Integrate ADR 0305 k6 exact-main replay onto `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.120
- Platform Version Observed During Integration: 0.130.77
- Release Date: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0305-mainline-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0305-mainline-final`
- Owner: codex
- Depends On: `ws-0305-live-apply`

## Purpose

Carry the verified ADR 0305 branch-local live apply onto the synchronized
`origin/main` baseline, refresh to the newest realistic `origin/main` when it
moves during closeout, cut the final `0.177.120` release from that exact-main
tree, rerun the authoritative repository automation and k6 validation paths,
and publish one canonical mainline receipt that preserves the repaired
comparison baseline together with the newest truthful live degradation on the
current platform.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0305-main-integration.md`
- `docs/workstreams/ws-0305-live-apply.md`
- `docs/adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md`
- `docs/runbooks/k6-load-testing.md`
- `docs/runbooks/configure-openfga.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `config/build-server.json`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `scripts/workstream_surface_ownership.py`
- `scripts/run_gate_fallback.py`
- `tests/test_workstream_surface_ownership.py`
- `tests/test_run_gate_fallback.py`
- `receipts/live-applies/`
- `receipts/k6/`
- `receipts/sbom/`

## Verification

- The first exact-main branch refresh targeted `origin/main` commit `5c7e07235f7b0da1f756148e145397f0ac6ceb10`, which carried repository version `0.177.117` and platform version `0.130.76`; committed source `0d6e8c9eb5d9d086e74cf92d8165248295baa076` was then used as the initial authoritative replay candidate, and the resulting `0.177.118` smoke-pass/load-fail evidence remains committed for comparison.
- The first exact-main smoke attempt exposed live drift rather than an ADR 0305 repo regression: Prometheus on `monitoring` was still loopback-bound to `127.0.0.1:9090` and OpenFGA on `docker-runtime` was concurrently restarting. The resulting failure is preserved in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-smoke-r5-0.177.118.txt`.
- `make converge-monitoring` then completed successfully from the rebased tree and updated the Prometheus runtime contract on `monitoring`; the correction loop is recorded in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-converge-monitoring-r8-0.177.118.txt` and `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-prometheus-bind-manual-r1-0.177.118.txt`.
- The repaired exact-main smoke replay passed from committed source and produced `receipts/k6/smoke-keycloak-20260331T133226Z.json` and `receipts/k6/smoke-openfga-20260331T133226Z.json`, with `110/0` and `112/0` request/failure counts respectively, captured in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-smoke-r6-0.177.118.txt`.
- The exact-main load replay completed without the earlier NATS deadlock and preserved the truthful final outcome in `receipts/k6/load-keycloak-20260331T133416Z.json`, `receipts/k6/load-openfga-20260331T133416Z.json`, and `receipts/k6/raw/20260331T133416Z-load-summary.json`, captured in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-load-r3-0.177.118.txt`. Keycloak failed the declared 1% objective with `1585` requests and `441` failures (`27.82%`); OpenFGA passed the run with `1184` requests and `8` failures (`0.68%`) but still reported `error_budget_remaining_pct: 0.0`.
- `origin/main` then advanced again to commit `2411a7cd428e0eba17168aa5eed66f04c4ed48dd`, which already carried repository version `0.177.118` and platform version `0.130.77`, so the workstream was rebased a second time and recut on that newer latest-main baseline.
- The latest-main smoke replay on the `0.177.119` closeout used committed source `6d476f01e75a2ecf31d8ce13df1250bc6aec193e` and preserved a real current-platform failure rather than a repo regression: `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-keycloak-public-oidc-r1-0.177.119.txt` shows `https://sso.example.com/realms/lv3/.well-known/openid-configuration` returning `502 Bad Gateway`, `receipts/k6/smoke-keycloak-20260331T145155Z.json` recorded `110` requests with `110` failures, and `receipts/k6/smoke-openfga-20260331T145155Z.json` still passed with `112` requests and `0` failures.
- The same latest-main verification loop also captured guest-local runtime degradation evidence: `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-keycloak-openfga-health-r1-0.177.119.txt` timed out against `http://10.10.10.20:8091/health/ready`, matching the public Keycloak failure and confirming the smoke breakage was live-platform truth.
- The latest-main load replay from that same committed source preserved the truthful degraded outcome in `receipts/k6/load-keycloak-20260331T145555Z.json`, `receipts/k6/load-openfga-20260331T145555Z.json`, and `receipts/k6/raw/20260331T145555Z-load-summary.json`, captured in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-load-r4-0.177.119.txt`. Keycloak failed with `1600` requests and `1184` failures (`74.00%`), OpenFGA also failed with `1182` requests and `14` failures (`1.18%`), Prometheus remote-write repeatedly timed out, and ntfy warning publication was bounded into `404 Not Found` warnings instead of blocking or discarding the receipts.
- Focused regression tests for the latest-main automation hardening passed: `uv run --with pytest pytest tests/test_run_gate_fallback.py` recorded `2 passed` in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-run-gate-fallback-tests-r2-0.177.119.txt`, and `uv run --with pytest pytest tests/test_remote_exec.py` recorded `16 passed` in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-remote-exec-tests-r5-0.177.119.txt`.
- The final latest-main repo-automation sweep passed from this tree: `make remote-validate` recorded `workstream-surfaces`, `agent-standards`, `ansible-syntax`, `schema-validation`, `policy-validation`, `alert-rule-validation`, `type-check`, and `dependency-graph` as `passed` in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-remote-validate-r5-0.177.119.txt`.
- `make pre-push-gate` then preserved the real remote-builder wrinkle without masking it: `docker-build` hit transient `502 Bad Gateway` pulls of `registry.example.com/check-runner/infra:2026.03.23`, `remote_exec.sh` synced the partial remote status file back first, and `scripts/run_gate_fallback.py` reran only unresolved `packer-validate` and `tofu-validate` locally. The first full post-edit rerun in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-pre-push-gate-r5-0.177.119.txt` proved that the old `120` second `packer-validate` budget was too tight for the controller-local arm64 fallback, so this closeout widened `packer-validate` to `300` seconds in `config/validation-gate.json` and `config/check-runner-manifest.json`; the final merged gate then passed in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-pre-push-gate-r6-0.177.119.txt`.
- `origin/main` later advanced again to commit `97f05802253cbb8fb4640249fdb8485fd7ecdde6`, which still carried repository version `0.177.119` and platform version `0.130.77` after ADR 0306 landed, so the final merge-to-main release was recut as `0.177.120` while preserving the latest realistic `0.177.119` k6 smoke/load evidence from committed source `6d476f01e75a2ecf31d8ce13df1250bc6aec193e`.
- The final integrated `0.177.120` verification from this exact merged tree also passed: `uv run --with pytest pytest tests/test_run_gate_fallback.py tests/test_remote_exec.py tests/test_iac_policy_scan.py` recorded `21 passed, 1 skipped` in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-final-targeted-pytest-r1-0.177.120.txt`, `make check-build-server` passed in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-final-check-build-server-r1-0.177.120.txt`, `make remote-validate` passed in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-final-remote-validate-r1-0.177.120.txt`, and `make pre-push-gate` passed in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-final-pre-push-gate-r1-0.177.120.txt` after syncing the partial remote status back and rerunning only unresolved `packer-validate` and `tofu-validate` locally around transient `502 Bad Gateway` pulls from `registry.example.com/check-runner/infra:2026.03.23`.
- The final metadata closeout also reran `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`, `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`, and `git diff --check`, with passing proofs in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-final-adr-index-r1-0.177.120.txt`, `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-final-live-apply-receipts-validate-r1-0.177.120.txt`, and `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-final-git-diff-check-r1-0.177.120.txt`.
- The canonical receipt JSON and closeout patch set also validate cleanly from this tree: `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate` passed in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-live-apply-receipts-validate-r5-0.177.119.txt`, `uv run --with pyyaml python3 scripts/generate_adr_index.py --write` refreshed `docs/adr/.index.yaml` in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-adr-index-r3-0.177.119.txt`, and `git diff --check` passed in `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-git-diff-check-r6-0.177.119.txt`.
- The canonical mainline receipt for the closeout is `receipts/live-applies/2026-03-31-adr-0305-k6-mainline-live-apply.json`.

## Outcome

- ADR 0305 is fully integrated on the dedicated exact-main branch and included
  in repository release `0.177.120`.
- The canonical closeout receipt is
  `receipts/live-applies/2026-03-31-adr-0305-k6-mainline-live-apply.json`.
- The latest realistic integration baseline observed platform version
  `0.130.77`, but no additional platform-version bump is recorded for this
  merge because ADR 0305 first became true earlier on platform version
  `0.130.75`; this exact-main closeout records the newest latest-main replay
  and the hardened repository automation path.
