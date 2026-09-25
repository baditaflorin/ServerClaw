# ADR 0443: Continuous Topology Reconciler & Drift Detection

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Implemented — all phases (probe, reconciler, linter, pre-push gate, hourly Windmill schedule, ops-portal receipt)
- Date: 2026-04-27
- Concern: drift, debuggability, multi-deployment-safety, registry-as-truth
- Tags: topology, registry, drift-detection, observability
- Implements: ADR 0416 (Declarative pg_hba from Service Registry) — generalizes the same pattern
- Depends on:
  - ADR 0373 (Service Registry & Derived Defaults)
  - ADR 0416 Phase 2 (pg_hba from `platform_service_registry.host_group`)
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation)

---

## Context

We have two flavors of topology drift:

1. **Write-time drift.** A role/template/script hardcodes `10.10.10.20` for
   Keycloak. Two months later the operator runs `make migrate-service
   svc=keycloak to=other-vm`. The registry, nginx upstream config, and
   pg_hba update atomically (ADR 0416 / `migrate-service`). But a
   forgotten template still emits `10.10.10.20` somewhere — a probe, a
   monitoring scrape target, a documentation snippet that becomes a bug
   the moment somebody reads it as truth. The pre-push gate catches some
   of this, but it's a string match and grows weaker as the codebase
   grows.

2. **Runtime drift.** Even if every committed file derives from the
   registry, the *running deployment* can diverge: a container restarts
   on the wrong VM after a manual SSH session, a converge fails halfway
   and leaves Keycloak running on the old host while nginx already
   points at the new one, or a `docker run --rm` spun up two months ago
   is still listening on a port we thought was free. Today we only
   notice when somebody hits a 502.

The recent debugging episode (nginx proxying Keycloak to the wrong host)
is the canonical example: the registry said `keycloak.host_group =
runtime-control` (10.10.10.92), but nginx was emitting an upstream of
10.10.10.20. Either a template was stale (case 1) or the live nginx
config drifted from the rendered file (case 2). Without instrumentation
we can't tell which.

We need both:

- A **write-time linter** that fails CI when a template hardcodes a
  topology fact that should be looked up from the registry.
- A **runtime reconciler** that periodically scrapes every guest and
  compares observed reality against the registry, emitting a
  machine-readable drift report.

Both are deployment-aware — they read the active deployment's profile
(ADR 0441) so the prod reconciler doesn't false-positive on services
0fork doesn't run.

---

## Decision

### Layer 1 — Write-time linter

A new script `scripts/validate_no_hardcoded_topology.py` walks all
non-allowlisted text files and flags any literal IP or `:port` that
matches a known service-host mapping from `platform_service_registry`.

**Allowlist** (files that legitimately contain real IPs):

- `inventory/hosts.yml` (generated)
- `inventory/group_vars/platform.yml` (generated)
- `inventory/host_vars/*.yml` (operator-authored topology — the source)
- `.local/**` (per-deployment overrides)
- `docs/**`, `*.md` (documentation — uses generic `10.10.10.X` examples)
- `tests/**` (test fixtures)
- `build/**` (generated artifacts)

**Detection rule** for each registered service `<svc>` with
`host_group=<group>` and `internal_port=<port>`:

- Resolve `<group>` → `<ipv4>` from `proxmox_guests` topology.
- Search every non-allowlisted file for the literal `<ipv4>:<port>`.
  When found outside allowlist, flag it.
- Also flag bare `<ipv4>` when accompanied by a known service name on
  the same line (heuristic; reduces false positives from generic IP
  references).

**Outcome**: pre-push gate runs `make validate-topology-templates`. If
any new hardcoded mapping is added, the gate fails with a precise
file:line:service reference.

### Layer 2 — Runtime probe + reconciler

Two scripts, one per side:

**`scripts/topology_probe.py`** — runs on a guest VM. Stdlib only (no
`requests`, no `psutil`). Captures:

```json
{
  "schema": "topology-probe/v1",
  "hostname": "runtime-control",
  "captured_at": "2026-04-27T10:30:00Z",
  "containers": [
    {"name": "keycloak", "image": "...", "state": "running", "ports": ["8091/tcp"]}
  ],
  "listening_tcp": [
    {"port": 8091, "address": "0.0.0.0", "process": "docker-proxy"}
  ]
}
```

Containers come from `docker ps --format=json`. Listening ports come
from `ss -tlnp` (or `/proc/net/tcp` parsing as a fallback). The probe
script is idempotent and finishes in under a second.

**`scripts/topology_reconciler.py`** — runs on the controller. For the
active deployment:

1. Load `platform_service_registry`, `proxmox_guests`,
   `service_profiles.yml`, and the deployment's `profile.yml`.
2. Compute `expected[host] = { (service, port), ... }` for every host
   that owns at least one enabled service.
3. SSH-fan-out to each host using the existing `ANSIBLE_INVENTORY`
   connection metadata (controller → host via proxmox jump host).
