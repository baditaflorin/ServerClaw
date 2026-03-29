# Workstream WS-0259: n8n Connector Fabric Live Apply

- ADR: [ADR 0259](../adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md)
- Title: Re-verify the governed n8n lane as the external app connector fabric for ServerClaw
- Status: ready_for_merge
- Implemented In Repo Version: not yet
- Live Applied In Platform Version: 0.130.50
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/adr-0259-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0259-live-apply`
- Owner: codex
- Depends On: `adr-0151-n8n`, `adr-0206-ports-and-adapters`, `adr-0254-serverclaw`, `adr-0258-temporal`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0259-live-apply.md`, `docs/adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-n8n.md`, `config/service-capability-catalog.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `scripts/restore_verification.py`, `tests/test_restore_verification.py`, `tests/test_validate_service_catalog.py`, `tests/test_n8n_metadata.py`, `receipts/live-applies/`

## Scope

- mark ADR 0259 as implemented by binding the already-live ADR 0151 n8n runtime
  to the ServerClaw product boundary instead of leaving it as an unclaimed
  standalone automation surface
- refresh the repo-managed service, workflow, command, and runbook metadata so
  operators can see that n8n is the third-party connector plane while
  assistant reasoning and long-lived orchestration stay outside n8n
- replay the governed n8n converge path from the latest `origin/main` state,
  verify the runtime end to end, and record fresh live-apply evidence

## Expected Repo Surfaces

- `docs/adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0259-live-apply.md`
- `docs/runbooks/configure-n8n.md`
- `config/service-capability-catalog.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `scripts/restore_verification.py`
- `tests/test_validate_service_catalog.py`
- `tests/test_n8n_metadata.py`
- `tests/test_restore_verification.py`
- `workstreams.yaml`
- `receipts/live-applies/2026-03-29-adr-0259-n8n-serverclaw-connector-fabric-live-apply.json`

## Expected Live Surfaces

- `https://n8n.lv3.org/healthz` still returns `200` through the shared edge
- `https://n8n.lv3.org/` still redirects humans into the shared edge auth flow
- `https://n8n.lv3.org/webhook-test/...` remains reachable without the browser
  auth redirect so ServerClaw can use governed webhook adapters
- the guest-local readiness and owner-login checks still pass on
  `docker-runtime-lv3`

## Verification Plan

- run the focused ADR 0259 regression slice for the n8n metadata, playbook, and
  runtime-role contracts
- run repository automation and validation paths, including the full validation
  suite and the pre-push gate
- replay `make converge-n8n` from this isolated latest-`origin/main` worktree
- record direct probes for public health, public editor auth, public webhook
  reachability, guest-local readiness, and owner sign-in before updating ADR
  metadata

## Live Apply Outcome

- Exact-main replay succeeded from source commit
  `8751d7f0f784794320994e6aca8a7cd9af0e423b`, rebased on top of
  `origin/main` commit `90c3b26f93fbfe6ffdaecd74fdc422cfcf10281f`
  (`VERSION` `0.177.76`, integrated platform baseline `0.130.51`), with final
  recap
  `docker-runtime-lv3 ok=117 changed=2 failed=0 skipped=32`,
  `postgres-lv3 ok=47 changed=0 failed=0 skipped=7`,
  `nginx-lv3 ok=37 changed=2 failed=0 skipped=8`, and
  `localhost ok=18 changed=0 failed=0 skipped=3`.
- The branch-local live apply fixed the real replay blockers surfaced during the
  first run: `n8n` now reads topology from `hostvars['proxmox_florin']`, uses
  host networking to reach `postgres-lv3` across the private guest network, and
  skips unrelated generated static-site syncs when publishing through the
  shared NGINX edge from a fresh worktree.
- Focused regression and repo-facing validation also passed on the rebased
  head: `24` targeted tests passed across the n8n metadata, playbook, runtime,
  idempotency, and artifact-cache guardrails; `make syntax-check-n8n` passed;
  and the service-specific guardrails remained green for interface contracts,
  standby capacity, service redundancy, and immutable guest replacement.
- The repo-wide validation sweep also required migrating a pre-existing
  restore-readiness warm-up loop onto the shared retry framework so the
  `check_ad_hoc_retry.py` gate now passes on the same branch that carries the
  ADR 0259 live-apply evidence.

## Live Evidence

- `curl -fsS https://n8n.lv3.org/healthz` returned `{"status":"ok"}`.
- `curl -fsSI https://n8n.lv3.org/` returned `HTTP/2 302` with
  `location: https://n8n.lv3.org/oauth2/sign_in?rd=https://n8n.lv3.org/`.
- `curl -sSI https://n8n.lv3.org/webhook-test/serverclaw-connector-smoke`
  returned `HTTP/2 404` from `n8n` without an oauth redirect, preserving the
  unauthenticated webhook ingress contract.
- Guest-local verification on `docker-runtime-lv3` returned
  `readiness_status: 200`, `readiness_body: ok`,
  `login_email: ops@lv3.org`, and `login_role: global:owner`.
- `sudo docker ps | grep -w n8n` on `docker-runtime-lv3` showed the
  `docker.n8n.io/n8nio/n8n:2.2.6` runtime container and the
  `openbao/openbao:2.5.1` sidecar both running.
- `scripts/service_redundancy.py --check-live-apply --service n8n` still reports
  `declared R1 -> platform R1 -> implemented R0 [gate=unproven]` because the
  repository has no recorded R1 rehearsal proof yet; this live apply does not
  claim that proof.

## Mainline Integration Outcome

- Pending the main-only integration surfaces:
  `VERSION`, release sections in `changelog.md`, the top-level `README.md`
  integrated status summary, `versions/stack.yaml`, and a final exact-main
  receipt after merge to `main`.
- The branch-local `make validate` sweep now clears every non-release stage and
  stops only at generated canonical truth for `changelog.md`, which is
  expected until those protected merge-to-`main` surfaces are updated in the
  final integration step.
