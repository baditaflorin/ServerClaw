# ADR 0463: Post-Converge / On-Demand Health-Probe Runner

- Status: Accepted
- Implementation Status: Implemented (`scripts/run_health_probes.py` + per-probe receipts under `receipts/health-probes/`)
- Date: 2026-04-29
- Concern: continuous-verification, drift-detection, stale-success
- Tags: health, observability, receipts, post-converge
- Implements: improvement #4 from the 2026-04-29 reliability review
- Depends on:
  - ADR 0205 (Capability contracts before product selection — mandates `health.liveness` per service)
  - ADR 0461 (Atomic receipt write)

---

## Context

Every service in `catalog/services/<svc>/service.yaml` already declares
a `health.liveness` block (HTTP/TCP probe with timeout, retries, and
expected status codes). That block exists for ADR 0205 documentation
purposes but isn't run from any continuous-verification loop today.

The 2026-04-28 ops.0fork.com 500 incident is the canonical case: the
v0.179.5 nginx converge wrote the new `proxy_buffer_size 64k` block,
but nginx wasn't reloaded and the value didn't take effect. The
operator only noticed when the URL stayed broken in a browser. A
post-converge HTTP probe against `https://ops.0fork.com/` would have
caught it within seconds.

Today's continuous-verification surfaces are:

- **Pre-push gate** — static checks against committed state. Cannot
  see live HTTP responses.
- **Per-role `verify.yml`** — runs at the end of each role's
  converge. Inconsistent in scope (some roles probe, some don't),
  not aggregated, and the result lives only in Ansible's transient
  PLAY RECAP.
- **Uptime Kuma** (per `health.uptime_kuma` blocks) — operator-grade
  monitoring on a 60-second interval, but receipt writes go to Uptime
  Kuma's storage, not to a repo-readable artifact.

What we're missing: a leaf primitive that takes a list of services,
runs each one's `health.liveness` probe, and writes a per-probe
receipt the rest of the platform (`make doctor`, `cross_deployment_doctor.py`,
the ops portal) can read.

## Decision

`scripts/run_health_probes.py`:

- CLI: `--service <slug>` (repeatable), `--all`, `--timeout <seconds>`, `--receipts-dir <path>`, `--json`, `--no-receipts`.
- Reads `catalog/services/<slug>/service.yaml::health.liveness` for each requested service.
- Dispatches by `kind`: `http` → `urllib.request.urlopen`, `tcp` → `socket.create_connection`. Unknown kinds return failure with a clear message.
- Writes one receipt per probe to `receipts/health-probes/<slug>-<ts>.json` using the atomic-write helper from ADR 0461.
- Exit codes: `0` all probes OK, `1` ≥ 1 probe failed, `2` usage / data error.

The script is intentionally a leaf:

- It does not orchestrate converges — that's the role's job.
- It does not gate pushes — pre-push gates require the worktree to reach the live deployment, which is not always true.
- It does not block on missing services — services without `health.liveness` are skipped with a clear message.

Operator surfaces:

```bash
# Probe one service:
python3 scripts/run_health_probes.py --service ops_portal

# Probe everything in the catalog:
python3 scripts/run_health_probes.py --all --json

# Run probes without writing receipts (CI / dry-run):
python3 scripts/run_health_probes.py --service api_gateway --no-receipts
```

### Why receipts under `receipts/health-probes/`

Aligns with ADR 0446 (receipt freshness) and ADR 0461 (atomic write).
A future workstream can add a `make doctor` signal that reads the most
recent probe receipt per service and flags anything older than N
hours OR last-failed. The receipt format is intentionally simple:
`service`, `probed_at`, `kind`, `ok`, `detail`, `probe`. It composes
with the existing receipt-search tooling.

### What this ADR explicitly defers

- **Wiring into per-role converge tasks.** A role-author workstream
  can `include_role: name: lv3.platform.health_probe_post_converge`
  (or call this script as a `command:` task) once the receipt format
  is stable.
- **Doctor signal that flags stale/failed probes.** Builds on this
  receipt format; out of scope here.
- **Aggregation into the ops portal.** Reads `receipts/health-probes/`
  the same way the portal already reads `receipts/live-applies/`.

## Consequences

- Operators have a single command to verify every service is reachable post-converge.
- The receipt format is a stable foundation for a `make doctor`
  signal and ops portal aggregation.
- Service authors can rely on the script to consume `health.liveness`
  blocks they're already writing for ADR 0205.

## References

- [ADR 0205 — Capability contracts before product selection](0205-capability-contracts-before-product-selection.md) — defines `health.liveness`.
- [ADR 0446 — Receipt freshness](0446-phase2-multi-deployment-hardening.md)
- [ADR 0461 — Atomic receipt write](0461-atomic-receipt-write-and-dangling-check.md)
- 2026-04-28 ops.0fork.com 500 incident — the failure mode this ADR
  closes.
