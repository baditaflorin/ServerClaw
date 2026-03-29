# Workstream WS-0252: Route And DNS Publication Assertion Ledger Live Apply

- ADR: [ADR 0252](../adr/0252-route-and-dns-publication-assertion-ledger.md)
- Title: Live apply the route and DNS publication assertion ledger across the governed `lv3.org` drift set
- Status: live_applied
- Implemented In Repo Version: 0.177.66
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0252-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0252-live-apply`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication-at-the-nginx-edge`, `adr-0076-subdomain-governance-and-dns-lifecycle`, `adr-0139-subdomain-exposure-audit-and-registry`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0252-live-apply.md`, `docs/adr/0252-route-and-dns-publication-assertion-ledger.md`, `docs/adr/.index.yaml`, `docs/runbooks/subdomain-exposure-audit.md`, `docs/runbooks/subdomain-governance.md`, `docs/runbooks/configure-postgres-vm.md`, `docs/runbooks/configure-edge-publication.md`, `config/workflow-catalog.json`, `config/command-catalog.json`, `config/correction-loops.json`, `config/controller-local-secrets.json`, `config/ansible-execution-scopes.yaml`, `config/subdomain-catalog.json`, `config/subdomain-exposure-registry.json`, `docs/schema/subdomain-catalog.schema.json`, `docs/schema/subdomain-exposure-registry.schema.json`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/subdomain_catalog.py`, `scripts/subdomain_exposure_audit.py`, `config/windmill/scripts/subdomain-exposure-audit.py`, `Makefile`, `playbooks/route-dns-assertion-ledger.yml`, `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/`, `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/`, `collections/ansible_collections/lv3/platform/roles/proxmox_tailscale_proxy/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/vaultwarden_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/vaultwarden_runtime/tasks/main.yml`, `tests/test_subdomain_catalog.py`, `tests/test_subdomain_exposure_audit.py`, `tests/test_hetzner_dns_record_role.py`, `tests/test_hetzner_dns_records_role.py`, `tests/test_proxmox_tailscale_proxy_role.py`, `tests/test_vaultwarden_runtime_role.py`, `tests/test_edge_publication_makefile.py`, `receipts/subdomain-exposure-audit/`, `receipts/live-applies/`

## Scope

- extend the governed hostname catalog and exposure registry so route assertions
  explicitly model apex publication, record sets, tailnet targets, and evidence
  plans
- add a dedicated live mutation path that reconciles the ADR 0252 drift set in
  Hetzner DNS instead of relying on ad hoc provider edits
- re-run the public and private exposure audit after live apply and record one
  branch-local receipt that proves the platform change end to end
- complete protected integration surfaces only during the final merge-to-main
  step

## Expected Repo Surfaces

