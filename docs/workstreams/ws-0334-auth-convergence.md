# Workstream ws-0334-auth-convergence: Integrate Open WebUI Into Keycloak-Backed Routine Operator Authentication

- ADR: [ADR 0341](../adr/0341-open-webui-keycloak-oidc-with-break-glass-fallback.md)
- Title: Make Open WebUI use repo-managed Keycloak OIDC for routine sign-in while keeping local recovery
- Status: live_applied
- Branch: `codex/ws-0334-auth-convergence-clean`
- Worktree: `.worktrees/ws-0334-auth-convergence`
- Owner: codex
- Depends On: `adr-0056-keycloak-for-operator-and-agent-sso`, `adr-0060-open-webui-for-operator-and-agent-workbench`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/active/ws-0334-auth-convergence.yaml`, `docs/workstreams/ws-0334-auth-convergence.md`, `docs/adr/0341-open-webui-keycloak-oidc-with-break-glass-fallback.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-open-webui.md`, `docs/runbooks/configure-keycloak.md`, `playbooks/open-webui.yml`, `playbooks/keycloak.yml`, `collections/ansible_collections/lv3/platform/playbooks/open-webui.yml`, `roles/open_webui_runtime/**`, `roles/keycloak_runtime/defaults/main.yml`, `roles/keycloak_runtime/tasks/main.yml`, `roles/keycloak_runtime/tasks/open_webui_client.yml`, `collections/ansible_collections/lv3/platform/roles/open_webui_runtime/**`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/open_webui_client.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/postgres_vm/tasks/main.yml`, `inventory/group_vars/platform.yml`, `inventory/host_vars/proxmox_florin.yml`, `config/api-publication.json`, `config/command-catalog.json`, `config/controller-local-secrets.json`, `config/secret-catalog.json`, `config/service-capability-catalog.json`, `config/service-completeness.json`, `config/workflow-catalog.json`, `tests/test_docker_runtime_role.py`, `tests/test_keycloak_playbook.py`, `tests/test_keycloak_runtime_role.py`, `tests/test_open_webui_playbook.py`, `tests/test_open_webui_runtime_role.py`, `tests/test_postgres_vm_role.py`, `receipts/live-applies/2026-04-03-adr-0341-open-webui-keycloak-oidc-live-apply.json`

## Scope

- add a dedicated repo-managed Keycloak client for Open WebUI and mirror its client secret under `.local/keycloak/`
- make `playbooks/open-webui.yml` reconcile that Keycloak client before the runtime role needs the secret
- switch the Open WebUI runtime defaults from “OIDC later” to “OIDC enabled for routine access”
- retain the local bootstrap admin and password flow as a break-glass and verification path
- align the top-level Keycloak playbook and Keycloak service topology surfaces with the observed live Docker runtime placement so downstream OIDC clients and the public SSO edge converge against the same host
- harden the supporting apt-backed runtime roles so reruns can reuse recent package metadata instead of failing on transient cache refresh churn during auth convergence
- update service catalogs, workflow metadata, and runbooks so the new auth contract is explicit
- add regression tests for the Keycloak client task, the top-level Keycloak playbook and topology, the Open WebUI playbook, and the new runtime defaults

## Non-Goals

- no public-edge publication of Open WebUI; the workbench stays private behind the existing Proxmox host Tailscale proxy
- no attempt in this workstream to move `uptime.lv3.org` behind shared edge auth because the repo-managed Uptime Kuma Socket.IO client still depends on a separate management path that is not yet provisioned
- no broader host-placement migration for Keycloak or the mail platform; this workstream follows the observed live placement on `docker-runtime-lv3` so the Open WebUI client can converge against the current identity runtime

## Verification Plan

- add playbook tests that assert the Open WebUI converge surface now reconciles its dedicated Keycloak client before runtime deployment
- add playbook and topology tests that assert the top-level Keycloak converge surface and service map target `docker-runtime-lv3`
- extend Keycloak role tests to cover the new Open WebUI client defaults, secret mirroring, and standalone client task file
- extend Open WebUI runtime tests to cover OIDC-enabled defaults with retained local password fallback and OIDC login redirect verification
- extend the supporting runtime-role tests to lock the apt cache reuse guard that kept the live replay stable
- run focused pytest coverage for the changed playbook, role, and catalog surfaces
- run the relevant repo validation checks, including ADR index regeneration and workstream-surface validation
- apply `make converge-open-webui` against production and verify both the OIDC redirect path and local break-glass sign-in

## Expected Outcome

- operators use the existing Keycloak identity plane for normal Open WebUI sign-in
- Open WebUI no longer depends on a separately provided controller-local OIDC secret file
- the bootstrap admin remains available for recovery, smoke verification, and controlled break-glass access

## Current State

- clean source commits `37933c499` and `2d29892b0` now carry the full Open WebUI and Keycloak auth convergence on top of current `origin/main`
- production `make converge-open-webui` passed on 2026-04-03 with recap `docker-runtime-lv3 ok=273 changed=3 failed=0` and `proxmox_florin ok=40 changed=4 failed=0`
- public SSO discovery now returns `HTTP 200` from `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`
- Open WebUI now redirects `http://100.64.0.1:8008/oauth/oidc/login` to the Keycloak `open-webui` client on `sso.lv3.org`
- the break-glass login path still works at `http://100.64.0.1:8008/api/v1/auths/signin` for `ops@lv3.org`
- the canonical live evidence for this replay is `receipts/live-applies/2026-04-03-adr-0341-open-webui-keycloak-oidc-live-apply.json`
