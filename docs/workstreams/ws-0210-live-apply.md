# Workstream ws-0210-live-apply: ADR 0210 Live Apply From Latest `origin/main`

- ADR: [ADR 0210](../adr/0210-canonical-domain-models-over-vendor-schemas.md)
- Title: Separate canonical publication models from delivery-adapter fields and verify the live public-surface automation path
- Status: ready
- Implemented In Repo Version: 0.177.32
- Live Applied In Platform Version: 0.130.36
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0210-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-ws-0210-live-apply`
- Owner: codex
- Depends On: `adr-0074-human-navigation-and-platform-ops-portal`, `adr-0076-subdomain-governance`, `adr-0139-subdomain-exposure-registry`, `adr-0207-anti-corruption-layers-at-provider-boundaries`
- Conflicts With: none
- Shared Surfaces: `config/subdomain-exposure-registry.json`, `docs/schema/subdomain-exposure-registry.schema.json`, `scripts/subdomain_exposure_audit.py`, `scripts/ops_portal/app.py`, `scripts/ops_portal/templates/partials/overview.html`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/ops-portal.env.j2`, `docs/runbooks/subdomain-exposure-audit.md`, `docs/runbooks/subdomain-governance.md`, `docs/runbooks/ops-portal-down.md`, `tests/test_subdomain_exposure_audit.py`, `tests/test_interactive_ops_portal.py`, `receipts/live-applies/2026-03-28-adr-0210-canonical-domain-models-live-apply.json`, `workstreams.yaml`

## Scope

- move the shared subdomain exposure registry from a flat adapter-shaped schema to a canonical publication model with explicit nested delivery-adapter details
- keep DNS, NGINX, and oauth2-proxy specifics at the adapter edge while shared consumers read the normalized publication contract
- expose the canonical publication contract in the interactive ops portal so the live platform reflects the ADR in a user-facing surface
- replay the affected runtime and audit automation from this isolated worktree, verify the platform result end to end, and record durable live-apply evidence

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest -q tests/test_subdomain_exposure_audit.py tests/test_interactive_ops_portal.py tests/test_compose_runtime_secret_injection.py` passed with `28 passed`.
- `uvx --from pyyaml --with jsonschema python scripts/subdomain_exposure_audit.py --check-registry --validate` passed from the committed branch state.
- `ansible-playbook -i inventory/hosts.yml -e ansible_ssh_private_key_file=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 playbooks/ops-portal.yml` replayed cleanly from commit `343f9028531a503815f156cbad54f17ebff3aeb3` with `docker-runtime-lv3 ok=99 changed=0 failed=0`.
- `curl -sf http://10.10.10.20:8092/health` returned `{"status":"ok"}` and `/partials/overview` rendered the canonical publication strings including `ops.lv3.org · operator · shared-edge · platform-sso`.
- `uvx --from pyyaml --with jsonschema python scripts/subdomain_exposure_audit.py --check-registry --include-live-dns --include-http-auth --include-tls --include-hetzner-zone --print-report-json --write-receipt` completed successfully and recorded `receipts/subdomain-exposure-audit/20260328T113654Z.json`.

## Live Evidence

- Branch-local live-apply receipt: `receipts/live-applies/2026-03-28-adr-0210-canonical-domain-models-live-apply.json`
- Live publication audit receipt: `receipts/subdomain-exposure-audit/20260328T113654Z.json`
- Ops portal runtime on `docker-runtime-lv3` now serves the canonical publication contract from `/opt/ops-portal/data/config/subdomain-exposure-registry.json` with `schema_version: 2.0.0`.

## Outcome

- ADR 0210 is live on the platform: the canonical publication contract now separates `publication` semantics from delivery-specific `adapter` fields, and the interactive ops portal renders that canonical model on the live overview cards.
- The first replay exposed a packaging regression where the portal image omitted `publication_contract.py`; the branch fixed that Dockerfile contract and added a regression test so future rollouts fail in CI instead of at runtime.
- The live publication audit path is now resilient to TLS probe failures and records those issues as findings instead of aborting; the latest live audit still reports pre-existing drift outside ADR 0210 for `mail.lv3.org`, `vault.lv3.org`, `autoconfig.lv3.org`, `lv3.org`, `notify.lv3.org`, `registry.lv3.org`, `www.lv3.org`, and `database.lv3.org`.
- Main-only integration work remains to be applied from `main`: `VERSION`, release sections in `changelog.md`, the top-level `README.md` integrated status summary, and `versions/stack.yaml`.
