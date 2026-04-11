# Workstream ws-0261-main-integration

- ADR: [ADR 0261](../adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md)
- Title: Integrate ADR 0261 and ADR 0262 exact-main replay onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.95
- Platform Version Observed During Integration: 0.130.63
- Release Date: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0261-main-promote`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0261-main-promote`
- Owner: codex
- Depends On: `ws-0261-live-apply`, `ws-0262-live-apply`

## Purpose

Carry the verified ADR 0261 and ADR 0262 exact-main replay onto the newest
available `origin/main`, refresh the protected release and canonical-truth
surfaces for repository version `0.177.95`, and re-validate the repo
automation plus the governed browser-runner and delegated-authz runtime proofs
before the final push to `origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0261-main-integration.md`
- `docs/workstreams/ws-0261-live-apply.md`
- `docs/workstreams/ws-0262-live-apply.md`
- `docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md`
- `docs/adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.95.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/sync_tree.yml`
- `tests/test_api_gateway_runtime_role.py`
- `receipts/live-applies/2026-03-30-adr-0261-playwright-browser-runners-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0262-openfga-keycloak-exact-main-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-*`

## Verification

- `git fetch origin --prune` confirmed the newest available upstream remained
  `origin/main` commit `8cd0623c2ee5717c1dd2ae1eedc6e693fb24e61e` while this
  promotion tree was being finalized.
- `curl -fsS https://api.example.com/healthz` returned `{"status":"ok"}` and the
  authenticated `https://api.example.com/v1/platform/services` response listed both
  `browser_runner` and `openfga` from the synchronized release tree.
- Guest-local browser-runner verification succeeded again through the Proxmox
  jump path: `curl http://127.0.0.1:8096/healthz` returned
  `{"status":"ok","artifact_root":"/data/artifacts"}` and a direct private
  `POST /sessions` smoke flow returned the expected heading, uppercase result,
  and two artifacts.
- The authenticated gateway route still worked from the synchronized tree:
  `uv run --with-requirements requirements/browser-runner.txt python
  scripts/browser_runner_client.py health --base-url https://api.example.com/v1/browser-runner --bearer-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/platform-context/api-token.txt`
  returned `{"status":"ok","artifact_root":"/data/artifacts"}`, and
  `scripts/browser_runner_smoke.py` against the same base URL returned the
  expected heading, uppercase result, and two artifacts.
- The governed Dify proof was repeated with the current tools API key:
  `POST https://api.example.com/v1/dify-tools/browser-run-session` using
  `X-LV3-Dify-Api-Key` returned HTTP `200` with title
  `LV3 Browser Runner Smoke`, result `BROWSER RUNNER`, and screenshot plus PDF
  artifacts.
- `python3 scripts/serverclaw_authz.py verify --config config/serverclaw-authz/bootstrap.json --openfga-url http://100.64.0.1:8014 --openfga-preshared-key-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openfga/preshared-key.txt --keycloak-url http://10.10.10.20:8091`
  returned `verification_passed: true` with the expected tuples and checks.
- `make pre-push-gate` passed, and `.local/validation-gate/last-run.json`
  recorded a successful build-server validation run at
  `2026-03-30T03:46:45.513234+00:00`.
- `git push origin HEAD:main` then published commit `0a971edbd` to
  `origin/main` after the same promotion tree passed the remote validation lane
  on the push path.

## Outcome

- The synchronized `0.177.95` integration for ADR 0261 and ADR 0262 is now on
  `origin/main`.
- No merge-to-main work remains for this integration workstream; the
  browser-runner and delegated-authorization receipts now document the merged
  current-main proofs.
