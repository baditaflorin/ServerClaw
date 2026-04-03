# Workstream ws-0334-auth-convergence: Integrate Open WebUI Into Keycloak-Backed Routine Operator Authentication

- ADR: [ADR 0341](../adr/0341-open-webui-keycloak-oidc-with-break-glass-fallback.md)
- Title: Make Open WebUI use repo-managed Keycloak OIDC for routine sign-in while keeping local recovery
- Status: in_progress
- Branch: `codex/ws-0334-auth-convergence`
- Worktree: `.worktrees/ws-0334-auth-convergence`
- Owner: codex
- Depends On: `adr-0056-keycloak-for-operator-and-agent-sso`, `adr-0060-open-webui-for-operator-and-agent-workbench`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0334-auth-convergence.md`, `docs/adr/0341-open-webui-keycloak-oidc-with-break-glass-fallback.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-open-webui.md`, `docs/runbooks/configure-keycloak.md`, `playbooks/open-webui.yml`, `collections/ansible_collections/lv3/platform/playbooks/open-webui.yml`, `roles/open_webui_runtime/**`, `roles/keycloak_runtime/defaults/main.yml`, `roles/keycloak_runtime/tasks/main.yml`, `roles/keycloak_runtime/tasks/open_webui_client.yml`, `collections/ansible_collections/lv3/platform/roles/open_webui_runtime/**`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/open_webui_client.yml`, `config/api-publication.json`, `config/command-catalog.json`, `config/controller-local-secrets.json`, `config/secret-catalog.json`, `config/service-capability-catalog.json`, `config/service-completeness.json`, `config/workflow-catalog.json`, `tests/test_keycloak_runtime_role.py`, `tests/test_open_webui_playbook.py`, `tests/test_open_webui_runtime_role.py`

## Scope

- add a dedicated repo-managed Keycloak client for Open WebUI and mirror its client secret under `.local/keycloak/`
- make `playbooks/open-webui.yml` reconcile that Keycloak client before the runtime role needs the secret
- switch the Open WebUI runtime defaults from “OIDC later” to “OIDC enabled for routine access”
- retain the local bootstrap admin and password flow as a break-glass and verification path
- update service catalogs, workflow metadata, and runbooks so the new auth contract is explicit
- add regression tests for the Keycloak client task, the Open WebUI playbook, and the new runtime defaults

## Non-Goals

- no public-edge publication of Open WebUI; the workbench stays private behind the existing Proxmox host Tailscale proxy
- no attempt in this workstream to move `uptime.lv3.org` behind shared edge auth because the repo-managed Uptime Kuma Socket.IO client still depends on a separate management path that is not yet provisioned
- no live apply; this workstream targets a repo merge and test coverage only

## Verification Plan

- add playbook tests that assert the Open WebUI converge surface now reconciles its dedicated Keycloak client before runtime deployment
- extend Keycloak role tests to cover the new Open WebUI client defaults, secret mirroring, and standalone client task file
- extend Open WebUI runtime tests to cover OIDC-enabled defaults with retained local password fallback and OIDC login redirect verification
- run focused pytest coverage for the changed playbook, role, and catalog surfaces
- run the relevant repo validation checks, including ADR index regeneration and workstream-surface validation

## Expected Outcome

- operators use the existing Keycloak identity plane for normal Open WebUI sign-in
- Open WebUI no longer depends on a separately provided controller-local OIDC secret file
- the bootstrap admin remains available for recovery, smoke verification, and controlled break-glass access
