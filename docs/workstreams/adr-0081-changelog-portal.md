# Workstream ADR 0081: Platform Changelog And Deployment History Portal

- ADR: [ADR 0081](../adr/0081-platform-changelog-and-deployment-history.md)
- Title: Generated deployment history portal synthesising receipts, promotions, and audit events into a human-readable timeline
- Status: live_applied
- Branch: `codex/adr-0081-changelog-portal`
- Worktree: `../proxmox_florin_server-changelog-portal`
- Owner: codex
- Depends On: `adr-0074-ops-portal`, `adr-0073-promotion-pipeline`, `adr-0066-mutation-audit-log`, `adr-0052-loki-logs`, `adr-0075-service-capability-catalog`
- Conflicts With: none
- Shared Surfaces: `scripts/`, `build/`, NGINX edge config, `receipts/`, `Makefile`, `changelog.md`

## Scope

- write `scripts/generate_changelog_portal.py` that reads receipts, promotions, and Loki audit events into a static HTML site at `build/changelog-portal/`
- implement four portal views: Timeline, Per-service history, Per-environment history, Promotions log
- add `changelog.lv3.org` NGINX route and subdomain catalog entry
- add `get-deployment-history` tool to `config/agent-tool-registry.json`
- replace the manual detail section of `changelog.md` with a pointer to the portal; preserve the `## Unreleased` scratchpad section
- add `make generate-changelog-portal` target and hook into `make generate-status`
- add `docs/release-notes/` directory and move numbered release notes out of the root changelog
- document the changelog model in `docs/runbooks/deployment-history-portal.md`

## Non-Goals

- real-time live streaming of events in the browser (static generation only)
- reverting deployments from the portal (read surface only)
- Loki integration before Loki is live-applied (falls back to receipts-only mode gracefully)

## Expected Repo Surfaces

- `scripts/generate_changelog_portal.py`
- `build/changelog-portal/` (gitignored)
- updated NGINX config for `changelog.lv3.org`
- updated `config/subdomain-catalog.json`
- updated `config/agent-tool-registry.json` (`get-deployment-history` tool)
- `docs/release-notes/`
- updated `changelog.md` (stripped to scratchpad + portal pointer)
- `docs/runbooks/deployment-history-portal.md`
- updated `Makefile`
- `docs/adr/0081-platform-changelog-and-deployment-history.md`
- `docs/workstreams/adr-0081-changelog-portal.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `https://changelog.lv3.org` serving the deployment history portal after a deliberate apply from `main`
- `get-deployment-history` tool callable via agent tool registry

## Verification

- `make generate-changelog-portal` produces `build/changelog-portal/index.html` with at least 20 entries from existing receipts
- per-service view for grafana shows all receipts mentioning grafana
- `changelog.lv3.org` serves the static portal with Keycloak auth gate
- `get-deployment-history` tool returns structured JSON for a query of `service_id=grafana, days=30`

## Merge Criteria

- all existing live-apply receipts appear in the timeline (no gaps)
- Loki unavailability causes graceful fallback to receipt-only mode with a visible banner in the portal
- the `docs/release-notes/` migration is complete and `changelog.md` links to the portal
- the agent tool returns valid JSON matching the documented output schema

## Notes For The Next Assistant

- share the HTML generation utilities with the ops portal generator (ADR 0074) — extract a common `scripts/portal_utils.py` module rather than duplicating HTML rendering logic
- the Loki query for audit events should use a short timeout (10 seconds) and fail gracefully; most of the value is in the structured receipt files which are always available without a live Loki instance
- parse receipts in parallel (concurrent file reads) to keep generation fast as the receipt count grows

## Outcome

- repository implementation is complete on `main`
- live publication and TLS verification for `changelog.lv3.org` completed on platform version `0.40.0`
