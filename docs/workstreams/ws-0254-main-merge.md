# Workstream ws-0254-main-merge

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Integrate ADR 0254 exact-main replay onto `origin/main`
- Status: `merged`
- Included In Repo Version: `0.177.91`
- Platform Version Observed During Merge: `0.130.60` on `origin/main` commit `72ee92ef77cae2cf73e3c42168b2e193984c05c1`
- Release Date: `2026-03-30`
- Live Applied On: `2026-03-30` from merged `main`
- Branch: `codex/ws-0254-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0254-main-merge`
- Owner: codex
- Depends On: `ws-0254-live-apply`

## Purpose

Carry the verified ADR 0254 latest-main replay onto the current `origin/main`,
refresh the protected release and canonical-truth surfaces from that merged
baseline, re-run the exact-main ServerClaw converge path from the integration
commit, and record the canonical mainline live-apply receipt before pushing
`origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0254-main-merge.md`
- `docs/workstreams/ws-0254-live-apply.md`
- `docs/adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `platform/policy/toolchain.py`
- `tests/test_policy_checks.py`
- `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0254-mainline-live-apply.txt`

## Verification

- `git push origin HEAD:main` advanced `origin/main` from `9102f1c6a0118cc7857831de95bb9f625d761738` to `72ee92ef77cae2cf73e3c42168b2e193984c05c1` after the remote pre-push gate passed `agent-standards`, `alert-rule-validation`, `ansible-lint`, `ansible-syntax`, `artifact-secret-scan`, `dependency-direction`, `dependency-graph`, `documentation-index`, `generated-docs`, `generated-portals`, `integration-tests`, `packer-validate`, `policy-validation`, `schema-validation`, `security-scan`, `service-completeness`, `tofu-validate`, `type-check`, `workstream-surfaces`, and `yaml-lint`
- the exact-main replay `make converge-serverclaw` then completed successfully from merged `main` with recap `coolify ok=60 changed=4 failed=0 skipped=14`, `docker-runtime ok=63 changed=0 failed=0 skipped=7`, `nginx-edge ok=39 changed=4 failed=0 skipped=7`, and `proxmox-host ok=241 changed=6 failed=0 skipped=108`
- host verification on `proxmox-host` confirmed `/etc/pve/firewall/170.fw` still contains `17:IN ACCEPT -source 10.10.10.10/32 -p tcp -dport 8096`
- internal edge verification confirmed `nc -vz -w 5 10.10.10.70 8096` from `nginx-edge` succeeds and `curl -sk -D - https://127.0.0.1/ -H 'Host: chat.example.com' -o /dev/null` now returns `HTTP/2 200`
- guest-local runtime verification on `coolify` confirmed `curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8096/` returns `200`, and bootstrap admin sign-in returns `{"email":"ops@example.com","role":"admin","token_type":"Bearer","has_token":true}`
- public verification confirmed `curl -Ik http://chat.example.com/` now returns `HTTP/1.1 308 Permanent Redirect` with `Location: https://chat.example.com/`, and `curl -Ik https://chat.example.com/` returns `HTTP/2 200`
- the final validation sweep passed `live_apply_receipts.py --validate`, `validate_repository_data_models.py --validate`, `canonical_truth.py --check`, `subdomain_exposure_audit.py --validate`, `platform_manifest.py --check`, and `agent-standards`; `workstream-surfaces` now returns the expected terminal-branch guard because `codex/ws-0254-main-merge` is no longer an active owner once its status flips to `merged`
- the earlier branch-local pass and later pre-merge gap remain preserved in the March 29 receipts, and the final merged-main truth is now recorded in `receipts/live-applies/2026-03-30-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json` plus `receipts/live-applies/evidence/2026-03-30-adr-0254-mainline-live-apply.txt`

## Current State

- ADR 0254 is now merged to `origin/main` in repository version `0.177.91`
- the exact-main replay succeeded from merged `main`, so the dedicated `chat.example.com` surface is now durable under repo-managed reconciliation on the current platform version `0.130.60`
- ADR metadata, release notes, stack truth, workstream state, and the final mainline receipt now agree with the verified live platform state

## Remaining For Merge-To-Main

- none
