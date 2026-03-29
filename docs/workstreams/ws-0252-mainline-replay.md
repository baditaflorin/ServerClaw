# Workstream ws-0252-mainline-replay

- ADR: [ADR 0252](../adr/0252-route-and-dns-publication-assertion-ledger.md)
- Title: Re-verify ADR 0252 from the latest `origin/main` and stage final merge surfaces
- Status: in_progress (`live_applied: true`, awaiting merge to `main`)
- Repo Version Observed During Replay: 0.177.72
- Platform Version Observed During Replay: 0.130.49
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0252-live-apply-r4`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0252-live-apply-r4`
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
- `make configure-edge-publication` completed from the same worktree with `nginx-lv3 : ok=61 changed=3 failed=0 skipped=14`.
- `make converge-vaultwarden` completed successfully with `docker-runtime-lv3 : ok=106 changed=5 failed=0 skipped=10`, `postgres-lv3 : ok=42 changed=0 failed=0 skipped=7`, and `proxmox_florin : ok=37 changed=4 failed=0 skipped=15`.
- `make subdomain-exposure-audit` wrote `receipts/subdomain-exposure-audit/20260329T112637Z.json`; the only remaining findings are the pre-existing `git.lv3.org` DNS warnings and the ADR 0252 governed apex, mail, database, and vault surfaces passed.
- `dig +short lv3.org` and `dig +short mail.lv3.org` both returned `65.108.75.123`, while `dig +short database.lv3.org` and `dig +short vault.lv3.org` both returned `100.64.0.1`.
- `curl -I https://mail.lv3.org` returned `HTTP/2 200`, `curl -I https://lv3.org` returned `HTTP/2 308` redirecting to `https://nginx.lv3.org/`, `tailscale ping -c 3 100.64.0.1` returned `pong`, and both `curl --http1.1 --insecure https://vault.lv3.org/alive` and `curl --http1.1 --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt --resolve vault.lv3.org:443:100.64.0.1 https://vault.lv3.org/alive` returned `200`.

## Outcome

- ADR 0252 remains first implemented in repo version `0.177.68` on platform version `0.130.43`; this replay only re-verifies the capability on the newer `0.177.72` / `0.130.49` mainline baseline.
- The new canonical latest-main receipt is `receipts/live-applies/2026-03-29-adr-0252-route-and-dns-publication-assertion-ledger-mainline-live-apply.json`.
- Remaining for merge to `main`: update the protected release and canonical-truth surfaces so they point at the latest-main replay receipt rather than the earlier branch-local live-apply receipt, and carry forward the exact-main docs portal metadata refresh from the shared edge rebuild.
