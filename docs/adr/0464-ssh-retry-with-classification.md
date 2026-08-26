# ADR 0464: SSH Retry With Backoff + Failure Classification

- Status: Accepted
- Implementation Status: Implemented (`scripts/ssh_with_retry.py` wrapper + `receipts/ssh-failures/` receipt format)
- Date: 2026-04-29
- Concern: transient-failure-handling, incident-triage, gate-bypass-evidence
- Tags: ssh, retry, backoff, classification, receipts
- Implements: improvement #3 from the 2026-04-29 reliability review
- Depends on:
  - ADR 0461 (atomic receipt write)
  - `network_partition` reason code in `config/gate-bypass-waiver-catalog.json`

---

## Context

Today every SSH invocation in the convergence path is one-shot. A
flaky network hop, a momentarily-unreachable Proxmox host, or a
post-reboot banner-exchange race fails the entire converge after one
30-second timeout. There is no retry, no backoff, and no signal that
the failure was *transient* vs *configuration-rooted*.

The 2026-04-28 ops.example.org diagnostic spent ~30 minutes
distinguishing `Connection to UNKNOWN port 65535 timed out` (a banner
issue caused by a wrong jump host) from `Permission denied`
(authentication, real config bug). Both look identical from the
operator's terminal: "ssh failed."

What we want:

- Up to N retries with exponential backoff (with jitter) before a
  terminal failure.
- A classifier that turns ssh stderr into a structured failure type
  the rest of the platform can reason about.
- A receipt format that records every attempt's classification so
  incident triage has data to grep against.

The existing `network_partition` gate-bypass reason code already
hints at this taxonomy — but there's no machinery emitting events in
that taxonomy, so the operator has to type-classify by hand.

## Decision

`scripts/ssh_with_retry.py`:

- Drop-in wrapper for `ssh` invocations. Forwards everything after
  `--` to the underlying `ssh` binary.
- Up to `--retries` attempts (default 3, env override
  `LV3_SSH_RETRY_DEFAULT_RETRIES`).
- Exponential backoff between retries: `base * 2^(attempt-1)` seconds
  with `±50%` jitter, capped at `--max-delay` (default 10s).
- On any ssh failure, classifies stderr into one of:
  `auth_failure`, `banner_timeout`, `connection_refused`,
  `dns_failure`, `network_partition`, `host_key_mismatch`, `unknown`.
- When `--classify-receipts-dir <path>` is set AND at least one
  attempt failed, writes a receipt summarising every attempt and the
  final outcome. Atomic write per [ADR 0461](0461-atomic-receipt-write-and-dangling-check.md).
- Exit code mirrors the inner ssh's last exit code on terminal
  failure; returns 0 on success (even after retries); returns 2 on
  argparse errors.

### Failure classifier patterns

| Class                  | Stderr substring matched (case-insensitive)                                           |
|------------------------|----------------------------------------------------------------------------------------|
| `host_key_mismatch`    | `REMOTE HOST IDENTIFICATION HAS CHANGED`                                              |
| `auth_failure`         | `Permission denied`, `publickey,...`, `Authentication failed`                          |
| `banner_timeout`       | `Connection timed out during banner exchange`, `Connection to ... port ... timed out` |
| `connection_refused`   | `Connection refused`                                                                  |
| `dns_failure`          | `Could not resolve hostname`, `Name or service not known`, `Temporary failure in name resolution` |
| `network_partition`    | `No route to host`, `Network is unreachable`                                          |
| `unknown`              | (anything else)                                                                       |

Order matters — `host_key_mismatch` is checked first because the
warning text overlaps with `auth_failure` patterns in some ssh builds.

### Receipt format

```json
{
  "schema_version": "1.0.0",
  "target": "ops@10.10.10.92",
  "recorded_at": "2026-04-29T14:30:00+00:00",
  "attempts": [
    {
      "attempt": 1,
      "exit_code": 255,
      "classification": "banner_timeout",
      "stderr_excerpt": "Connection timed out during banner exchange",
      "sleep_before_next": 1.2
    },
    {
      "attempt": 2,
      "exit_code": 0,
      "classification": "unknown",
      "stderr_excerpt": ""
    }
  ],
  "final_outcome": "success"
}
```

The receipt is path-stable: `<safe_target>-<UTC ts>.json` under
`receipts/ssh-failures/`. Multiple receipts per host accumulate
(easy to grep for `banner_timeout` patterns over time).

### Composes cleanly with `network_partition` gate-bypass reason code

A converge that fails 3 retries with classification `network_partition`
gives the operator an evidence trail to attach when filing a
`network_partition` waiver in `config/gate-bypass-waiver-catalog.json`.
Receipt path goes into `GATE_BYPASS_SUBSTITUTE_EVIDENCE`.

### What this ADR explicitly defers

- **Replacing the convergence path's bare `ssh` calls with the
  wrapper.** That's a much wider surface (Ansible's
  `ProxyCommand`, `ansible_ssh_common_args`) and per-role review.
  ws-0467 ships only the leaf primitive.
- **Aggregating receipts into a `make doctor` signal.** The receipt
  format is stable; a `make doctor` workstream can read it.
- **Wiring into `make` targets.** Operators can call the wrapper
  directly today.

## Consequences

- A flaky-network failure that recovers within 1-2 backoff windows no
  longer fails the converge.
- An auth-failure (real config bug) is reported as `auth_failure` and
  not retried meaningfully — the wrapper still retries N times, but
  the receipt classification surfaces the cause clearly.
- Incident triage gets a grep-able artifact (`receipts/ssh-failures/`)
  that the existing receipt-search tooling already consumes.

## References

- [ADR 0461 — Atomic Receipt Write](0461-atomic-receipt-write-and-dangling-check.md)
- [ADR 0463 — Health-Probe Runner](0463-post-converge-health-probe.md) — same receipt-write pattern.
- `config/gate-bypass-waiver-catalog.json::reason_codes.network_partition` — the existing taxonomy this ADR populates.
