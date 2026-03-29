# Subdomain Exposure Audit

This runbook covers the ADR 0139 subdomain exposure registry and the ADR 0252
route and DNS publication assertion ledger workflow.

## Repo Surfaces

- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `docs/schema/subdomain-catalog.schema.json`
- `docs/schema/subdomain-exposure-registry.schema.json`
- `scripts/subdomain_exposure_audit.py`
- `playbooks/route-dns-assertion-ledger.yml`
- `config/windmill/scripts/subdomain-exposure-audit.py`
- `receipts/subdomain-exposure-audit/`

## Registry

The committed registry is a deterministic projection of the canonical subdomain
catalog plus the repo-managed edge publication surfaces and route assertions.

The shared contract is now split into two layers:

- `publication`: canonical delivery, access, and audience semantics used by
  shared consumers
- `adapter`: DNS, NGINX route, oauth2-proxy, and TLS details that stay at the
  delivery edge

Each registry entry also carries:

- `assertions`: the declared route target, audience, and publication-class
  checks ADR 0252 expects to remain true
- `evidence_plan`: which live probes should run for DNS, Hetzner zone state,
  HTTP auth, private routes, and TLS

Refresh it after catalog or edge-routing changes:

```bash
uvx --from pyyaml python scripts/subdomain_exposure_audit.py --write-registry
```

Validation fails if the committed registry drifts from the generated output:

```bash
uvx --from pyyaml python scripts/subdomain_exposure_audit.py --validate
```

## Live Audit

Run the full audit against current DNS, Hetzner zone state, private-route
reachability, TLS metadata, and public HTTP behavior:

```bash
make subdomain-exposure-audit
```

This performs six checks:

1. repo contract validation between the canonical publication model and the
   repo-managed edge auth adapter wiring
2. live public DNS resolution for production hostnames that should already be
   active
3. Hetzner DNS zone record-set comparison when `HETZNER_DNS_API_TOKEN` is
   available
4. unauthenticated HTTP probing for `edge_oidc` hostnames
5. private-route probing from the declared target path for tailnet-only or
   operator-only endpoints
6. TLS metadata collection for public and declared private HTTPS endpoints

Each run writes one timestamped receipt under `receipts/subdomain-exposure-audit/`.

## Findings

Typical findings:

- `subdomain_resolves_publicly_but_is_not_tracked_active`
- `active_subdomain_missing_expected_public_resolution`
- `catalog_requires_edge_oidc_but_route_is_not_protected`
- `undeclared_subdomain_present_in_zone`
- `edge_oidc_not_enforced_on_live_probe`
- `active_subdomain_zone_records_do_not_match_expected_set`
- `private_route_not_reachable_at_declared_target`
- `tls_certificate_subject_does_not_cover_hostname`

Treat CRITICAL findings as exposure drift that should block further public-surface changes until resolved.

## Remediation

- If a hostname is live but still marked `planned`, update
  `config/subdomain-catalog.json`, regenerate the registry, and commit both
  changes.
- If the canonical publication model says `platform-sso` but the edge route is
  not protected, update `roles/nginx_edge_publication/defaults/main.yml` and
  re-run the audit.
- If Hetzner DNS exposes a hostname that is absent from the catalog, either catalog and govern it immediately or remove the DNS record.
- If an active hostname no longer resolves publicly, verify Hetzner DNS, the shared edge IP target, and recent DNS-management changes before changing the catalog.
- If the governed drift set is known and should be reconciled directly, run
  `HETZNER_DNS_API_TOKEN=... make route-dns-assertion-ledger` and then rerun
  `make subdomain-exposure-audit`.

## Reconcile Governed DNS Drift

ADR 0252 adds a dedicated mutation path for the currently governed drift set:

```bash
HETZNER_DNS_API_TOKEN=... make route-dns-assertion-ledger
```

Use this when the route ledger needs to converge the shared apex, mail, tailnet
database, or tailnet vault records, or when the audited stale records should be
retired from Hetzner DNS.

## Verification

```bash
uvx --from pyyaml python scripts/subdomain_exposure_audit.py --validate
uv run --with pytest --with pyyaml --with jsonschema --with jinja2 pytest -q tests/test_subdomain_catalog.py tests/test_subdomain_exposure_audit.py tests/test_docs_site.py
python3 config/windmill/scripts/subdomain-exposure-audit.py --help
HETZNER_DNS_API_TOKEN=... make route-dns-assertion-ledger
```
