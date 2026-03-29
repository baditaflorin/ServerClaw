# Workstream ADR 0273: Public Endpoint Admission Control

- ADR: [ADR 0273](../adr/0273-public-endpoint-admission-control-for-dns-catalog-and-certificate-concordance.md)
- Title: Live apply public-endpoint admission control across the DNS catalog, shared edge, and certificate plan
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0273-public-endpoint-admission-control`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0273-public-endpoint-admission-control`
- Owner: codex
- Depends On: `adr-0101-automated-certificate-lifecycle-management`, `adr-0139-subdomain-exposure-audit-and-registry`, `adr-0252-route-and-dns-publication-assertion-ledger`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/adr-0273-public-endpoint-admission-control.md`, `docs/adr/0273-public-endpoint-admission-control-for-dns-catalog-and-certificate-concordance.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-edge-publication.md`, `docs/runbooks/subdomain-exposure-audit.md`, `config/certificate-catalog.json`, `Makefile`, `scripts/subdomain_exposure_audit.py`, `scripts/validate_repo.sh`, `tests/test_subdomain_exposure_audit.py`, `tests/test_edge_publication_makefile.py`, `tests/test_validate_repo_cache.py`, `receipts/live-applies/`

## Scope

- enforce repo-side admission across the canonical public hostname catalog, the generated publication registry, and the certificate plan
- block shared-edge and route-ledger live replays when a public TLS hostname is missing from `config/certificate-catalog.json` or the rendered shared-edge certificate domain set
- verify the live edge and DNS workflows end to end from an isolated latest-`origin/main` worktree and record one receipt

## Expected Repo Surfaces

- `config/certificate-catalog.json`
- `Makefile`
- `scripts/subdomain_exposure_audit.py`
- `scripts/validate_repo.sh`
- `docs/runbooks/configure-edge-publication.md`
- `docs/runbooks/subdomain-exposure-audit.md`
- `docs/adr/0273-public-endpoint-admission-control-for-dns-catalog-and-certificate-concordance.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/adr-0273-public-endpoint-admission-control.md`
- `workstreams.yaml`
- `tests/test_subdomain_exposure_audit.py`
- `tests/test_edge_publication_makefile.py`
- `tests/test_validate_repo_cache.py`
- `receipts/live-applies/2026-03-29-adr-0273-public-endpoint-admission-control-live-apply.json`

## Expected Live Surfaces

- shared-edge replays refuse to run when public hostname, route, or certificate-plan truth diverges
- route-ledger DNS replays refuse to run when the public endpoint admission contract is broken
- the live shared edge certificate still covers every active public hostname declared in the catalog after replay

## Verification Plan

- run focused pytest slices for the admission logic, make targets, and validation-script wiring
- run `uv run --with pyyaml python scripts/subdomain_exposure_audit.py --validate`
- run `./scripts/validate_repo.sh data-models agent-standards`
- replay `make configure-edge-publication` and `make route-dns-assertion-ledger` from this isolated worktree
- rerun `make subdomain-exposure-audit` plus direct TLS and HTTP checks before writing the receipt

## Notes For The Next Assistant

- this workstream intentionally leaves protected release files alone until the final mainline integration step
- if the live audit still reports unrelated legacy public-hostname drift, record it explicitly in the receipt instead of hiding it inside chat context