4. Run `topology_probe.py` on each host, parse the JSON.
5. Diff:
   - **Missing** — service is in `expected[host]` but no container or
     listening port matches.
   - **Misplaced** — service is running on a host but the registry says
     it should be on a different host.
   - **Unexpected** — container running on a host that does not appear
     anywhere in `expected[host]` for that service name.
   - **Port stranger** — listening port on a host not claimed by any
     enabled service.
6. Write `.local/deployments/<slug>/state/drift-report.json` and a
   human-readable `drift-report.md`. Exit code 0 when clean, 1 when
   drift is detected.

**Scheduling**: out of scope for this ADR. Operators wire `make
detect-topology-drift` into a cron job, a Windmill workflow, or a
GitHub Action — same model as the existing pre-push gate. The script
is a primitive; scheduling is policy.

**Alerting**: drift-report.json has a stable schema. Operators add
ntfy/alertmanager forwarding by reading the JSON in their job runner.

### Make surface

```
make validate-topology-templates       # write-time linter (pre-push)
make detect-topology-drift             # one-shot runtime reconcile
make detect-topology-drift deployment=0fork
make topology-probe-self               # run the probe on the local guest
                                       # (used by the reconciler over SSH)
```

### Per-deployment isolation

The reconciler reads only the active deployment's enabled services. For
deployment `0fork` (which only runs `core + devtools`), the reconciler
will not flag the absence of `langfuse` on `runtime-control` as drift,
because langfuse is not in 0fork's profile.

The drift report lives under
`.local/deployments/<slug>/state/drift-report.json` so two deployments
running the reconciler in parallel cannot clobber each other's reports.
A separate advisory lock (`state/topology-reconcile.lock`) prevents two
reconciler runs against the same deployment.

---

## Consequences

**Positive**

- The write-time linter prevents new drift from being introduced — the
  pre-push gate will catch a hand-typed `10.10.10.20` next to a
  reference to keycloak in any non-allowlisted file.
- The runtime reconciler catches drift introduced by anything outside
  the converge path: manual SSH, half-failed migrations, third-party
  changes, container restart on the wrong node.
- Both work per-deployment, so 0fork's reconciler doesn't false-positive
  on services prod runs.
- The probe is stdlib-only, so it works on any guest with Python 3
  without requiring an Ansible converge to install dependencies first.
- The drift-report schema is stable, so operators can build their own
  alerting on top.

**Negative / cost**

- The linter has false-positive risk for files that legitimately
  reference registry IPs (e.g., a runbook explaining the topology). The
  allowlist approach is coarse but maintainable; we accept that adding
  a new operator-facing file may require an allowlist update.
- The reconciler requires SSH access from the controller to every
  registered host. Not new — every other Ansible play already does this
  — but it does mean the reconciler can't run from a totally
  disconnected machine.
- The probe leaks process names and listening port info to the
  reconciler. This stays inside `.local/` (gitignored) so it never
  reaches the public mirror. Sensitive process names should not appear
  in container labels regardless.

**Out of scope**

- Auto-remediation: the reconciler reports drift; it does not fix it.
  Self-healing is intentionally postponed until we have signal on
  false-positive rates.
- Schedule provisioning: operators wire it into their job runner of
  choice.

---

## Migration

All three phases shipped together (2026-04-27):

1. **Phase 1 — ship the primitives.**
   - `scripts/topology_probe.py` (stdlib-only guest probe).
   - `scripts/topology_reconciler.py` (controller-side SSH-fan-out + diff).
   - `scripts/validate_no_hardcoded_topology.py` (write-time linter).
   - Make targets: `validate-topology-templates`, `topology-probe-self`,
     `detect-topology-drift`, `plan-topology`.

2. **Phase 2 — promote the linter to a hard gate.**
   - Wired into `scripts/validate_repo.sh` as the
     `validate_no_hardcoded_topology` stage, runs as part of the `all`
     bundle and via `bash scripts/validate_repo.sh no-hardcoded-topology`.
   - Allowlist tightened to data-source paths (`catalog/`, `config/`,
     `inventory/host_vars/`, `playbooks/vars/`, `workstreams/`); per-line
     `# noqa: topology-hardcode` for the few legitimate defaults.

3. **Phase 3 — periodic reconcile + ops-portal surface.**
   - `config/windmill/scripts/topology-drift-check.py` — Windmill wrapper
     that runs the reconciler against the active deployment, writes
     `.local/deployments/<slug>/state/drift-report.{json,md}`, and
     publishes an ops-portal-compatible receipt under
     `receipts/drift-reports/topology-<slug>-<timestamp>.json`.
   - Schedule `f/lv3/topology_drift_check_hourly` registered in
     `roles/windmill_runtime/defaults/main.yml` (every hour at :30).
   - The portal aggregator already scans `receipts/drift-reports/*.json`
     so the topology drift surfaces in the existing drift panel without
     additional UI work.

---

## References

- ADR 0373 — service registry as the source of truth
- ADR 0416 — declarative pg_hba derivation; same pattern, different
  artifact
- ADR 0441 — service profile resolver, used to compute "enabled
  services" for the reconciler
- Recent incident (2026-04): nginx upstream pointed at wrong VM for
  Keycloak — the canonical motivation for runtime drift detection
