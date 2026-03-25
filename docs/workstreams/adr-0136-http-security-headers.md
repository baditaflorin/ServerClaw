# Workstream ADR 0136: HTTP Security Headers Hardening

- ADR: [ADR 0136](../adr/0136-http-security-headers-hardening.md)
- Title: Harden browser-facing HTTP response headers on every public-edge hostname
- Status: live_applied
- Branch: `codex/adr-0136-http-security-headers`
- Worktree: `.worktrees/adr-0136`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0133-portal-auth-by-default`
- Conflicts With: none
- Shared Surfaces: `roles/nginx_edge_publication/`, `inventory/group_vars/platform.yml`, `scripts/`, `docs/runbooks/`, `README.md`, `VERSION`, `versions/stack.yaml`

## Scope

- add repo-managed HTTP response headers to the public edge role
- support per-host CSP overrides for current public applications
- add a repeatable audit command for live header verification
- update the ADR and release metadata once the change is merged and applied from `main`

## Non-Goals

- broader public-surface scanning beyond HTTP response headers
- replacing third-party applications whose CSP needs are currently relaxed
- changing mail-port or non-HTTP exposure policy

## Expected Repo Surfaces

- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2`
- `scripts/security_headers_audit.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_security_headers_audit.py`
- `docs/runbooks/http-security-headers.md`
- `docs/adr/0136-http-security-headers-hardening.md`
- `docs/workstreams/adr-0136-http-security-headers.md`

## Expected Live Surfaces

- every public-edge hostname serves HSTS, CORP, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, and X-Robots-Tag
- `make security-headers-audit` passes against the live platform after apply

## Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_nginx_edge_publication_role.py tests/test_security_headers_audit.py`
- `python3 -m py_compile scripts/security_headers_audit.py`
- `make security-headers-audit`

## Merge Criteria

- the edge role renders the required headers without regressing current published apps
- CSP exceptions are explicit and limited to the hostnames that need them
- the audit command passes against the live platform after the public-edge rollout
- ADR 0136 and the integrated release metadata record the repo and live implementation truth

## Notes For The Next Assistant

- `docs.lv3.org`, `ops.lv3.org`, `grafana.lv3.org`, `uptime.lv3.org`, `status.lv3.org`, and `sso.lv3.org` now have host-specific CSP overrides derived from their current live HTML payloads.
- The live rollout converged from `Check whether the public edge certificate exists` onward after the full `make live-apply-service service=public-edge env=production` path stalled in static-site copy steps inside the integration worktree.
