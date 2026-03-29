# Workstream ws-0254-main-merge

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Integrate ADR 0254 exact-main replay onto `origin/main`
- Status: `ready_for_merge`
- Included In Repo Version: not yet
- Platform Version Observed During Merge: 0.130.59 on latest `origin/main` before the final replay
- Release Date: not yet
- Live Applied On: not yet from merged `main`
- Branch: `codex/ws-0254-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0254-main-merge`
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

## Verification

- `git fetch origin --prune` most recently refreshed this worktree onto `origin/main` commit `020c5f5ad21d21864861e7b3aa21570474ff8988`, which currently carries repository version `0.177.88` and platform version `0.130.59`.
- `git diff origin/main -- inventory/group_vars/platform.yml inventory/host_vars/proxmox_florin.yml playbooks/serverclaw.yml docs/runbooks/configure-serverclaw.md collections/ansible_collections/lv3/platform/roles/linux_guest_firewall/templates/nftables.conf.j2 collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/tasks/main.yml` confirmed current `main` still lacks the ADR 0254 ServerClaw topology, playbook, runbook, guest-firewall rule, and public-edge publication contract.
- Regenerating the dependent catalogs and diagrams restored the current branch truth after merging `origin/main`; `python3 scripts/validate_service_completeness.py --validate` passed, and `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check` passed.
- `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-live-apply.json` preserves the first branch-local proof where the dedicated `chat.lv3.org` surface, internal `8096` lane, and bootstrap admin sign-in all succeeded before later `origin/main` drift.
- `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json` plus `receipts/live-applies/evidence/2026-03-29-adr-0254-*.txt` preserve the later pre-merge gap where the merged-main lane was not yet durable on current `origin/main`.
- The merged branch now also carries the ADR 0266 validation-runner contract hardening and the platform-scoped policy-toolchain refresh from current `origin/main`; a fresh exact-main `make converge-serverclaw` replay from this merged branch is still required before any final platform-version claim.

## Current State

- The ADR 0254 branch implementation is complete and validated, and the branch-local live proof remains preserved in the first receipt.
- This integration branch is now refreshed onto current `origin/main` commit `020c5f5ad21d21864861e7b3aa21570474ff8988`, so the next realistic repository release is the post-`0.177.88` patch cut from this merged tree.
- The latest exact-main proof is still pending from this merged branch, so shared release files and platform-version claims remain intentionally provisional until that replay succeeds from the refreshed base.

## Remaining For Merge-To-Main

- merge this branch onto the latest `origin/main`
- cut the next patch release from merged `main`
- replay `make converge-serverclaw` from that merged `main` checkout
- verify both the internal `nginx-lv3 -> 10.10.10.70:8096` lane and public `https://chat.lv3.org/`
- update `VERSION`, `changelog.md`, `docs/release-notes/`, `versions/stack.yaml`, `README.md`, ADR 0254 metadata, and the mainline receipt only after that replay is clean
