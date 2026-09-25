# ADR 0461: Atomic Receipt Write + Dangling-Receipt Gate

- Status: Accepted
- Implementation Status: Implemented (`write_receipt_atomic` helper + `--check-files` flag on `scripts/check_receipt_freshness.py`)
- Date: 2026-04-29
- Concern: data-integrity, half-applied-state, gate-completeness
- Tags: receipts, live-apply, gate, atomic-io
- Implements: improvement #6 from the 2026-04-29 reliability review
- Depends on: ADR 0446 (receipt freshness check)

---

## Context

PR [#71](https://github.com/baditaflorin/platform_server/pull/71)
(`coolify_runtime deployed on 0fork`) added `latest_receipts.coolify_runtime`
to `versions/stack.yaml` but never committed the corresponding
`receipts/live-applies/2026-04-28-coolify-0fork-runtime-live-apply.json`
file. The schema-validation gate failed for every subsequent push to
main between 2026-04-28 13:39 UTC and the ws-0448 reconstruction at
14:30 UTC. Operators on that window saw `Repository data model error:
versions/stack.yaml.latest_receipts references unknown receipt`
without any signal that the fix was "commit the missing JSON file."

Two failure modes underneath:

1. **Non-atomic receipt write.** A converge that crashes mid-write
   leaves a truncated JSON file. The next gate run reads partial JSON
   and fails with a parse error, not a "this receipt is incomplete"
   message.

2. **No pre-commit signal for dangling references.** Adding a slug to
   `latest_receipts` is a one-line `versions/stack.yaml` edit. Adding
   the matching JSON file is a separate `git add`. Forgetting the
   second step is invisible until the gate runs on the build server,
   which is hours later.

[ADR 0446](0446-phase2-multi-deployment-hardening.md) added staleness
checks but does NOT verify file existence — an entry in
`latest_receipts` whose JSON file does not exist is "fresh" by date
and silently passes ADR 0446's window check.

## Decision

### 1. `write_receipt_atomic(path, payload)` helper

Added to `scripts/check_receipt_freshness.py`. Pattern:

```python
fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
with os.fdopen(fd, "w") as fh:
    json.dump(payload, fh, indent=2, sort_keys=True)
    fh.flush()
    os.fsync(fh.fileno())
os.replace(tmp_str, path)  # atomic on POSIX + Windows
```

A crash between `fsync` and `replace` leaves the original file (or no
file) intact, never a half-written one. Other receipt-writing scripts
(`scripts/convergence_timer.py`, future converge primitives) should
import and call this helper instead of `path.write_text(...)`.

### 2. `find_dangling_receipts()` + `--check-files` flag

Same module exposes:

```python
def find_dangling_receipts(receipts: dict[str, str], receipt_dir: Path) -> list[tuple[str, str]]:
    """Return [(service, slug), ...] for slugs with no JSON file."""
```

CLI:

```bash
python3 scripts/check_receipt_freshness.py --check-files
```

Exits 1 with one stderr line per dangling reference, naming the
expected path so the operator can either commit the missing file or
revert the `latest_receipts` entry. Always exits non-zero on dangling
findings, regardless of `--strict` (the same way `--strict` operates
for stale receipts) — these are bugs, not advisory.

### Live signal

Running this against current main on 2026-04-29 surfaces **2
pre-existing dangling receipts**:

- `preview_environment` → `2026-03-27-adr-0185-ws-0185-live-apply-20260327t191234z`
- `staging_environment` → `2026-03-27-adr-0183-staging-live-apply`

Neither was reported by the existing gate. Both predate ws-0448. They
are out of scope for this ADR (operator action — either commit the
JSONs or revert the references), but their existence proves the
check is doing real work.

### Wiring (deferred to follow-up)

Adding `--check-files` to the pre-push gate's all-lane runner is a
one-line follow-up. Out of scope for this ADR so the noise from the
two pre-existing dangling receipts does not block unrelated PRs
during the operator-action window.

## Consequences

- Future PRs that add a `latest_receipts.<svc>` value without the
  matching JSON file are caught by `--check-files` once it's wired
  into the gate.
- Receipt-writing scripts can adopt the atomic helper to eliminate
  the half-written-file class of corruption.
- The two pre-existing dangling receipts become visible operator
  signal instead of latent gate fragility.

## References

- [ADR 0446 — Phase 2 Multi-Deployment Hardening](0446-phase2-multi-deployment-hardening.md) — baseline receipt-freshness check.
- [PR #71](https://github.com/baditaflorin/platform_server/pull/71) — the dangling-receipt incident this ADR closes.
- [ws-0448 postmortem](../postmortems/2026-04-28-ws-0448-deployment-connection-registry.md) — the recovery that surfaced the gap.
