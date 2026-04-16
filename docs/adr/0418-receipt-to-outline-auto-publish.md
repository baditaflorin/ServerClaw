# ADR 0418: Automatic Receipt-to-Outline Publishing — Shared Utility and Coverage Gaps

**Date:** 2026-04-15
**Status:** Implemented
**Related:** ADR 0036 (Live Apply Receipts), ADR 0199 (Outline Living Wiki), ADR 0346 (Outline Programmatic API), ADR 0364 (Outline Agent Tools)

---

## Context

Platform scripts generate timestamped JSON receipt files under `receipts/` to
record evidence of operational activity: security scans, backup verifications,
TLS checks, subdomain audits, gate bypasses, and live-apply runs.

The `outline_tool.py receipt.publish` command converts any such receipt to
structured markdown and pushes it to the appropriate Outline collection,
making evidence surfaceable in the wiki at `wiki.example.com`.

As of 2026-04-15, **9 of the ~40 receipt-generating scripts** call an
inline `_publish_receipt_to_outline()` helper after writing a receipt.
The remaining ~30 scripts write receipts to disk but never push them to
Outline, so their evidence is invisible unless an operator manually runs
`receipt.backfill`.

### Current scripts WITH auto-publish

| Script | Receipt directory | Collection |
|--------|------------------|------------|
| `subdomain_exposure_audit.py` | `receipts/subdomain-exposure-audit/` | Security & Compliance |
| `https_tls_assurance.py` | `receipts/https-tls-assurance/` | Security & Compliance |
| `sbom_refresh.py` | `receipts/cve/`, `receipts/sbom/` | Security & Compliance |
| `security_posture_report.py` | `receipts/security-reports/` | Security & Compliance |
| `backup_coverage_ledger.py` | `receipts/backup-coverage/` | DR & Backup Status |
| `restic_config_backup.py` | `receipts/restore-verifications/` | DR & Backup Status |
| `restore_verification.py` | `receipts/restore-verifications/` | DR & Backup Status |
| `agent_coordination_snapshot.py` | `receipts/agent-coordination/` | Platform Findings |
| `log_gate_bypass.py` | `receipts/gate-bypasses/` | Gate Bypass Waivers |

### Current scripts WITHOUT auto-publish (sample)

`atlas_schema.py`, `capacity_report.py`, `container_image_policy.py`,
`convergence_timer.py`, `drift_detector.py`, `k6_load_testing.py`,
`live_apply_receipts.py`, `preview_environment.py`, `promotion_pipeline.py`,
`public_surface_scan.py`, `sbom_scanner.py`, `semgrep_gate.py`,
`slo_tracking.py`, `token_lifecycle.py`, `vulnerability_budget.py`, and
~15 more.

### Code-duplication problem

Every script that does auto-publish contains an identical ~20-line
`_publish_receipt_to_outline()` helper that:
1. Reads `OUTLINE_API_TOKEN` from env or `.local/outline/api-token.txt`
2. Calls `outline_tool.py receipt.publish --file <path>` as a subprocess
3. Swallows errors silently (best-effort, non-blocking)

Any improvement to this helper — e.g., adding a timeout, adding a retry,
or logging failures — must be made in 9 separate files.

---

## Decision

### Step 1 — Extract shared utility into `outline_client.py`

Add a module-level function to `scripts/outline_client.py`:

```python
def publish_receipt_to_outline(receipt_path: Path) -> None:
    """Best-effort: upload a receipt JSON file to Outline.

    Reads OUTLINE_API_TOKEN from env or .local/outline/api-token.txt.
    Silent on failure — never blocks the caller.
    """
    import subprocess, sys as _sys, os as _os
    token = _os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = receipt_path.resolve().parents[99] / ".local" / "outline" / "api-token.txt"
        # Walk up to find repo root (contains scripts/)
        candidate = Path(__file__).resolve().parents[1] / ".local" / "outline" / "api-token.txt"
        if candidate.exists():
            token = candidate.read_text(encoding="utf-8").strip()
    if not token or not receipt_path.exists():
        return
    outline_tool = Path(__file__).resolve().parent / "outline_tool.py"
    if not outline_tool.exists():
        return
    try:
        subprocess.run(
            [_sys.executable, str(outline_tool), "receipt.publish", "--file", str(receipt_path)],
            capture_output=True,
            check=False,
            timeout=30,
            env={**_os.environ, "OUTLINE_API_TOKEN": token},
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
```

