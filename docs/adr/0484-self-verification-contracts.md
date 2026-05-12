# ADR 0484: Self-Verification Contracts

**Status**: ACCEPTED
**Date**: 2026-05-12
**Decision**: Every state-changing step in the platform (every `converge-*`, `provision-guests`, `live-apply-*`, `bootstrap`) ships an explicit, machine-checkable post-condition declared in a committed registry. The post-condition is what "this step succeeded" means — not the exit code of the playbook, not the absence of red logs, but a declarative invariant that an independent verifier can run.

---

## Context

### The 0fork Harbor incident, in one paragraph

On 2026-05-06, `harbor_runtime`'s `nginx` + `harbor-portal` containers exited with code 128 from a transient harbor-log syslog driver hiccup. `restart: always` doesn't fire on container-creation errors, so they stayed exited. Nothing surfaced this for **five days**. The most recent `converge-harbor` run had exited 0. The most recent `live-apply` receipt said "harbor deployed and verified UP." Both were technically true at the moment they were written. Neither caught the silent regression.

### Root cause

The platform's definition of "step succeeded" was operational ("ansible exited 0", "the playbook didn't raise"), not contractual ("the post-state matches the declared invariant"). Once the converge had run, no part of the system was *asking* whether Harbor was actually serving requests.

### Why ADR 0481 / 0482 don't fix this

- ADR 0481 makes deployment context explicit. Doesn't say what "deployed" means.
- ADR 0482 makes sizing dynamic. Doesn't say what "verified" means.

ADR 0483 declares that bootstrap is gated by post-conditions. This ADR specifies **what a post-condition is, where it lives, how it runs, and what guarantees it provides.**

---

## Decision

### 1. A post-condition is a structured assertion

Every check is one entry in `config/post_conditions.yml` (committed):

```yaml
post_conditions:
  - id: harbor.registry.public-ping
    description: registry.<apex>/api/v2.0/ping returns Pong over TLS
    after_step: converge-harbor
    type: http
    url: "https://registry.{apex}/api/v2.0/ping"
    expect_status: 200
    expect_body_contains: "Pong"
    timeout_s: 10
    retries: 3
    retry_backoff_s: 5
    critical: true
```

Fields:

| Field | Meaning |
|---|---|
| `id` | Globally unique. Referenced by step records, receipts, dashboards. |
| `description` | One human-readable line. Shown in failure messages. |
| `after_step` | Which step's post-condition this is. Drives "what to check after X." |
| `type` | One of: `http`, `tcp`, `tls`, `dns`, `pveapi`, `docker`, `file`, `command`. Extensible via `scripts/self_check.py` plugins. |
| `expect_*` | Type-specific expectations. Required. |
| `timeout_s` / `retries` / `retry_backoff_s` | Knobs the runner honours; non-flakiness contract is "≤ retries failures means *real* failure". |
| `critical` | When true, failure blocks downstream steps. When false, failure is recorded as a warning. |

### 2. Eight check types, no more (initial set)

Adding a check type means adding a plugin to `scripts/self_check.py`. The MVP set:

| Type | What it does |
|---|---|
| `http` | Issues an HTTP(S) request, asserts status code + optional body substring + optional max latency. |
| `tcp` | Opens a TCP socket, asserts it connects within timeout. No data exchange. |
| `tls` | Connects, asserts the served certificate's SAN list includes `expect_san`, asserts not expired within `expect_days_remaining`. |
| `dns` | `dig +short` for `record`, asserts result matches `expect_value`. |
| `pveapi` | Authenticated GET against Proxmox API. Used for "is VM N running", "does storage pool X have ≥ Y GB free". |
| `docker` | Runs `docker inspect` over SSH against a host, asserts container state. Used for "harbor-nginx is in `running` state". |
| `file` | Asserts a path exists / has content matching a regex / matches a SHA256. |
| `command` | Runs an arbitrary command on a target host, asserts exit code + optional stdout match. Escape hatch only. |

Each type has a tight schema in `config/contracts/deployment-v1/post-conditions.schema.json`. `scripts/self_check.py` validates entries at startup and refuses to run on a malformed registry.

### 3. Three modes of running checks

```bash
# 1. After a specific step (gated by step contract from ADR 0483):
make self-check step=converge-harbor

# 2. After a deployment is "done" — runs every check tagged `final-smoke`:
make self-check tag=final-smoke

# 3. Continuous "is this deployment still healthy" — runs every check not tagged `bootstrap-only`:
make self-check         # default: full run minus bootstrap-only
```

Output: structured JSON to stdout, human-readable summary to stderr, exit 0 only if every `critical: true` check passed. Non-critical failures exit 0 but are logged.

