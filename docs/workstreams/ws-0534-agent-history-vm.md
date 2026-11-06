# WS-0534: Dedicated guest for the agent-history store (git only)

## Status

In progress. The pull request is open and not merged; nothing was applied. No `[live-apply]` marker, no receipt, no version bump.

## Goal

ADR 0494: the agent-history store (Postgres 17 with pgvector and agent-store, with a collector, a query CLI and a redaction library on the operator laptops) runs on its own guest `agent-history` (vmid 155, 10.10.10.55) with an encrypted data volume, secrets delivered by OpenBao and tailnet-only exposure. This workstream declares the guest and everything the repository needs to know about it, so a later, owner-approved provisioning is one reviewed command.

## Change

- `docs/adr/0494-agent-history.md` and the regenerated ADR index.
- `inventory/host_vars/proxmox-host.yml`: the guest entry (4 vCPU, 8192 MiB, 24 GiB + 128 GiB, pinned MAC), `network_policy.guests.agent-history`, an OpenBao rule on `runtime-control`, and `platform_service_topology.agent_history`. `inventory/hosts.yml` regenerated. `config/network-policy/0mcp.yaml`: VM 155 and the same OpenBao flow for the netpolicy drift check.
- `inventory/group_vars/all/platform_services.yml`: the service registry block (`image_catalog_key: ""`, `needs_openbao: false`, with the reason).
- The planned-guest guard (`lifecycle: planned`): `playbooks/proxmox-install.yml` (and its collection copy) default guest set, the `proxmox_guests` role assertion, `scripts/generate_inventory.py` (`planned_guests` group and `!planned_guests` in the group patterns), `platform/ansible/execution_scopes.py` (scoped runs never return a planned guest), and tests: `tests/test_planned_guests.py`, additions to `tests/test_generate_inventory.py` and `tests/test_ansible_execution_scopes.py`.
- `config/tailscale/policy.hujson`: `tag:agent-history` (owners `group:admins` plus a temporary `tag:pool-runtime`, the 0pipe two-step), one grant (the four operator Macs and `ubuntuvm1`, 100.64.0.7, to the tag on `tcp:443`, by exact address) and two policy tests (accept 443; deny 22, 5432, 8080, 9100). Merging does not apply it: a new tag is a section change the CT108 reconciler marks `blocked`, so a human applies it after the merge, then a follow-up change removes the temporary co-owner.
- `playbooks/agent-history-vm.yml` and `make provision-agent-history-vm` (plus `syntax-check-agent-history-vm`, the workflow and command catalog entries and the execution scope). The play limits `proxmox_guests_active` to vmid 155 and asserts it; it is not reachable from `make provision-guests`.
- `collections/ansible_collections/lv3/platform/roles/agent_history_runtime`: Docker compose project (Postgres with pgvector, agent-store, an OpenBao Agent), LUKS2 data volume with an unlock helper and an immutable empty mount point, token files rendered from OpenBao onto tmpfs (no secret value anywhere in git), `tailscale serve` for the loopback listener, a metrics bridge and an optional canary database scan.
- `scripts/service_completeness.py` and its test: **a fix the gate forced.** In a remote validation snapshot (no Git), the completeness check scopes a changed aggregate catalog to the changed service bundles, but it looked the bundle directory name (`agent_history`) up in a map keyed by the hyphenated slug (`agent-history`), so every multi-word service fell back to validating all 79 services, 42 of which have legacy gaps. All 24 existing multi-word services use underscore directories, so this never ran before. The lookup now normalises underscores, and `config/dependency-graph.json` joins the catalogs that are built from the bundles (a change is attributed to the changed bundles; with no bundle changed it stays global). `build/platform-manifest.json` is regenerated (the new workflow).
- `catalog/services/agent_history/service.yaml` and the regenerated aggregate catalogs; `config/capacity-model.json`; `config/publication-sanitization.yaml`; `docs/runbooks/configure-agent-history.md`.

## What merging does and does not do

Does: put the declarations above on `main`. Does not: create the VM, run any playbook, or change the hypervisor, OpenBao, the tailnet as it is running (the policy file changes in git; a human applies it), Prometheus or any laptop, pin or scan an image, or deploy.

**The declaration is inert until the owner activates it.** VM 155 is declared `lifecycle: planned`: the default guest set of `proxmox-install.yml` (`make provision-guests`, bootstrap) skips it, the guests role refuses a planned guest in any selection (including the empty-selection fallback to every declared guest), the inventory puts it in `planned_guests` (and it stays in `lv3_guests`), every scoped run and the scoped host patterns exclude that group, and `make provision-agent-history-vm` refuses to run. The owner's activation is one reviewed change: delete the `lifecycle: planned` line and run `make generate-inventory`; its description is the recorded approval of the capacity decision.

## Verification

- The repository pre-push gate on the build server (`scripts/remote_exec.sh pre-push-gate`, no local fallback).
- `lv3 validate --service agent_history` equivalent: service completeness for the new bundle.
- Not verified, because nothing may be applied: the role has never run on a guest; `tailscale serve --https` syntax and certificate availability, the OpenBao Agent template options (`perms`, `error_on_missing_key`), the Debian node exporter default textfile directory on this guest, and whether Prometheus discovers the guest's exporter.

## Questions (numbers from the planning notes)

Answered by the owner on 2026-10-29 and reflected in the ADR and the runbook: 1 capacity (wait for the 0pipe migration and re-measure; VM 130 was trimmed live from 20 to 10 GiB on 2026-10-29 and `MemAvailable` went from 10.4 to 15.5 GiB, which is not yet the 24-hour minimum and is below the 15 % guard, so **a written exception to the 15 % guard is still needed** unless the migration changes that; `drop_caches` and the VM 171 and VM 200 trims are only a fallback; VM 180 never), 4 a new tag `tag:agent-history` and HTTPS certificates enabled (the tag, the one grant and two policy tests are in this change; a human applies them after the merge with `scripts/tailscale-policy-ct108.sh plan` and `apply`), 5 the hub's traffic reaches the store from `ubuntuvm1` (100.64.0.7, `0docker_docker`), 15 the controller is the `platform_server` checkout whose `.local/active-deployment` is `0mcp`, 16 warning only (the alert rules are a separate pull request).

Still open: 7 OpenBao AppRole and paths (the owner's step at provisioning); the written capacity exception; 6 the manual unlock, no swap and no log shipping; 12 the weekly restore drill; 13 the pilot's end date; 14 where embeddings run (a Mac; the store's embed flags are empty placeholders).
