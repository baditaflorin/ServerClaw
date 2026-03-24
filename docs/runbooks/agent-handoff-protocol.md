# Agent Handoff Protocol

## Purpose

Use the repository-managed handoff subsystem when one agent, workflow, or operator needs to transfer task ownership to another actor without losing the task context.

## Runtime Surfaces

- Python package: `platform/handoff/`
- CLI surface: `lv3 handoff ...`
- Durable store: `handoff.transfers` or the repo-local sqlite fallback
- Optional operator notification webhook: `LV3_HANDOFF_OPERATOR_WEBHOOK_URL`

## Default Local Store

If `LV3_HANDOFF_DSN` is unset, the CLI uses:

```bash
sqlite:///<repo>/.local/state/handoffs.sqlite3
```

This is appropriate for local testing and controller-side coordination.

## Primary Commands

Create a handoff:

```bash
lv3 handoff send \
  --from-agent agent/triage-loop \
  --to-agent agent/runbook-executor \
  --task incident:inc-2026-03-24-netbox-001 \
  --subject "Run remediation workflow" \
  --payload-json '{"workflow_id":"converge-netbox"}' \
  --requires-accept
```

List current handoffs:

```bash
lv3 handoff list --task incident:inc-2026-03-24-netbox-001
```

Accept an operator escalation:

```bash
lv3 handoff accept <handoff-id> --actor operator --estimate-seconds 300
```

Refuse a handoff:

```bash
lv3 handoff refuse <handoff-id> --actor operator --reason capability_exceeded
```

Mark work complete after acceptance:

```bash
lv3 handoff complete <handoff-id> --actor agent/runbook-executor
```

Inspect one transfer as JSON:

```bash
lv3 handoff view <handoff-id>
```

## Environment

- `LV3_HANDOFF_DSN`: database DSN for durable handoff records
- `LV3_LEDGER_DSN` or `LV3_LEDGER_FILE`: optional ledger sink for handoff audit events
- `LV3_HANDOFF_OPERATOR_WEBHOOK_URL`: optional webhook used when a timeout or explicit fallback escalates to an operator

## Verification

Run the focused protocol tests:

```bash
uv run --with pytest python -m pytest tests/unit/test_handoff_protocol.py tests/test_lv3_cli.py -q
```

Check syntax for the runtime surfaces:

```bash
python3 -m py_compile platform/handoff/core.py scripts/lv3_cli.py
```

## Notes

- The repository implementation is transport-agnostic. The tests use the in-memory bus so retries, timeouts, and concurrent bursts are deterministic.
- When the recipient is `operator`, the durable transfer is still created even if no webhook is configured.
- `fallback=operator` preserves the transfer instead of closing it, so an operator can accept it later.
