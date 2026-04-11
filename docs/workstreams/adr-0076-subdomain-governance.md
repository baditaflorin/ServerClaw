# Workstream ADR 0076: Subdomain Governance And DNS Lifecycle

- ADR: [ADR 0076](../adr/0076-subdomain-governance-and-dns-lifecycle.md)
- Title: Catalog-backed subdomain naming, TLS provisioning, and lifecycle management for example.com
- Status: merged
- Branch: `codex/adr-0076-subdomain-governance`
- Worktree: `.worktrees/adr-0076`
- Owner: codex
- Depends On: `adr-0042-step-ca`, `adr-0021-nginx-edge-publication`, `adr-0072-staging-environment`
- Conflicts With: none
- Shared Surfaces: `config/subdomain-catalog.json`, `roles/hetzner_dns_record`, `roles/nginx_edge_publication`, `Makefile`, `config/workflow-catalog.json`, `config/command-catalog.json`

## Scope

- define JSON schema in `docs/schema/subdomain-catalog.schema.json`
- populate `config/subdomain-catalog.json` with the current governed hostname set plus reserved first-label prefixes
- write `make provision-subdomain FQDN=<name>` so catalogued hostnames can converge DNS and, when already route-backed, refresh the shared edge publication
- add subdomain catalog validation to `make validate` so every repo-managed NGINX route has a catalog entry
- document the subdomain lifecycle process in `docs/runbooks/subdomain-governance.md`
- reserve the listed first-label prefixes (`ops`, `internal`, `staging`, `api`, `smtp`, `imap`, `mail`) in the catalog

## Non-Goals

- DNSSEC configuration (security hardening, separate runbook item)
- CAA record management (separate security hardening item)
- multi-domain support for domains other than `example.com`

## Expected Repo Surfaces

- `config/subdomain-catalog.json`
- `docs/schema/subdomain-catalog.schema.json`
- `scripts/subdomain_catalog.py`
- `playbooks/provision-subdomain.yml`
- updated `Makefile` (`provision-subdomain` target plus edge syntax-check passthrough)
- updated workflow and command catalogs
- `docs/runbooks/subdomain-governance.md`
- `docs/adr/0076-subdomain-governance-and-dns-lifecycle.md`
- `docs/workstreams/adr-0076-subdomain-governance.md`
- `workstreams.yaml`

## Expected Live Surfaces

- no direct live change claimed by this merge; this workstream completes repository governance and the operator workflow
- `make provision-subdomain` is ready for deliberate live use against already-catalogued hostnames

## Verification

- `uvx --from pyyaml python scripts/subdomain_catalog.py --validate`
- `uv run --with pyyaml --with jsonschema python -m unittest tests/test_subdomain_catalog.py`
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/provision-subdomain.yml --syntax-check`
- `uvx --from pyyaml python scripts/subdomain_catalog.py --fqdn ops.example.com --provision-check`
- `make validate`

## Merge Criteria

- all current repo-managed public routes are represented in the subdomain catalog
- reserved prefixes are represented in the catalog and enforced by validation
- `make provision-subdomain` is implemented, documented, and limited to already-catalogued hostnames
- ADR metadata records repository implementation in the release that merges this workstream

## Delivered

- added reserved-prefix governance to `config/subdomain-catalog.json` and extended the validator to enforce both prefix policy and NGINX route coverage
- added `playbooks/provision-subdomain.yml` plus the `make provision-subdomain FQDN=<hostname>` entry point backed by new workflow and command contracts
- documented the lifecycle in `docs/runbooks/subdomain-governance.md` and corrected subdomain-validator invocation examples to use the required PyYAML runtime
- recorded ADR 0076 as implemented in repository release `0.84.0` without claiming a corresponding live platform rollout yet