- `inventory/host_vars/proxmox_florin.yml`
- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/ansible-execution-scopes.yaml`
- `config/command-catalog.json`
- `config/controller-local-secrets.json`
- `config/correction-loops.json`
- `docs/schema/subdomain-catalog.schema.json`
- `docs/schema/subdomain-exposure-registry.schema.json`
- `scripts/subdomain_catalog.py`
- `scripts/subdomain_exposure_audit.py`
- `config/windmill/scripts/subdomain-exposure-audit.py`
- `Makefile`
- `playbooks/route-dns-assertion-ledger.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/record.yml`
- `docs/runbooks/subdomain-exposure-audit.md`
- `docs/runbooks/subdomain-governance.md`
- `docs/runbooks/configure-postgres-vm.md`
- `docs/adr/0252-route-and-dns-publication-assertion-ledger.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0252-live-apply.md`
- `docs/runbooks/configure-edge-publication.md`
- `workstreams.yaml`
- `collections/ansible_collections/lv3/platform/roles/proxmox_tailscale_proxy/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/vaultwarden_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/vaultwarden_runtime/tasks/main.yml`
- `tests/test_proxmox_tailscale_proxy_role.py`
- `tests/test_vaultwarden_runtime_role.py`
- `tests/test_edge_publication_makefile.py`
- `receipts/subdomain-exposure-audit/`
- `receipts/live-applies/2026-03-29-adr-0252-route-and-dns-publication-assertion-ledger-live-apply.json`

## Expected Live Surfaces

- Hetzner DNS for `lv3.org` matches the governed ADR 0252 record set for the
  apex, `mail.lv3.org`, `database.lv3.org`, and `vault.lv3.org`
- stale public records for the retired ADR 0252 drift set are removed from the
  zone
- the shared edge publication path exposes the catalogued informational apex and
  mail HTTPS surfaces with certificates that cover the declared hostnames
- the private database and vault routes remain reachable only through the
  declared Proxmox Tailscale target

## Verification Plan

- refresh generated artifacts with `make generate-platform-vars` and `uvx --from pyyaml --with jsonschema python scripts/subdomain_exposure_audit.py --write-registry`
- run the focused ADR 0252 regression slice plus repository validation gates
- apply `make route-dns-assertion-ledger` and any required edge publication
  converge from this isolated latest-`origin/main` worktree
- rerun `make subdomain-exposure-audit` and direct DNS, HTTP, and TLS spot
  checks before writing the live-apply receipt

## Live Apply Outcome

- `make route-dns-assertion-ledger` completed successfully and left the
  governed Hetzner DNS set aligned with ADR 0252: `lv3.org` and `mail.lv3.org`
  now resolve publicly to `65.108.75.123`, while `database.lv3.org` and
  `vault.lv3.org` resolve to the Proxmox host Tailscale target `100.64.0.1`
- the same live reconcile retired the stale apex `AAAA`, `autoconfig`, `notify`,
  and `www` records from the `lv3.org` zone
- `make converge-vaultwarden` completed successfully after this branch fixed the
  Proxmox Tailscale proxy socket replay and Vaultwarden Docker bridge/network
  recovery paths; `curl --cacert .local/step-ca/certs/root_ca.crt -Is
  https://vault.lv3.org/alive` now returns `HTTP/1.1 200 OK`
- `make configure-edge-publication` then re-expanded the shared `lv3-edge`
  Let's Encrypt certificate to cover `mail.lv3.org`; direct verification now
  returns `HTTP/2 200` for `https://mail.lv3.org` and shows `DNS:mail.lv3.org`
  in the live SAN set
- `make subdomain-exposure-audit` wrote audit run
  `d45fbd4e-f07a-4b07-8c94-5ba73cef0298` at `2026-03-29T00:04:34.903617Z`;
  the remaining findings are out-of-scope pre-existing drift on `git.lv3.org`
  and `registry.lv3.org`, not regressions in the ADR 0252 governed set

## Live Evidence

- live-apply receipt:
  `receipts/live-applies/2026-03-29-adr-0252-route-and-dns-publication-assertion-ledger-live-apply.json`
- final audit receipt:
  `receipts/subdomain-exposure-audit/20260329T000434Z.json`
- final direct probes:
  `dig +short lv3.org`, `dig +short mail.lv3.org`, `dig +short database.lv3.org`,
  `dig +short vault.lv3.org`, `curl -I https://mail.lv3.org`, `curl -I https://lv3.org`,
  and `curl --cacert .local/step-ca/certs/root_ca.crt -Is https://vault.lv3.org/alive`

## Mainline Integration Outcome

- repository version `0.177.66` now carries ADR 0252 on `main` without a
  platform-version bump; the current integrated baseline remains
  `0.130.46`, while this ADR first became true on platform version `0.130.43`
  during the verified live apply
- `versions/stack.yaml` now records the ADR 0252 live-apply receipt as the
  latest evidence for `route_dns_assertion_ledger`, `public_edge_publication`,
  and `vaultwarden`, and the generated README status surfaces now reflect the
  apex plus `mail.lv3.org` publication truth and the corrected database
  tailnet DNS evidence
- during diagnosis, direct Hetzner DNS API `PUT` and `POST` requests were used
  to inspect and partially correct provider state before the final idempotent
  `make route-dns-assertion-ledger` replay; that manual intervention remains
  recorded in the live-apply receipt as part of the permanent audit trail
- remaining for merge to `main`: none; this branch now contains the validated
  `0.177.66` release surfaces prepared for the final push to `origin/main`
