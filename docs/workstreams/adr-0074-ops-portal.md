# Workstream ADR 0074: Platform Operations Portal

- ADR: [ADR 0074](../adr/0074-platform-operations-portal.md)
- Title: Generated static web portal for human navigation of all platform services, VMs, and runbooks
- Status: live_applied
- Branch: `codex/adr-0074-ops-portal`
- Worktree: `../proxmox_florin_server__adr_0074`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0076-subdomain-governance`, `adr-0056-keycloak-sso`, `adr-0021-nginx-edge-publication`
- Conflicts With: none
- Shared Surfaces: `scripts/generate_ops_portal.py`, `build/ops-portal/`, NGINX edge config, `Makefile`, `ops.lv3.org`

## Scope

- render a static operations portal from the canonical repo catalogs into `build/ops-portal/`
- implement the six portal views: Service Map, VM Inventory, DNS Map, Runbook Index, ADR Decision Log, Agent Capability Surface
- surface generation-time health from a snapshot when available, with direct probe fallback for deterministic local validation
- add generated-static publication support for `ops.lv3.org` in the public edge role
- add `make generate-ops-portal`, `make deploy-ops-portal`, and `make generate-status` integration
- keep live publication as a deliberate `main` apply, not a branch-local claim

## Non-Goals

- real-time browser-side health polling
- command execution or mutation from the portal
- claiming `ops.lv3.org` is live before the edge role is applied from `main`

## Expected Repo Surfaces

- `scripts/generate_ops_portal.py`
- `scripts/portal_utils.py`
- `tests/test_ops_portal.py`
- `tests/fixtures/ops_portal_health.json`
- `roles/public_edge_oidc_auth/`
- `build/ops-portal/` (gitignored, generated artifact)
- updated `roles/nginx_edge_publication`
- updated `Makefile`
- `docs/adr/0074-platform-operations-portal.md`
- `docs/runbooks/platform-operations-portal.md`
- `docs/workstreams/adr-0074-ops-portal.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `https://ops.lv3.org` serving the generated operations portal through the shared NGINX edge certificate
- Keycloak-backed auth gate on `ops.lv3.org` via `oauth2-proxy` running on `nginx-lv3`
- `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration` reachable through the same public edge for browser login

## Verification

- `make generate-ops-portal`
- `uvx --from pyyaml python scripts/generate_ops_portal.py --check`
- `uvx --from pyyaml python -m unittest discover -s tests -p 'test_*.py'`
- `make validate`

## Merge Criteria

- all six portal views render from repo-managed inputs
- portal generation is wired into repo validation and status generation
- generated-static edge publication support is present without claiming live rollout
- ADR and workstream metadata show repository implementation in release `0.69.0`

## Notes For The Next Assistant

- repository implementation is merged by `0.69.0`
- live publication and TLS verification completed on platform version `0.40.0`
- `nginx-lv3` now intentionally uses `proxmox_firewall_enabled: false`; leaving `firewall=1` on VM `110` reproduced a Proxmox bridge-path failure where public `80/443` SYNs reached `fwbr110i0` but never reached the guest kernel
- `docker-runtime-lv3` now explicitly allows TCP `8091` from `nginx-lv3`; without that rule, `ops.lv3.org` still published but redirected users into an unreachable `sso.lv3.org`
