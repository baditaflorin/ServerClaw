# ADR 0466: Converge State Diff Receipts

- Status: Accepted
- Implementation Status: Implemented (`scripts/converge_state_receipt.py` with `snapshot` + `write-receipt` subcommands)
- Date: 2026-04-29
- Concern: half-applied-state, post-converge-verification
- Tags: converge, receipts, observability
- Implements: improvement #2 from the 2026-04-29 reliability review
- Depends on: ADR 0461 (atomic receipt write), ADR 0463 (post-converge health probes)

---

## Context

Today, Ansible's per-task `changed: true` signal tells you the role intended a change but does not tell you whether the resulting file matches the template's idempotent output, or whether the notify→handler chain actually fired. The 2026-04-28 nginx-buffer incident is the canonical case: the `lv3-edge.conf` template was rewritten with `proxy_buffer_size 64k`, but the `reload nginx` handler either didn't fire or failed silently, and there was no post-converge artifact to grep against.

A single `receipts/converge-state/<run_id>.json` per converge gives:

- **Before/after sha256 + size** of every managed file the role declared.
- **List of handlers that fired.**
- **List of handlers that were notified but skipped** (e.g. due to `--check`, `serial`, or a failing earlier task).

That signal turns "did the buffer reload actually happen" into a `jq` query rather than a stack-trace archaeology session.

## Decision

`scripts/converge_state_receipt.py`:

- `snapshot <path>...` — emit a JSON array of `{path, sha256, size_bytes}` (or `{path, missing: true}`) for the given paths. Roles call this twice: once before any changes, once after.
- `write-receipt --run-id ... --host ... --role ... --before <json> --after <json> --handlers-fired ... --handlers-notified-but-skipped ...` — diff the two snapshots, build a receipt, write atomically per ADR 0461 to `receipts/converge-state/<run_id>.json`.

Receipt schema:

```json
{
  "schema_version": "1.0.0",
  "run_id": "manual-1714382400",
  "host": "nginx",
  "role": "nginx_edge_publication",
  "recorded_at": "2026-04-29T14:30:00+00:00",
  "files": [
    {
      "path": "/etc/nginx/sites-available/lv3-edge.conf",
      "before_sha256": "8d4d...",
      "after_sha256": "0592...",
      "before_missing": false,
      "after_missing": false,
      "changed": true,
      "size_bytes_before": 32944,
      "size_bytes_after": 33080
    }
  ],
  "handlers_fired": ["reload nginx"],
  "handlers_notified_but_skipped": [],
  "summary": {
    "files_total": 1,
    "files_changed": 1,
    "handlers_fired": 1,
    "handlers_skipped": 0
  }
}
```

### What this ADR explicitly defers

- **Wiring into role tasks.** Each role declares its managed file list and calls the script. That's per-role review territory; ws-0468 only ships the leaf primitive.
- **A `make doctor` signal that flags files-changed-but-handler-not-fired.** Builds on this receipt format.
- **Aggregation into the ops portal.**

## Consequences

- Roles that opt in get a stable, grep-able artifact per converge.
- The "did the reload actually happen" question becomes a 1-line `jq`.
- Receipt format is forward-compatible with later doctor signals.

## References

- [ADR 0461 — Atomic Receipt Write](0461-atomic-receipt-write-and-dangling-check.md)
- [ADR 0463 — Health-Probe Runner](0463-post-converge-health-probe.md)
- 2026-04-28 ops.0fork.com 500 incident — the failure mode this ADR closes.
