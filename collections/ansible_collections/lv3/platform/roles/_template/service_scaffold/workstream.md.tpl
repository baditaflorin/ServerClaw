# Workstream ADR @@ADR_ID@@: @@DISPLAY_NAME@@

- ADR: [ADR @@ADR_ID@@](../adr/@@ADR_FILENAME@@)
- Title: scaffold @@DISPLAY_NAME@@ across roles, playbooks, docs, and catalogs
- Status: ready
- Branch: `@@BRANCH_NAME@@`
- Worktree: `@@WORKTREE_PATH@@`
- Owner: codex
- Depends On: `adr-0062-role-composability`, `adr-0075-service-capability-catalog`, `adr-0076-subdomain-governance`, `adr-0077-compose-secrets-injection`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/@@ROLE_NAME@@`, `playbooks/@@PLAYBOOK_FILENAME@@`, `playbooks/services/@@PLAYBOOK_FILENAME@@`, `config/`, `inventory/host_vars/proxmox-host.yml`

## Scope

- refine the scaffolded role in `@@ROLE_PATH@@`
- complete the service catalog, health probe, secret, image, and subdomain entries
- remove all scaffold TODO markers before merge
- finish the ADR and runbook content for @@DISPLAY_NAME@@

## Verification

- `make validate-data-models`
- `ansible-playbook -i inventory/hosts.yml playbooks/@@PLAYBOOK_FILENAME@@ --syntax-check`

## Outcome

- TODO: record the final repo version and any live-apply status when this workstream is actually merged or applied
