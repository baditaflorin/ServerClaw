# Workstream ADR 0076: Subdomain Governance And DNS Lifecycle

- ADR: [ADR 0076](../adr/0076-subdomain-governance-and-dns-lifecycle.md)
- Title: Catalog-backed subdomain naming, TLS provisioning, and lifecycle management for lv3.org
- Status: ready
- Branch: `codex/adr-0076-subdomain-governance`
- Worktree: `../proxmox_florin_server-subdomain-governance`
- Owner: codex
- Depends On: `adr-0042-step-ca`, `adr-0021-nginx-edge-publication`, `adr-0072-staging-environment`
- Conflicts With: none
- Shared Surfaces: `config/subdomain-catalog.json`, `roles/hetzner_dns_record`, `roles/nginx_edge_publication`, `Makefile`

## Scope

- define JSON schema in `docs/schema/subdomain-catalog.schema.json`
- populate `config/subdomain-catalog.json` with all current subdomains (minimum: all live-applied subdomains)
- write `make provision-subdomain FQDN=<name>` target that runs DNS record + TLS + NGINX route in sequence
- add subdomain catalog validation to `make validate` (check every NGINX route has a catalog entry)
- document the subdomain lifecycle process in `docs/runbooks/subdomain-governance.md`
- reserve all listed prefixes (ops, internal, staging, api, smtp, imap, mail) in the catalog

## Non-Goals

- DNSSEC configuration (security hardening, separate runbook item)
- CAA record management (separate security hardening item)
- multi-domain support for domains other than `lv3.org`

## Expected Repo Surfaces

- `config/subdomain-catalog.json`
- `docs/schema/subdomain-catalog.schema.json`
- updated `roles/nginx_edge_publication` (validates against catalog on apply)
- updated `Makefile` (`provision-subdomain` target)
- `docs/runbooks/subdomain-governance.md`
- `docs/adr/0076-subdomain-governance-and-dns-lifecycle.md`
- `docs/workstreams/adr-0076-subdomain-governance.md`
- `workstreams.yaml`

## Expected Live Surfaces

- no new subdomains created by this workstream; catalog documents existing subdomains
- `make provision-subdomain` is operational (tested against staging with a test subdomain)

## Verification

- `make validate` catches a missing catalog entry for a NGINX route
- `make provision-subdomain FQDN=test.staging.lv3.org` creates DNS record, step-ca cert, and NGINX route
- all existing public subdomains appear in the catalog with correct TLS provider and target

## Merge Criteria

- all live-applied subdomains are in the catalog
- the NGINX validation lint rule is integrated into `make validate`
- `make provision-subdomain` is tested and documented
- reserved prefixes are documented in the catalog and the runbook

## Notes For The Next Assistant

- the existing `roles/hetzner_dns_record` role already handles DNS API calls; `provision-subdomain` should wrap it, not replace it
- staging wildcard `*.staging.lv3.org` can be a single step-ca cert issued to the nginx-staging VM; add that as the first staging TLS entry in the catalog