Key improvement over the inline copies: adds a 30-second `timeout` so a
slow Outline API never hangs a script indefinitely.

### Step 2 — Replace inline copies in existing scripts

In each of the 9 scripts listed above, replace the local `_publish_receipt_to_outline`
function with an import and delegation:

```python
from outline_client import publish_receipt_to_outline
# ...
publish_receipt_to_outline(receipt_path)
```

### Step 3 — Add auto-publish to gap scripts

For each script that writes a receipt but currently lacks auto-publish, add:

```python
from outline_client import publish_receipt_to_outline
# ... after writing the receipt file:
publish_receipt_to_outline(receipt_path)
```

Priority order for implementation:
1. **High visibility** (already have Outline collections): `drift_detector.py`,
   `k6_load_testing.py`, `live_apply_receipts.py`, `semgrep_gate.py`
2. **Security posture**: `container_image_policy.py`, `sbom_scanner.py`,
   `vulnerability_budget.py`, `public_surface_scan.py`
3. **Operational evidence**: `convergence_timer.py`, `promotion_pipeline.py`,
   `preview_environment.py`, `token_lifecycle.py`
4. **Remaining**: all other scripts that call `write_json` to a `receipts/` path

### Step 4 — Add Makefile backfill targets

```makefile
# Backfill all existing receipts by category to their Outline collections
backfill-receipts-security:
    python3 scripts/outline_tool.py receipt.backfill \
        --collection "Security & Compliance" --receipt-dir receipts/subdomain-exposure-audit
    python3 scripts/outline_tool.py receipt.backfill \
        --collection "Security & Compliance" --receipt-dir receipts/https-tls-assurance
    python3 scripts/outline_tool.py receipt.backfill \
        --collection "Security & Compliance" --receipt-dir receipts/cve

backfill-receipts-dr:
    python3 scripts/outline_tool.py receipt.backfill \
        --collection "DR & Backup Status" --receipt-dir receipts/restore-verifications
    python3 scripts/outline_tool.py receipt.backfill \
        --collection "DR & Backup Status" --receipt-dir receipts/backup-coverage
```

### Step 5 — Document the convention in AGENTS.md

Add a "Programmatic Wiki Tools" subsection to `AGENTS.md` covering:
- `scripts/outline_tool.py` — CLI for document/collection management
- `scripts/outline_client.py` — shared API client + `publish_receipt_to_outline()`
- Convention: every script that writes to `receipts/` **must** call
  `publish_receipt_to_outline(receipt_path)` after writing

---

## Consequences

### Positive

- Evidence from all platform operations surfaces in Outline automatically
- Improvements to the publish flow (timeouts, retries, error logging) need
  only be made in one place
- New scripts get auto-publish by following a documented convention
- Agents can rely on Outline reflecting current operational state, not a
  manually-maintained subset

### Negative / Trade-offs

- `outline_client.py` grows a runtime dependency on `outline_tool.py` existing
  (this dependency already exists implicitly in every script)
- Scripts that previously had zero Outline dependency now silently depend
  on `.local/outline/api-token.txt` existing — this is safe because the
  function is silent on missing credentials

### Not in scope

- Changing the receipt JSON schema
- Adding receipt indexing or search
- Changing which Outline collection a receipt maps to
  (that logic lives in `outline_tool.py:_infer_collection_from_path`)

---

## Implementation Checklist

- [ ] Add `publish_receipt_to_outline()` to `scripts/outline_client.py`
- [ ] Replace inline copies in 9 existing scripts (import from `outline_client`)
- [ ] Add to high-priority gap scripts (Step 3, priority 1–2)
- [ ] Add to remaining gap scripts (Step 3, priority 3–4)
- [ ] Add Makefile `backfill-receipts-*` targets
- [ ] Update `AGENTS.md` with "Programmatic Wiki Tools" section
- [ ] Run `receipt.backfill` for all pre-existing receipts missing from Outline
- [ ] Verify: run `subdomain-exposure-audit` → check new doc appears in Outline
