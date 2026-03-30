# Workstream ws-0286-live-apply: Live Apply ADR 0286 From Latest `origin/main`

- ADR: [ADR 0286](../adr/0286-tesseract-ocr-service-for-scanned-image-text-extraction.md)
- Title: Deploy the private Tesseract OCR extraction service and its Apache Tika dependency
- Status: in_progress
- Included In Repo Version: pending main integration
- Canonical Mainline Receipt: pending exact-main integration
- Live Applied In Platform Version: pending verification
- Implemented On: pending verification
- Live Applied On: pending verification
- Branch: `codex/ws-0286-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0286-live-apply`
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

- pending

## Verification

- pending

## Outcome

- pending
