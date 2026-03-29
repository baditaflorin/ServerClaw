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

- `git fetch origin --prune` refreshed this worktree onto `origin/main` commit `bae420263872e079fdc34f7f755a6984a3cd5949`, which currently carries repository version `0.177.87` and platform version `0.130.59`.
- `git diff origin/main -- inventory/group_vars/platform.yml inventory/host_vars/proxmox_florin.yml playbooks/serverclaw.yml docs/runbooks/configure-serverclaw.md collections/ansible_collections/lv3/platform/roles/linux_guest_firewall/templates/nftables.conf.j2 collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/tasks/main.yml` confirmed current `main` still lacks the ADR 0254 ServerClaw topology, playbook, runbook, guest-firewall rule, and public-edge publication contract.
- Regenerating the dependent catalogs and diagrams restored the current branch truth after merging `origin/main`; `python3 scripts/validate_service_completeness.py --validate` passed, and `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check` passed.
- Current live host checks still confirm `Debian GNU/Linux 13 (trixie)`, kernel `6.17.13-2-pve`, `pve-manager/9.1.6/71482d1833ded40a`, and `/etc/pve/firewall/170.fw` entry `17:IN ACCEPT -source 10.10.10.10/32 -p tcp -dport 8096` on `proxmox_florin`.
- Current guest-local checks still confirm `coolify-lv3` serves the dedicated ServerClaw container on `0.0.0.0:8096->8080`, returns `HTTP/1.1 200 OK` locally on `127.0.0.1:8096`, and still accepts bootstrap admin sign-in for `ops@lv3.org`.
- Current exact-main candidate checks also show the durability gap clearly: `coolify-lv3` guest nftables currently allows `10.10.10.10` only to `{ 80, 443, 8000 }`, `nginx-lv3` times out on `10.10.10.70:8096`, and public `https://chat.lv3.org/` currently returns `HTTP/2 308` with `location: https://nginx.lv3.org/`.
- The repo automation fixes discovered during this workstream remain on the branch: `platform/policy/toolchain.py` now scopes cached OPA and Conftest binaries by platform, and `config/check-runner-manifest.json` plus `config/validation-gate.json` raise the `yaml-lint` timeout to `240` seconds for local amd64-container replays on arm64 hosts.

## Current State

- The ADR 0254 branch implementation is complete and validated, and the branch-local live proof remains preserved in the first receipt.
- The latest exact-main candidate proof is currently partial, not final: it records that the runtime is healthy but `main` still lacks the governed topology required to keep `chat.lv3.org` stable under server-resident reconciliation.
- Shared integration files remain intentionally untouched here until the final merge step, because the realistic first integrated repo and platform versions will only be known after the exact-main replay succeeds from merged `main`.

## Remaining For Merge-To-Main

- merge this branch onto the latest `origin/main`
- cut the next patch release from merged `main`
- replay `make converge-serverclaw` from that merged `main` checkout
- verify both the internal `nginx-lv3 -> 10.10.10.70:8096` lane and public `https://chat.lv3.org/`
- update `VERSION`, `changelog.md`, `docs/release-notes/`, `versions/stack.yaml`, `README.md`, ADR 0254 metadata, and the mainline receipt only after that replay is clean
