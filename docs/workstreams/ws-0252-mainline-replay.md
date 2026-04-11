# Workstream ws-0252-mainline-replay

- ADR: [ADR 0252](../adr/0252-route-and-dns-publication-assertion-ledger.md)
- Title: Re-verify ADR 0252 from the latest `origin/main` and stage final merge surfaces
- Status: `live_applied`
- Included In Repo Version: 0.177.76
- Integrated Platform Version: 0.130.51
- Repo Version Observed During Replay: 0.177.72
- Platform Version Observed During Replay: 0.130.49
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0252-live-apply-r4`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0252-live-apply-r4`
- Owner: codex
- Depends On: `ws-0252-live-apply`

## Purpose

Replay ADR 0252 from the latest realistic `origin/main` baseline so the route
and DNS assertion ledger, shared edge publication, and private Vaultwarden path
are all re-verified from repository version `0.177.72` without changing the
original first-implementation truth recorded by ADR 0252.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0252-mainline-replay.md`
- `docs/workstreams/ws-0252-live-apply.md`
- `docs/runbooks/configure-vaultwarden.md`
- `receipts/live-applies/2026-03-29-adr-0252-route-and-dns-publication-assertion-ledger-mainline-live-apply.json`
- `receipts/subdomain-exposure-audit/20260329T112637Z.json`
- `docs/site-generated/architecture/dependency-graph.md`

## Verification

- `make generate-platform-vars` plus `uvx --from pyyaml --with jsonschema python scripts/subdomain_exposure_audit.py --write-registry` completed without committed contract drift.
- `uv run --with pytest --with pyyaml --with jsonschema --with jinja2 pytest -q tests/test_subdomain_catalog.py tests/test_subdomain_exposure_audit.py tests/test_hetzner_dns_record_role.py tests/test_hetzner_dns_records_role.py tests/test_proxmox_tailscale_proxy_role.py tests/test_vaultwarden_runtime_role.py tests/test_edge_publication_makefile.py tests/test_nginx_edge_publication_role.py tests/test_security_headers_audit.py` returned `59 passed in 3.02s`.
- `make route-dns-assertion-ledger` completed from the latest-main worktree with `localhost : ok=56 changed=0 failed=0 skipped=24`.
- `make configure-edge-publication` completed from the same worktree with `nginx-edge : ok=61 changed=3 failed=0 skipped=14`.
- `make converge-vaultwarden` completed successfully with `docker-runtime : ok=106 changed=5 failed=0 skipped=10`, `postgres : ok=42 changed=0 failed=0 skipped=7`, and `proxmox-host : ok=37 changed=4 failed=0 skipped=15`.
- `make subdomain-exposure-audit` wrote `receipts/subdomain-exposure-audit/20260329T112637Z.json`; the only remaining findings are the pre-existing `git.example.com` DNS warnings and the ADR 0252 governed apex, mail, database, and vault surfaces passed.
- `dig +short example.com` and `dig +short mail.example.com` both returned `203.0.113.1`, while `dig +short database.example.com` and `dig +short vault.example.com` both returned `100.64.0.1`.
- `curl -I https://mail.example.com` returned `HTTP/2 200`, `curl -I https://example.com` returned `HTTP/2 308` redirecting to `https://nginx.example.com/`, `tailscale ping -c 3 100.64.0.1` returned `pong`, and both `curl --http1.1 --insecure https://vault.example.com/alive` and `curl --http1.1 --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt --resolve vault.example.com:443:100.64.0.1 https://vault.example.com/alive` returned `200`.

## Outcome

- ADR 0252 remains first implemented in repo version `0.177.68` on platform version `0.130.43`; this replay re-verified the capability on the `0.177.72` / `0.130.49` mainline baseline and was later integrated into repo version `0.177.76` while the platform baseline had advanced to `0.130.51`.
- The new canonical latest-main receipt is `receipts/live-applies/2026-03-29-adr-0252-route-and-dns-publication-assertion-ledger-mainline-live-apply.json`.
- Release `0.177.76` now carries the exact-main replay onto `main`, and the canonical latest-receipt pointers for `public_edge_publication`, `route_dns_assertion_ledger`, and `vaultwarden` now point at the latest-main replay receipt rather than the earlier branch-local live-apply receipt.
