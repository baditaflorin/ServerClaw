# Workstream ADR 0066: Structured Mutation Audit Log

- ADR: [ADR 0066](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0066-structured-mutation-audit-log.md)
- Title: Unified structured audit trail for all platform mutations across every governed surface
- Status: live_applied
- Branch: `codex/adr-0066-mutation-audit-log`
- Worktree: `../proxmox-host_server-mutation-audit-log`
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

- `{job="mutation-audit"}` Loki label populated for the verified host and runtime mutation sinks
- `/var/log/platform/mutation-audit.jsonl` on `proxmox-host` and `docker-runtime`
- OpenBao audit device enabled with `/opt/openbao/logs/audit.log` scraped by Alloy on `docker-runtime`

## Verification

- `scripts/mutation_audit.py --validate-schema`
- `scripts/mutation_audit.py --emit --actor-class operator --actor-id ops --surface manual --action document.manual_change --target proxmox-host --outcome success --evidence-ref docs/runbooks/mutation-audit-log.md`
- `scripts/command_catalog.py --check-approval --command configure-network --requester-class human_operator --approver-classes human_operator --validation-passed --preflight-passed --receipt-planned --audit-correlation-id test-0066 --audit-actor-id ops`
- `uvx --from pyyaml python scripts/validate_repository_data_models.py --validate`
- `python3 scripts/live_apply_receipts.py --validate`
- `make converge-monitoring`
- `make syntax-check-openbao`
- `make syntax-check-windmill`
- `make converge-windmill`
- `ansible -i inventory/hosts.yml proxmox-host -u ops --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -b -m shell -a 'test -s /var/log/platform/mutation-audit.jsonl && grep -q "/var/log/platform/mutation-audit.jsonl" /etc/alloy/config.alloy && systemctl is-active alloy'`
- `ansible -i inventory/hosts.yml docker-runtime -u ops --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -b -m shell -a 'test -s /var/log/platform/mutation-audit.jsonl && grep -q "/var/log/platform/mutation-audit.jsonl" /etc/alloy/config.alloy && grep -q "/opt/openbao/logs/audit.log" /etc/alloy/config.alloy && systemctl is-active alloy'`
- POST a live payload to `http://100.118.189.95:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fmutation_audit_emit` and verify correlation id `windmill:emit.mutation_audit_event:20260323T084527Z` lands in `docker-runtime:/var/log/platform/mutation-audit.jsonl`

## Merge Criteria

- the schema file is valid JSON Schema
- the callback plugin does not break existing playbook runs
- at least one full mutation cycle (plan → apply → receipt) produces a verifiable audit trail

## Notes For The Next Assistant

- the callback plugin must handle Ansible failure gracefully and not suppress the original error
- scrubbing of variable values tagged `no_log: true` is inherited from Ansible's existing behaviour; verify this is working before merging
- controller-side JSONL emission still defaults to `.local/state/mutation-audit/`, while host-local runtime sinks now live under `/var/log/platform/` and are shipped to Loki
- this workstream is merged to `main` in `0.78.0` and applied live on platform `0.37.0`