### 4. Receipts gain a `verification` block

Per ADR 0420 (receipt schema), every receipt already lists "what was applied." This ADR extends the schema (additively — old receipts grandfathered) with:

```json
"verification": [
  {
    "check_id": "harbor.registry.public-ping",
    "result": "pass",
    "observed": "https://registry.0fork.com/api/v2.0/ping -> 200 'Pong' in 0.18s",
    "ran_at": "2026-05-12T09:14:33Z"
  }
]
```

If the receipt has no `verification` block, or the block has failing critical checks, downstream tooling (the ADR 0420 receipt validator) **must** refuse to consider the receipt valid evidence of a successful apply.

### 5. The "ran but unverified" anti-pattern is now a defect

Today, an Ansible playbook that exits 0 is "successful." Going forward:

- An apply with no matching post-conditions is incomplete instrumentation, not "trusted by default." `scripts/self_check.py` reports steps with no post-conditions as `unverified`; CI flags any new step added without a post-condition.
- An apply that ran and had post-conditions but didn't *invoke* `self_check` after is a defect in the wrapper, not "OK because the playbook said so."
- An apply that ran, invoked `self_check`, and got at least one critical failure is a failed apply — even if Ansible exited 0.

### 6. Initial set of post-conditions (lands with this ADR)

A first installment of `config/post_conditions.yml` covering the load-bearing services:

- `harbor.registry.public-ping` — would have caught the 2026-05-06 incident on day one
- `harbor.containers.nginx-running` — would have caught it at the container layer too
- `keycloak.realm-discovery-endpoint`
- `nginx-edge.tls-san-coverage` — covers the s3.0fork.com SAN mismatch
- `postgres.tcp-reachable`
- `openbao.unsealed`
- `outline.public-200`
- `plausible.public-200`
- `glitchtip.public-200`
- `woodpecker.public-200`
- `ntfy.public-200`
- `dns.apex-points-at-edge`
- `proxmox.host.swap-not-thrashing` (would have caught the 0fork memory pressure)
- `proxmox.guest.balloon-enabled` (would have caught balloon=0)

This is the MVP — comprehensive coverage grows incrementally as new services are wired.

### 7. Out of scope

- **Alerting on continuous failure.** `self_check` reports the state. Routing failures to ntfy / PagerDuty / etc. is the existing monitoring stack's job (the container-watchdog from ws-0482 is the same pattern for one specific signal). A future ADR will define how `self_check` results flow into the monitoring stack as first-class signals.
- **Distributed verification.** Today `self_check` runs from the operator's machine (or wherever `make` runs). A future ADR will define how a verifier process runs *inside* the deployment continuously.

---

## Consequences

### Positive

- **"Did it actually work" becomes a yes/no question with a script.** No more reading 200 lines of Ansible output looking for red.
- **The Harbor incident is uncatchable in this regime.** Within minutes of the container exiting, `self-check` reports `harbor.containers.nginx-running` failing; within the same run, `harbor.registry.public-ping` reports a non-200. Both critical. Both surfaced.
- **Receipts become evidence-bearing, not aspirational.** No verification block, no trusted receipt.
- **New steps come with verification by construction.** CI lints `config/post_conditions.yml` against `config/bootstrap_steps.yml` — every step must have at least one matching condition.

### Negative

- **One more place to author.** Every new service gets ≥1 post-condition. Mitigated by a small ergonomic library — common check templates (http-200, tls-valid, etc.) compose with one-line entries.
- **Flaky checks erode trust.** A check that fires false-positive once a week trains operators to ignore it. Mitigated by the explicit retry/backoff/timeout contract and CI tests that exercise each check shape.
- **Initial registry is incomplete.** Day-1 coverage is the load-bearing services only. The platform is at higher confidence for those services, the same as today for the rest. That asymmetry is fine because the gap is visible — `make self-check` reports `unverified` for services without checks.

### Migration

1. Land this ADR + `config/post_conditions.yml` MVP (this PR).
2. Land `scripts/self_check.py` runner + 8 check-type plugins (this PR).
3. Land unit tests for the runner + each plugin (this PR).
4. Future PRs: expand coverage to every service; add a CI lint that enforces "new step ⇒ new check."

---

## References

- ADR 0420 — Receipt schema (extended additively here)
- ADR 0450 — Drift signals + `make doctor` (consumes self_check output)
- ADR 0481 — Explicit deployment context
- ADR 0482 — Capacity-aware dynamic sizing
- ADR 0483 — Hands-off bootstrap (the consumer of this ADR's contracts)
- ADR 0485 — Convergence idempotency tests (sibling)
- Postmortem: 2026-05-11 0fork Harbor 502 — the load-bearing motivator
