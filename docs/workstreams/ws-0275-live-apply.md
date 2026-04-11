# Workstream ws-0275-live-apply: ADR 0275 Exact-Main Apache Tika Replay

- ADR: [ADR 0275](../adr/0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline.md)
- Title: private Apache Tika document extraction service exact-main live apply
- Status: live_applied
- Included In Repo Version: 0.177.151
- Latest Verified Receipt: `receipts/live-applies/2026-04-03-adr-0275-apache-tika-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.94
- Latest Observed On Platform Version: 0.130.94
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Branch: `codex/ws-0275-main-closeout-r8`
- Worktree: `.worktrees/ws-0275-main-closeout-r8`
- Owner: codex
- Depends On: `adr-0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline`, `adr-0319-runtime-pools-as-the-service-partition-boundary`, `adr-0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0275-live-apply.md`, `docs/adr/0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline.md`, `docs/runbooks/configure-tika.md`, `docs/adr/.index.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/0.177.151.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/site-generated/architecture/dependency-graph.md`, `receipts/ops-portal-snapshot.html`, `tests/test_tika_playbook.py`, `tests/test_tesseract_ocr_runtime_role.py`, `tests/test_gotenberg_runtime_role.py`, `receipts/security-reports/20260403T062829Z.json`, `receipts/restic-backups/20260403T063547Z.json`, `receipts/sbom/host-runtime-ai-2026-04-03.cdx.json`, `receipts/live-applies/2026-04-03-adr-0275-apache-tika-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-03-ws-0275-*`

## Scope

- replace the shared runtime-ai pool receipt pointer with a dedicated Apache Tika exact-main receipt after the runtime-ai migration from ADR 0319
- align the Tika, Gotenberg, and Tesseract syntax-check expectations with the document-runtime host-selection contract that the playbooks actually use
- carry the verified replay through protected release surfaces, platform truth, and merge-safe workstream metadata on `main`

## Non-Goals

- publishing Apache Tika through NGINX, the shared API gateway, or any public hostname
- adding OCR or switching to the `apache/tika-full` image; ADR 0275 still keeps OCR out of scope
- replaying the first full runtime-ai pool rollout; this workstream only refreshes the dedicated Tika service truth on the already-live pool guest

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0275-live-apply.md`
- `docs/adr/0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline.md`
- `docs/runbooks/configure-tika.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.151.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `tests/test_tika_playbook.py`
- `tests/test_tesseract_ocr_runtime_role.py`
- `tests/test_gotenberg_runtime_role.py`
- `receipts/security-reports/20260403T062829Z.json`
- `receipts/restic-backups/20260403T063547Z.json`
- `receipts/restic-snapshots-latest.json`
- `receipts/sbom/host-runtime-ai-2026-04-03.cdx.json`
- `receipts/live-applies/2026-04-03-adr-0275-apache-tika-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-release-status-r1-0.177.150.json`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-release-manager-r1-0.177.151.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-targeted-pytest-r1-0.177.150.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-syntax-check-tika-r1-0.177.150.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-syntax-check-gotenberg-r1-0.177.150.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-syntax-check-tesseract-ocr-r1-0.177.150.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-security-posture-host-refresh-r2.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-vulnerability-budget-r1-0.177.150.json`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-immutable-plan-r1-0.177.150.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-live-apply-r1-0.177.151.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-host-via-proxmox-probe-r3-0.177.151.txt`
- `receipts/live-applies/evidence/2026-04-03-ws-0275-mainline-guest-probe-r3-0.177.151.txt`

## Expected Live Surfaces

- `runtime-ai` listens privately on `10.10.10.90:9998`
- `/opt/tika/docker-compose.yml` exists on `runtime-ai`
- the `tika` container is healthy on `runtime-ai`
- `GET /version`, `PUT /tika`, and `PUT /meta` succeed both guest-local and from the Proxmox host over the private network
- the service remains private to the guest network and controller-side automation; no shared edge publication is issued

## Ownership Notes

- Apache Tika now runs on `runtime-ai`, so the routine exact-main replay uses the guarded `make live-apply-service service=tika env=production` path without the ADR 0191 in-place override that was previously required on `docker-runtime`
- take the exclusive lock on `service:tika` before mutation starts and keep heartbeating it until receipts, validations, and pushes are complete
- this closeout branch intentionally owns the protected release and platform-truth surfaces because it is the exact-main integration step for ADR 0275

## Verification

- `uv run --with pyyaml python3 scripts/release_manager.py status --json`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python3 scripts/release_manager.py --bump patch --released-on 2026-04-03 --platform-impact "Apache Tika exact-main replay verified on runtime-ai; this release advances the live platform truth to 0.130.94 with a dedicated Tika receipt."`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_tika_runtime_role.py tests/test_tika_playbook.py tests/test_tesseract_ocr_runtime_role.py tests/test_gotenberg_runtime_role.py tests/test_generate_platform_vars.py tests/test_service_id_resolver.py tests/test_docker_runtime_role.py`
- `make syntax-check-tika`
- `make syntax-check-gotenberg`
- `make syntax-check-tesseract-ocr`
- `uv run --with ansible-core --with pyyaml --with nats-py python scripts/security_posture_report.py --env production --skip-lynis --skip-trivy --print-report-json`
- `python3 scripts/vulnerability_budget.py --service tika --json`
- `make immutable-guest-replacement-plan service=tika`
- `make live-apply-service service=tika env=production`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 'python3 - <<'"'"'PY'"'"'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p" ops@10.10.10.90 'python3 - <<'"'"'PY'"'"'`
- `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`
- `uvx --from pyyaml python scripts/canonical_truth.py --write`
- `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --write`
- `uv run --with pyyaml python3 scripts/generate_diagrams.py --write`
- `git diff --check`
- `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`
- `uvx --from pyyaml python scripts/canonical_truth.py --check`
- `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --check`
- `scripts/validate_repo.sh workstream-surfaces generated-docs generated-portals data-models health-probes alert-rules agent-standards`
- `make remote-validate`
- `make pre-push-gate`

## Outcome

- Release `0.177.151` now carries the exact-main ADR 0275 closeout and the document-runtime validation tests that match the syntax-check-safe host-selection contract.
- The dedicated receipt `receipts/live-applies/2026-04-03-adr-0275-apache-tika-mainline-live-apply.json` supersedes `receipts/live-applies/2026-04-02-adr-0319-runtime-ai-pool-mainline-live-apply.json` as the canonical `tika` latest-receipt pointer.
- The April 3, 2026 replay succeeded on `runtime-ai` with final recap `ok=171 changed=5 failed=0 skipped=37 rescued=1`; during the run, `linux_guest_firewall` temporarily dropped the Docker bridge chains, and the shared recovery path restored them by restarting Docker and reasserting the bridge-chain health checks before Tika verification continued.
- Fresh host-via-Proxmox and guest-local probes reverified Apache Tika `3.2.3`, successful plaintext extraction, successful metadata JSON extraction, the healthy `tika` container, and listeners on both `0.0.0.0:9998` and `[::]:9998`.
- The final validation bundle passed locally and on the build server: `scripts/validate_repo.sh workstream-surfaces generated-docs generated-portals data-models health-probes alert-rules agent-standards`, `make remote-validate`, and `make pre-push-gate` all completed successfully on the exact-main candidate.
- The exact-main closeout advanced the integrated repository truth to `0.177.151` and the verified live platform truth to `0.130.94`.
