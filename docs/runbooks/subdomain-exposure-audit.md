# Subdomain Exposure Audit

This runbook covers the ADR 0139 subdomain exposure registry and audit workflow.

## Repo Surfaces

- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `docs/schema/subdomain-exposure-registry.schema.json`
- `scripts/subdomain_exposure_audit.py`
- `config/windmill/scripts/subdomain-exposure-audit.py`
- `receipts/subdomain-exposure-audit/`

## Registry

The committed registry is a deterministic projection of the canonical subdomain catalog plus the repo-managed edge publication surfaces.

Refresh it after catalog or edge-routing changes:

```bash
uvx --from pyyaml python scripts/subdomain_exposure_audit.py --write-registry
```

Validation fails if the committed registry drifts from the generated output:

```bash
uvx --from pyyaml python scripts/subdomain_exposure_audit.py --validate
```

## Live Audit

Run the full audit against current DNS and public HTTP behavior:

```bash
make subdomain-exposure-audit
```

This performs four checks:

1. repo contract validation between the catalog and repo-managed edge auth wiring
2. live public DNS resolution for production hostnames that should already be active
3. unauthenticated HTTP probing for `edge_oidc` hostnames
4. Hetzner DNS zone enumeration when `HETZNER_DNS_API_TOKEN` is available

Each run writes one timestamped receipt under `receipts/subdomain-exposure-audit/`.

## Findings

Typical findings:

- `subdomain_resolves_publicly_but_is_not_tracked_active`
- `active_subdomain_missing_expected_public_resolution`
- `catalog_requires_edge_oidc_but_route_is_not_protected`
- `undeclared_subdomain_present_in_zone`
- `edge_oidc_not_enforced_on_live_probe`

Treat CRITICAL findings as exposure drift that should block further public-surface changes until resolved.

## Remediation

- If a hostname is live but still marked `planned`, update `config/subdomain-catalog.json`, regenerate the registry, and commit both changes.
- If the catalog says `edge_oidc` but the edge route is not protected, update `roles/nginx_edge_publication/defaults/main.yml` and re-run the audit.
- If Hetzner DNS exposes a hostname that is absent from the catalog, either catalog and govern it immediately or remove the DNS record.
- If an active hostname no longer resolves publicly, verify Hetzner DNS, the shared edge IP target, and recent DNS-management changes before changing the catalog.

## Verification

```bash
uvx --from pyyaml python scripts/subdomain_exposure_audit.py --validate
uv run --with pytest --with pyyaml --with jsonschema --with jinja2 pytest -q tests/test_subdomain_catalog.py tests/test_subdomain_exposure_audit.py tests/test_docs_site.py
python3 config/windmill/scripts/subdomain-exposure-audit.py --help
```
