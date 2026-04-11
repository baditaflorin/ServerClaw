# ADR 0392: Convergence Speed and Incremental Apply

**Status:** Accepted

**Date:** 2026-04-10

**Extends:** ADR 0355 (Apply Phase Serialization), ADR 0372 (Data-Driven Playbook Composition)

## Context

A single `make converge-keycloak env=production` takes 15-25 minutes. `converge-plane` is similar. When deploying a new integration (e.g., Keycloak-Plane OIDC), the operator must run both sequentially — 30-50 minutes of wall-clock time for what amounts to adding three environment variables and one OIDC client.

This latency compounds:

- **Operator frustration:** waiting 30+ minutes for a config-only change discourages small, safe deploys in favor of batched, risky ones.
- **Feedback loop:** a typo discovered post-deploy means another 30-minute cycle.
- **Validation gate coupling:** the pre-push validation gates cannot pass until deployment artifacts exist, but deployment takes too long to run speculatively.

### Where the time goes

Profiling `converge-keycloak` (5 plays, 5 hosts) reveals:

| Phase | Time | % | Root cause |
|-------|------|---|------------|
| SSH connection + fact gathering | 2.5-5 min | 20% | 5 sequential hosts × 30-60s each. Facts gathered even for hosts where no tasks run. |
| Preflight validation | 1-3 min | 12% | Sequential secret file checks, health probes with generous timeouts. |
| Docker image pulls | 2-4 min | 16% | No local image cache policy. `docker compose pull` runs unconditionally. |
| Role convergence (unchanged) | 5-8 min | 40% | Entire role re-runs even when compose file, env, and images are identical to running state. |
| NGINX reload + health checks | 1-2 min | 8% | Full config test + reload even when no routes changed. |
| Notification + receipt | <1 min | 4% | Acceptable. |

**Key insight:** ~80% of runtime is spent re-verifying state that hasn't changed. The platform has no mechanism to detect "nothing changed, skip this play."

## Decision

### Phase 1: Quick wins (target: cut 40% of runtime)

#### 1.1 Conditional fact gathering

Plays that only delegate to localhost (DNS, preflight) do not need remote facts. Change from:

```yaml
gather_facts: true
```

to:

```yaml
gather_facts: "{{ 'yes' if inventory_hostname != 'localhost' else 'no' }}"
```

**Savings:** 60-120s (skip fact gathering for 2-3 hosts that don't need it).

#### 1.2 Docker image digest pinning

Before pulling, check if the running image digest matches the desired tag:

```yaml
- name: Check if image pull is needed
  command: docker image inspect {{ item }}
  register: image_check
  failed_when: false
  changed_when: false

- name: Pull only if image missing or stale
  command: docker compose pull
  when: image_check.rc != 0
```

**Savings:** 120-240s when images haven't changed (the common case).

#### 1.3 Preflight parallelism

The preflight controller checks secrets sequentially. Use Python's `concurrent.futures.ThreadPoolExecutor` to check all secrets in parallel:

```python
with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(check_secret, secret_specs))
```

**Savings:** 30-60s.

### Phase 2: Incremental convergence (target: cut 70% for no-change runs)

#### 2.1 Convergence fingerprinting

Before running a role, compute a fingerprint of its inputs:

```
fingerprint = sha256(
    compose_file_content +
    env_file_content +
    role_defaults_hash +
    image_digests
)
```

Store the fingerprint as a file on the target host (e.g., `/var/lib/lv3/convergence/<service>.fingerprint`). On the next run, compare:

- **Match:** skip the role entirely, emit `ok: [converged, no changes]`
- **Mismatch:** run the role normally, update the fingerprint on success

**Savings:** 5-8 minutes for unchanged services (the majority case).

#### 2.2 Play-level parallelism via lanes

Currently, plays run sequentially because Ansible processes them in order. Services on different hosts can converge in parallel using `strategy: free` or by splitting into independent playbook invocations:

```
Lane A (postgres):  database prep          ──┐
Lane B (docker-runtime): docker pull + compose  ──┼── wait ── NGINX reload
Lane C (nginx-edge):     config generation       ──┘
```

The `ansible_scope_runner.py` already computes host limits per playbook. Extend it to detect independent lanes and fork parallel `ansible-playbook` processes.

**Savings:** 3-5 minutes (postgres and docker-runtime converge simultaneously).

### Phase 3: Speculative validation (target: unblock git push)

#### 3.1 Dry-run mode for validation gates

Add a `--dry-run` flag to the validation gate that checks contract schemas and config syntax without requiring live infrastructure:

```bash
make validate-integration config/integrations/keycloak--plane.yaml
```

This allows the pre-push hook to pass for config-only changes without a full deployment cycle.

#### 3.2 Gate result caching

Cache validation gate results keyed by the content hash of changed files. If the same set of files was validated successfully in a recent run, skip re-validation:

```json
{
  "content_hash": "abc123...",
  "gates_passed": ["schema-validation", "service-completeness"],
  "validated_at": "2026-04-08T10:00:00Z",
  "ttl_seconds": 3600
}
```

## Consequences

### Positive

- **Config-only deploys drop from 30 min to ~5 min** (Phase 1 + 2 combined).
- **No-change convergence drops to <2 min** (fingerprint match → skip).
- **Git push unblocked for config changes** without waiting for full deployment (Phase 3).
- **Smaller, safer deploys** become the default because the feedback loop is fast enough to encourage them.

### Negative

- **Fingerprint staleness risk:** if external state changes (manual Docker intervention, host reboot), the fingerprint may falsely indicate "no change." Mitigation: `make converge-keycloak env=production force=true` bypasses fingerprint cache.
- **Parallel lane complexity:** debugging failures across parallel lanes is harder. Mitigation: each lane writes to its own log file; a summary report merges results.
- **Dry-run validation gap:** dry-run cannot catch runtime errors (port conflicts, OOM). Mitigation: dry-run is a speed optimization, not a correctness guarantee; full convergence remains the source of truth.

### Migration

All phases are additive. No existing behavior changes unless explicitly opted into:

- Phase 1: direct code changes, no flag needed.
- Phase 2: fingerprinting defaults to disabled; enable with `LV3_INCREMENTAL_CONVERGE=1`.
- Phase 3: dry-run validation is a new Make target, does not replace existing gates.

## Implementation Status

All phases implemented on 2026-04-10:

| Phase | File(s) Changed | Notes |
|-------|----------------|-------|
| 1.1 Conditional facts | `ansible.cfg` | Added `gather_subset = !hardware` globally |
| 1.2 Image digest check | `common/tasks/docker_compose_converge.yml` | Skips `docker compose pull` when images exist locally |
| 1.3 Preflight parallel | `scripts/preflight_controller_local.py` | Secret checks now use `ThreadPoolExecutor` |
| 2.1 Fingerprinting | `common/tasks/convergence_fingerprint.yml`, `common/defaults/main.yml` | Opt-in via `LV3_INCREMENTAL_CONVERGE=1` |
| 2.2 Lane parallelism | `scripts/ansible_scope_runner.py` | New `parallel-run` command; `make parallel-converge` |
| 3.1 Dry-run validation | `Makefile` | `make validate-integration` runs syntax + schema gates |
| 3.2 Gate caching | `scripts/gate_result_cache.py` | Content-hash keyed cache with configurable TTL |

**Also:** reduced default health check timeouts (port: 300s→120s, retries: 36→24) in `common/defaults/main.yml`.
