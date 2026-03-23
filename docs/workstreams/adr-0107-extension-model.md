# Workstream ADR 0107: Platform Extension Model for Adding New Services

- ADR: [ADR 0107](../adr/0107-platform-extension-model.md)
- Title: 15-item extension checklist encoded in the scaffold generator and enforced by a validation gate completeness check, with grandfathering for existing services
- Status: merged
- Branch: `codex/adr-0107-extension-model`
- Worktree: `../proxmox_florin_server-extension-model`
- Owner: codex
- Depends On: `adr-0033-service-catalog`, `adr-0064-health-probes`, `adr-0078-scaffold-generator`, `adr-0087-validation-gate`, `adr-0092-platform-api-gateway`, `adr-0096-slo-tracking`, `adr-0104-dependency-graph`
- Conflicts With: none
- Shared Surfaces: `scripts/generate_service_scaffold.py`, `config/validation-gate.json`, all catalog JSON files

## Scope

- update `scripts/generate_service_scaffold.py` — extends the scaffold generator to produce all 15 checklist artifacts (not just the Ansible role skeleton)
- write `scripts/validate_service_completeness.py` — checks every service in the capability catalog against the 15-item checklist; reports missing items
- write `config/service-completeness.json` — tracks completeness status for all current services using per-check suppressions for legacy services
- update `config/validation-gate.json` — add `service-completeness` check (runs `validate_service_completeness.py`; legacy suppressions expire on 2026-09-23)
- write Jinja2 templates for all generated scaffold artifacts: `docs/templates/service-page.md.j2`, `docs/templates/alert-rules.yml.j2`, `docs/templates/grafana-dashboard.json.j2`, `docs/templates/runbook.md.j2`
- update `docs/runbooks/add-a-new-service.md` — replace ad-hoc instructions with the formal 5-step process (write ADR → scaffold → fill stubs → validate → open workstream)
- add `lv3 validate --service <name>` command to platform CLI — runs completeness check for a specific service

## Non-Goals

- Automated filling of scaffold stubs (stubs are generated empty; operator fills content)
- Automated Grafana dashboard configuration (template only; panels must be configured)
- Removing existing services that are grandfathered (cleanup is tracked in `config/service-completeness.json`)

## Expected Repo Surfaces

- `scripts/generate_service_scaffold.py` (updated)
- `scripts/validate_service_completeness.py` (new)
- `config/service-completeness.json` (new)
- `config/validation-gate.json` (patched: service-completeness check added)
- `docs/templates/service-page.md.j2`
- `docs/templates/alert-rules.yml.j2`
- `docs/templates/grafana-dashboard.json.j2`
- `docs/templates/runbook.md.j2`
- `docs/runbooks/add-a-new-service.md` (updated)
- `docs/adr/0107-platform-extension-model.md`
- `docs/workstreams/adr-0107-extension-model.md`

## Expected Live Surfaces

- `make scaffold-service NAME=test-service TYPE=compose VM=docker-runtime-lv3 DEPENDS_ON=postgres,keycloak` generates all 15 artifacts in the correct directories
- `lv3 validate --service keycloak` shows which checklist items keycloak has (and which are grandfathered)
- Validation gate rejects a push that adds a new service to the capability catalog without completing the checklist (non-grandfathered service only)

## Verification

- Run `make scaffold-service NAME=demo-service TYPE=compose VM=docker-runtime-lv3 DEPENDS_ON=postgres`
- Verify all 15 expected files/patches are created
- Run `lv3 validate --service demo_service` → all 15 items present
- Delete one item (e.g., remove demo-service from health-probe-catalog.json); run `lv3 validate --service demo-service` → reports missing health probe
- Attempt to push with demo-service missing the health probe; verify validation gate rejects it
- Clean up demo-service artifacts (remove from all catalogs)

## Merge Criteria

- `lv3 scaffold new-service` generates all 15 artifacts
- `lv3 validate --service <name>` works for at least 3 existing services
- Validation gate updated with completeness check
- All existing services catalogued in `config/service-completeness.json` with correct grandfathering status
- `docs/runbooks/add-a-new-service.md` updated with formal process

## Notes For The Next Assistant

- The scaffold generator must use `json.loads(Path(catalog).read_text())` and then `json.dumps(updated, indent=2)` to patch existing JSON catalogs; do not overwrite files — patch them in-place so existing entries are preserved
- Grandfathering in `config/service-completeness.json` should stay per-check rather than global; this allows individual items to graduate from grandfathered status independently as they are fixed
- The `grafana-dashboard.json.j2` template must produce valid Grafana JSON; use a minimal working dashboard template (one stat panel, one time series panel) rather than an empty JSON — an empty dashboard breaks Grafana's provisioning
- Jinja2 templates live in `docs/templates/`; confirm this directory does not conflict with MkDocs's template directory (`docs/overrides/` is MkDocs's convention; use a different path if needed)

## Outcome

- merged in repo version `0.97.0`
- live apply not yet performed from `main`
