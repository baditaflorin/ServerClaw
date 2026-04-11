# Workstream ADR 0273: Public Endpoint Admission Control

- ADR: [ADR 0273](../adr/0273-public-endpoint-admission-control-for-dns-catalog-and-certificate-concordance.md)
- Title: Live apply public-endpoint admission control across the DNS catalog, shared edge, and certificate plan
- Status: live_applied
- Implemented In Repo Version: 0.177.77
- Live Applied In Platform Version: 0.130.52
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0273-public-endpoint-admission-control`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0273-public-endpoint-admission-control`
- Owner: codex
- Depends On: `adr-0101-automated-certificate-lifecycle-management`, `adr-0139-subdomain-exposure-audit-and-registry`, `adr-0252-route-and-dns-publication-assertion-ledger`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/release-notes/README.md`, `docs/release-notes/0.177.77.md`, `docs/workstreams/adr-0273-public-endpoint-admission-control.md`, `docs/adr/0273-public-endpoint-admission-control-for-dns-catalog-and-certificate-concordance.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-edge-publication.md`, `docs/runbooks/subdomain-exposure-audit.md`, `config/certificate-catalog.json`, `Makefile`, `scripts/subdomain_exposure_audit.py`, `scripts/validate_repo.sh`, `tests/test_subdomain_exposure_audit.py`, `tests/test_edge_publication_makefile.py`, `tests/test_validate_repo_cache.py`, `docs/site-generated/architecture/dependency-graph.md`, `docs/diagrams/agent-coordination-map.excalidraw`, `receipts/subdomain-exposure-audit/`, `receipts/live-applies/`

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
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.77.md`
- `tests/test_subdomain_exposure_audit.py`
- `tests/test_edge_publication_makefile.py`
- `tests/test_validate_repo_cache.py`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `receipts/subdomain-exposure-audit/20260329T124900Z.json`
- `receipts/live-applies/2026-03-29-adr-0273-public-endpoint-admission-control-mainline-live-apply.json`

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

## Live Apply Outcome

- after `git fetch origin` confirmed the exact-main baseline at
  `90c3b26f93fbfe6ffdaecd74fdc422cfcf10281f`, the protected release cut on the
  synchronized tree advanced repository version `0.177.76` to `0.177.77`, and
  the synchronized replay of that exact-main candidate establishes platform
  version `0.130.52` for ADR 0273
- from release commit `e3de9561c1e55a190be8f20176a68c9c2fe97e39`,
  `make route-dns-assertion-ledger env=production` completed successfully with
  `localhost ok=56 changed=0 failed=0 skipped=24`, proving the admission gate
  remains idempotent when the live DNS state is already aligned
- from release commit `e3de9561c1e55a190be8f20176a68c9c2fe97e39`,
  `make configure-edge-publication env=production` completed successfully with
  `nginx-edge ok=61 changed=3 failed=0 skipped=14`; the exact-main run rebuilt
  the docs and changelog portals, published the generated static directories,
  revalidated the shared-edge certificate inputs, rendered the final NGINX
  configuration, and re-verified both HTTP and HTTPS probe hostnames before
  finishing
- direct live verification showed `https://example.com` returning `HTTP/2 308` to
  `https://nginx.example.com/`, while `https://docs.example.com` and
  `https://ops.example.com` both returned `HTTP/2 302` to the expected
  `oauth2/sign_in` paths with `x-robots-tag: noindex, nofollow`
- the live shared-edge certificate proved the concordance contract with a
  Let's Encrypt issuer (`CN=E7`) and SAN coverage including
  `agents.example.com`, `api.example.com`, `apps.example.com`, `changelog.example.com`,
  `docs.example.com`, `draw.example.com`, `headscale.example.com`, `home.example.com`,
  `langfuse.example.com`, `logs.example.com`, `example.com`, `n8n.example.com`,
  `nginx.example.com`, `ops.example.com`, `realtime.example.com`, `registry.example.com`,
  `status.example.com`, `tasks.example.com`, and `wiki.example.com`
- the final exact-main `make subdomain-exposure-audit` rerun wrote
  `receipts/subdomain-exposure-audit/20260329T124900Z.json`; the remaining
  findings are still only the pre-existing `git.example.com` DNS warnings, not ADR
  0273 regressions

## Live Evidence

- canonical mainline live-apply receipt:
  `receipts/live-applies/2026-03-29-adr-0273-public-endpoint-admission-control-mainline-live-apply.json`
- isolated-worktree branch-local receipt:
  `receipts/live-applies/2026-03-29-adr-0273-public-endpoint-admission-control-live-apply.json`
- final audit receipt:
  `receipts/subdomain-exposure-audit/20260329T124900Z.json`
- final direct probes:
  `curl -I https://example.com`, `curl -I https://docs.example.com`,
  `curl -I https://ops.example.com`, and
  `echo | openssl s_client -servername docs.example.com -connect docs.example.com:443 2>/dev/null | openssl x509 -noout -issuer -subject -text`

## Mainline Integration Outcome

- repository version `0.177.77` now carries ADR 0273 on `main`, and the
  synchronized exact-main replay establishes platform version `0.130.52`
- the protected release surfaces now include `README.md`, `RELEASE.md`,
  `VERSION`, `changelog.md`, `versions/stack.yaml`,
  `docs/release-notes/0.177.77.md`, and the updated
  `docs/release-notes/README.md`
- the canonical mainline evidence for this integration is
  `receipts/live-applies/2026-03-29-adr-0273-public-endpoint-admission-control-mainline-live-apply.json`,
  with `receipts/subdomain-exposure-audit/20260329T124900Z.json` preserved as
  the final exact-main audit proof
