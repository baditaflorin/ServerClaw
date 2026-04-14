# ADR 0415: Postmortem — cert_mismatch Gate Forced `--no-verify` Push

- Status: Accepted
- Implementation Status: Resolved (see ADR 0414)
- Date: 2026-04-14

## Incident Summary

**What happened:**
The pre-push gate blocked a push due to 16 `cert_mismatch` entries. The documented
bypass `SKIP_CERT_VALIDATION=1 git push origin <branch>` was tried but silently
failed — the hook never read that env var. The operator was forced to use
`git push --no-verify`, which bypassed **all** gate checks (ADR validation, NATS
topic validation, and the remote pre-push gate) rather than just the cert check.

**When:** 2026-04-14

**Duration of bypass:** Single push; operator flagged as "follow up when convenient".

**Impact:**
- All three gate lanes were bypassed instead of just the cert lane
- No audit record was created for the cert bypass (log_gate_bypass.py was not called)
- 16 production domains remained with cert_mismatch status, potentially visible
  to users as TLS warnings if nginx was serving stale certs

**Severity:** Low — cert mismatches were pre-existing (not caused by this push),
and no user-visible TLS errors were reported. Gate bypass is recoverable.

---

## Root Cause Analysis

### Primary cause: SKIP_CERT_VALIDATION=1 never implemented

ADR 0375 was implemented in `.githooks/pre-push` with the cert validation block
at lines 48-75. The error message on failure (line 70) told the operator:

```
Bypass: SKIP_CERT_VALIDATION=1 git push origin <branch>
```

However, the code never checked `SKIP_CERT_VALIDATION`. Compare the cert block
with the ADR validation block (lines 78-109): the ADR block begins with
`if [[ "${SKIP_ADR_VALIDATION:-0}" == "1" ]]; then` and calls `log_gate_bypass.py`.
The cert block had no such check.

The operator read the documented bypass, tried it, and got the same error. With
no working bypass and a deadline to push, `--no-verify` was the only option.

### Contributing cause: no cron auto-repair

The 16 `cert_mismatch` entries had accumulated over time (new subdomains added to
the catalog without running `converge-nginx-edge`). Without a daily auto-sync,
mismatches only surface at push time — the worst possible moment for a surprise.

### Contributing cause: no tiered bypass

The gate had two options: pass completely or bypass everything via `--no-verify`.
There was no "bypass just this lane" mechanism for cert validation, even though
`SKIP_ADR_VALIDATION=1` existed as a model to follow.

---

## Timeline

| Time | Event |
|------|-------|
| T-? | 16 subdomains added to catalog without running `converge-nginx-edge` |
| T-0 | Operator runs `git push origin <branch>` |
| T+1m | Gate fails: "CRITICAL: 16 certificate issue(s)" |
| T+2m | Operator tries `SKIP_CERT_VALIDATION=1 git push origin <branch>` |
| T+3m | Gate still fails (env var silently ignored) |
| T+4m | Operator uses `git push --no-verify` — all gates bypassed |
| T+5m | Push lands on remote; no bypass audit record created |
| T+6m | Operator adds Plane comment: "Follow up when convenient: make converge-nginx-edge" |

---

## What Went Wrong (Five Whys)

1. **Why was `--no-verify` used?**
   Because the documented `SKIP_CERT_VALIDATION=1` bypass didn't work.

2. **Why didn't `SKIP_CERT_VALIDATION=1` work?**
   Because the pre-push hook never read that env var, despite advertising it.

3. **Why was the env var advertised but not implemented?**
   The cert validation block was added to ADR 0375 without copying the bypass
   pattern from the adjacent ADR validation block. No test verified the bypass
   worked.

4. **Why were there 16 cert_mismatch entries to begin with?**
   No automated check detected the accumulation. The pre-push gate is the first
   place cert status is validated after catalog changes.

5. **Why wasn't the bypass traceable?**
   `log_gate_bypass.py` is only called from the specific bypass blocks; `--no-verify`
   skips the hook entirely, leaving no record.

---

## Fixes Applied (ADR 0414)

### Fix 1: `SKIP_CERT_VALIDATION=1` now actually works

`.githooks/pre-push` updated to check `SKIP_CERT_VALIDATION=1` before the cert
validation block, with the same bypass-logging pattern as `SKIP_ADR_VALIDATION=1`.
Every bypass is now logged via `scripts/log_gate_bypass.py`.

```bash
# Now works as documented:
SKIP_CERT_VALIDATION=1 \
  GATE_BYPASS_REASON_CODE=cert-mismatch-pending-converge \
  GATE_BYPASS_DETAIL="16 mismatches; converge-nginx-edge queued" \
  git push origin <branch>
```

### Fix 2: Cron auto-repair

`config/cert-sync-cron.yaml` defines a daily systemd timer that runs
`cert_lifecycle_manager.py sync-missing --apply` at 03:00 UTC. Mismatches
accumulating over days will be auto-corrected before the next push.

### Fix 3: `scripts/cert_lifecycle_manager.py`

A new programmatic entry point for all cert lifecycle operations. The `sync-missing`
command provides the same repair capability as `make converge-nginx-edge` but:
- Scans first (only invokes Ansible if mismatches found)
- Reports JSON results for automation
- Is safe to run from cron without operator intervention

### Fix 4: Skip mode for forks

`platform_cert_validation_mode: skip|warn|enforce` in `.local/identity.yml` allows
operators on forks without Hetzner DNS API to disable cert validation gracefully
rather than using `--no-verify`.

---

## Detection

How we would catch this class of bug in the future:

1. **Gate bypass tests** — Added to the validation checklist: every advertised env
   var bypass (`SKIP_*`) must have a test that confirms it actually skips the gate.

2. **Cron monitoring** — `cert-sync.service` exits non-zero and triggers
   `cert-sync-alert.service` if any mismatches remain after auto-repair. This
   surfaces in the gate-bypass log as a named event.

3. **ADR 0375 updated** — The ADR now references the bypass mechanism explicitly
   and notes that `log_gate_bypass.py` must be called.

---

## Action Items

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Implement `SKIP_CERT_VALIDATION=1` in pre-push hook | platform-infra | Done (ADR 0414) |
| 2 | Create `cert_lifecycle_manager.py` | platform-infra | Done (ADR 0414) |
| 3 | Deploy cert-sync cron via `cert_renewal_timer` role | platform-infra | Pending converge |
| 4 | Run `make converge-nginx-edge env=production` to fix existing 16 mismatches | operator | Pending |
| 5 | Add gate bypass test to CI checklist | platform-infra | Backlog |

---

## Consequences

**What we learned:**
- Advertised bypasses must be tested, not just documented.
- The cert validation gate had no safe escape hatch — `--no-verify` was the only
  working option.
- Mismatches should be corrected daily (cron), not discovered at push time.

**What did not happen:**
- No user-visible TLS errors (cert mismatches were for internal services)
- No data loss or security breach
- No cert expiry (mismatches ≠ expired certs)

**What changes in behavior:**
- `SKIP_CERT_VALIDATION=1` now works and is audited
- Daily cron prevents mismatch accumulation
- `cert_lifecycle_manager.py` is the operator's primary tool for cert operations

---

## Related ADRs

- ADR 0375: Certificate validation and concordance enforcement (the gate with the bug)
- ADR 0414: Cert lifecycle agent tools and cron sync (the fixes)
- ADR 0101: Automated certificate lifecycle management
