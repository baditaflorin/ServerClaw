# Workstream ADR 0139: Subdomain Exposure Audit And Registry

- ADR: [ADR 0139](../adr/0139-subdomain-exposure-audit-and-registry.md)
- Title: Deterministic subdomain exposure registry plus live DNS and edge-auth audit for all tracked `example.com` hostnames
- Status: merged
- Branch: `codex/adr-0139-subdomain-exposure-audit`
- Worktree: `.worktrees/adr-0139`
- Owner: codex
- Depends On: `adr-0076-subdomain-governance`, `adr-0091-drift-detection`
- Conflicts With: none
- Shared Surfaces: `config/subdomain-catalog.json`, `config/subdomain-exposure-registry.json`, `scripts/subdomain_exposure_audit.py`, `roles/nginx_edge_publication/defaults/main.yml`, `config/workflow-catalog.json`

## Scope

- extend `config/subdomain-catalog.json` with an explicit `auth_requirement` classification per hostname
- correct the catalog status for production hostnames already live on public DNS
- add `config/subdomain-exposure-registry.json` as the deterministic registry derived from the catalog and repo-managed edge publication
- add `scripts/subdomain_exposure_audit.py` to validate the repo contract and optionally probe live DNS, edge auth, Hetzner zone records, and TLS expiry
- add `config/windmill/scripts/subdomain-exposure-audit.py` and `make subdomain-exposure-audit` for operator execution from a worker checkout
- document the operator workflow in `docs/runbooks/subdomain-exposure-audit.md`

## Non-Goals

- auto-remediating undeclared or misclassified hostnames
- changing live edge auth on currently public portals as part of this ADR
- claiming the live schedule or notification plumbing is already applied from `main`

## Expected Repo Surfaces

- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `docs/schema/subdomain-catalog.schema.json`
- `docs/schema/subdomain-exposure-registry.schema.json`
- `scripts/subdomain_catalog.py`
- `scripts/subdomain_exposure_audit.py`
- `config/windmill/scripts/subdomain-exposure-audit.py`
- `docs/runbooks/subdomain-exposure-audit.md`
- `docs/runbooks/subdomain-governance.md`
- `tests/test_subdomain_catalog.py`
- `tests/test_subdomain_exposure_audit.py`
- `tests/test_docs_site.py`
- `docs/workstreams/adr-0139-subdomain-exposure-audit.md`

## Expected Live Surfaces

- One audit receipt can be produced from a worker checkout with `make subdomain-exposure-audit`
- Production hostnames that already resolve publicly are no longer tracked as `planned` in the catalog
- Edge OIDC enforcement for `ops.example.com` is represented explicitly in both the catalog and the derived registry

## Verification

- `uvx --from pyyaml python scripts/subdomain_catalog.py --validate`
- `uvx --from pyyaml python scripts/subdomain_exposure_audit.py --validate`
- `uv run --with pytest --with pyyaml --with jsonschema --with jinja2 pytest -q tests/test_subdomain_catalog.py tests/test_subdomain_exposure_audit.py tests/test_docs_site.py`
- `python3 config/windmill/scripts/subdomain-exposure-audit.py --help`

## Merge Criteria

- catalog auth classification is enforced by validation
- the committed exposure registry is generated from canonical repo sources and kept in sync by validation
- the audit workflow can detect planned-but-live hostnames and missing edge OIDC enforcement
- the ADR, runbooks, and workstream registry all reflect repository implementation status

## Outcome

- repository implementation is complete on `main` in repo release `0.127.0`
- no platform version change is claimed yet; the weekly worker schedule and any notification plumbing still require apply from `main`
