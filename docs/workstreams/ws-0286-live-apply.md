# Workstream ws-0286-live-apply: Live Apply ADR 0286 From Latest `origin/main`

- ADR: [ADR 0286](../adr/0286-tesseract-ocr-service-for-scanned-image-text-extraction.md)
- Title: Deploy the private Tesseract OCR extraction service and its Apache Tika dependency
- Status: live_applied
- Included In Repo Version: 0.177.107
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0286-tesseract-ocr-live-apply.json`
- Live Applied In Platform Version: 0.130.71
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0286-live-apply-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0286-live-apply-r3`
- Owner: codex
- Depends On: `adr-0107`, `adr-0165`, `adr-0275`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0275`, `docs/adr/0286`, `docs/workstreams/ws-0286-live-apply.md`, `docs/runbooks/configure-tika.md`, `docs/runbooks/configure-tesseract-ocr.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/tika.yml`, `playbooks/tesseract-ocr.yml`, `collections/ansible_collections/lv3/platform/playbooks/tika.yml`, `collections/ansible_collections/lv3/platform/playbooks/tesseract-ocr.yml`, `collections/ansible_collections/lv3/platform/roles/tika_runtime/`, `collections/ansible_collections/lv3/platform/roles/tesseract_ocr_runtime/`, `config/*catalog*.json`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `Makefile`, `scripts/document_extraction.py`, `scripts/generate_platform_vars.py`, `scripts/validate_repo.sh`, `tests/test_document_extraction.py`, `tests/test_tika_runtime_role.py`, `tests/test_tesseract_ocr_runtime_role.py`, `receipts/image-scans/`, `receipts/live-applies/`

## Purpose

Implement ADR 0286 from the latest `origin/main` by making the image-OCR
fallback real on the live platform, including the missing ADR 0275 Apache Tika
dependency, a repo-managed Tika-first and Tesseract-fallback extraction helper,
and branch-local live-apply evidence that another agent can merge safely.

## Branch-Local Delivery

- `a895e0660` replayed the initial Tesseract OCR service surfaces onto the
  newer `origin/main@4db2d1f4d` baseline, including the service playbooks,
  runtime role, helper CLI, generated catalog updates, and the workstream
  scaffolding needed for ADR 0286.
- `9aee835bb` regenerated the dependency, SLO, and capability surfaces after
  the service landed so the newer mainline kept the OCR runtime wired into the
  generated service inventories.
- `4aaedd2ce` replaced the corrupt OCR verification fixture with the
  deterministic `ocr-ok.png` sample and aligned the verification and runbook
  surfaces around the working `/ocr` contract.
- `1bcc69f94` stabilized the shared Tika metadata verification path, refreshed
  the Tesseract workflow and health-catalog surfaces, and preserved the first
  governed Tika and Tesseract replay evidence from the synchronized workstream
  before `origin/main` advanced again under ADR 0269.
- `e025bcd0c` carried forward the Docker recovery hardening discovered during
  the live apply, including stale compose-network recovery in both runtimes and
  the removal of Tesseract's `network_mode: bridge` override.

## Verification

- The refreshed latest-main tree reran the focused OCR regression slice with
  `uv run --with pytest --with pyyaml python -m pytest -q tests/test_tika_runtime_role.py tests/test_tesseract_ocr_runtime_role.py tests/test_document_extraction.py tests/test_generate_platform_vars.py tests/test_service_id_resolver.py tests/test_docker_runtime_role.py tests/test_post_verify_tasks.py tests/test_docker_publication_assurance_playbook.py`
  plus both service syntax checks; the transcript is preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0286-targeted-checks-r1-0.177.107.txt`
  and returned `71 passed in 3.02s`.
- The governed Tika prerequisite replay is preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0286-tika-prereq-replay.txt`
  and completed with final recap
  `docker-runtime-lv3 : ok=129 changed=5 unreachable=0 failed=0 skipped=24 rescued=1 ignored=0`.
- The governed Tesseract replay is preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0286-live-apply-run.txt`
  and completed with final recap
  `docker-runtime-lv3 : ok=127 changed=5 unreachable=0 failed=0 skipped=21 rescued=0 ignored=0`.
- Direct private-endpoint verification is preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0286-endpoint-verify-r1-0.177.107.txt`
  and confirmed `Apache Tika 3.2.3`, the healthy OCR payload, and direct OCR
  output `text: "OCR OK"`.
- The controller-local Tika-first helper verification is preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0286-helper-verify-r1-0.177.107.txt`
  and confirmed `fallback_used: true`, `extraction_method: "tesseract"`, and
  `text: "OCR OK"`.
- Release automation is preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0286-release-status-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-release-dry-run-r1-0.177.107.txt`,
  and
  `receipts/live-applies/evidence/2026-03-30-adr-0286-release-write-r1-0.177.107.txt`;
  the dry run planned `0.177.107` from `0.177.106`, and the write run then cut
  release `0.177.107` with no additional platform-version bump.
- Final generation and validation automation is preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0286-generate-adr-index-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-generate-status-docs-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-generate-dependency-diagram-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-generate-dependency-diagram-r2-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-generate-diagrams-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-generate-ops-portal-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-validate-generated-docs-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-validate-generated-portals-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-git-diff-check-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-live-apply-receipts-validate-r1-0.177.107.txt`,
  and
  `receipts/live-applies/evidence/2026-03-30-adr-0286-check-build-server-r1-0.177.107.txt`.
- Current-base repo automation path testing is preserved in
  `receipts/live-applies/evidence/2026-03-30-adr-0286-dependency-check-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-type-check-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-workstream-surfaces-r1-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-validate-r4-0.177.107.txt`,
  `receipts/live-applies/evidence/2026-03-30-adr-0286-remote-validate-r2-0.177.107.txt`,
  and
  `receipts/live-applies/evidence/2026-03-30-adr-0286-pre-push-gate-r1-0.177.107.txt`;
  `make validate` completed every preceding lane and then failed only the
  expected terminal-workstream branch guard, while `make remote-validate`
  passed every selected substantive check and `make pre-push-gate` passed 19 of
  20 blocking checks with that same lone branch-local non-pass.

## Outcome

- ADR 0286 is now integrated in repository release `0.177.107`.
- The private OCR capability is live on the current verified platform baseline
  `0.130.71`; this release records the exact-main proof and does not bump the
  platform version again.
- `receipts/live-applies/2026-03-30-adr-0286-tesseract-ocr-live-apply.json`
  is the canonical receipt for the integrated Tesseract OCR rollout on top of
  the newer ADR 0269 mainline.
- On the exact-main candidate branch, the only remaining non-pass in the
  top-level repo automation is the expected `workstream-surfaces` guard because
  `codex/ws-0286-live-apply-r3` still maps to terminal workstream
  `ws-0286-live-apply`.
- That terminal-branch guard is the only remaining difference between this
  dedicated workstream branch and the final `origin/main` push; no ADR 0286
  regression or unresolved latest-main blocker remains.
