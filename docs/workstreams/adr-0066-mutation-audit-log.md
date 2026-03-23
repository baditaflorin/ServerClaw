# Workstream ADR 0066: Structured Mutation Audit Log

- ADR: [ADR 0066](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0066-structured-mutation-audit-log.md)
- Title: Unified structured audit trail for all platform mutations across every governed surface
- Status: ready
- Branch: `codex/adr-0066-mutation-audit-log`
- Worktree: `../proxmox_florin_server-mutation-audit-log`
- Owner: codex
- Depends On: `adr-0052-loki-logs`, `adr-0048-command-catalog`, `adr-0044-windmill`, `adr-0043-openbao`
- Conflicts With: none
- Shared Surfaces: Ansible callback plugins, Loki, Windmill workflows, command-catalog, OpenBao audit device

## Scope

- define `docs/schema/mutation-audit-event.json` event schema
- implement `callback_plugins/mutation_audit.py` Ansible callback plugin
- configure OpenBao audit device to forward to Loki
- add audit emit calls to Windmill workflow template
- add audit emit to command-catalog approval and execution paths
- document the audit model in `docs/runbooks/mutation-audit-log.md`

## Non-Goals

- compliance-grade immutable audit storage
- auditing read-only operations

## Expected Repo Surfaces

- `docs/schema/mutation-audit-event.json`
- `scripts/mutation_audit.py`
- `callback_plugins/mutation_audit.py`
- `docs/runbooks/mutation-audit-log.md`
- `config/windmill/scripts/lv3-mutation-audit.py`
- `ansible.cfg`
- updated Windmill workflow template
- updated command-catalog scripts
- `docs/adr/0066-structured-mutation-audit-log.md`
- `docs/workstreams/adr-0066-mutation-audit-log.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `{job="mutation-audit"}` Loki label populated on every governed mutation
- `/var/log/platform/mutation-audit.jsonl` on the Proxmox host
- OpenBao audit device enabled and forwarding

## Verification

- `scripts/mutation_audit.py --validate-schema`
- `scripts/mutation_audit.py --emit --actor-class operator --actor-id ops --surface manual --action document.manual_change --target proxmox_florin --outcome success --evidence-ref docs/runbooks/mutation-audit-log.md`
- `scripts/command_catalog.py --check-approval --command configure-network --requester-class human_operator --approver-classes human_operator --validation-passed --preflight-passed --receipt-planned --audit-correlation-id test-0066 --audit-actor-id ops`
- `make syntax-check-openbao`
- `make syntax-check-windmill`
- trigger a test Ansible play with a `mutation`-tagged task and verify the event appears in Loki
- `test -f /var/log/platform/mutation-audit.jsonl` on the host after first emission

## Merge Criteria

- the schema file is valid JSON Schema
- the callback plugin does not break existing playbook runs
- at least one full mutation cycle (plan → apply → receipt) produces a verifiable audit trail

## Notes For The Next Assistant

- the callback plugin must handle Ansible failure gracefully and not suppress the original error
- scrubbing of variable values tagged `no_log: true` is inherited from Ansible's existing behaviour; verify this is working before merging
- controller-side JSONL emission still defaults to `.local/state/mutation-audit/`, while host-local runtime sinks now live under `/var/log/platform/` and are shipped to Loki
