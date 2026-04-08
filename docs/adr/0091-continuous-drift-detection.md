# ADR 0091: Continuous Drift Detection and Reconciliation

- Status: Accepted
- Implementation Status: Partial Implemented
- Implemented In Repo Version: 0.94.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

As the platform grows, the gap between **declared state** (what the IaC says should exist) and **actual state** (what is actually running on Proxmox) widens silently. Sources of drift include:

- Manual changes in the Proxmox UI (memory resize, disk expansion, CPU hotplug)
- Docker containers updated via Watchtower or manual `docker pull` outside of the deployment pipeline
- Ansible roles that are not idempotent in all edge cases leaving partial state
- VM snapshots or backups restored to a prior state
- Network routes or firewall rules changed during an incident that were never cleaned up
- OpenBao secrets that have been manually rotated (breaking the version tracking)

The agent observation loop (ADR 0071) collects observations but does not classify them as drift. The mutation audit log (ADR 0066) records mutations but only for changes made through the platform tooling — it is blind to out-of-band changes. No periodic reconciliation job exists.

The result: `main` declares one thing; the platform runs another. Over time this erodes trust in the IaC repo as the source of truth and makes operators reluctant to run playbooks ("I'm not sure what will change").

## Decision

We will implement **continuous drift detection** as a scheduled Windmill workflow that:
1. Compares desired state (IaC) to actual state (live query)
2. Classifies each discrepancy as `expected`, `warn`, or `critical`
3. Emits NATS events for actionable drift
4. Surfaces results in the ops portal and as a Grafana panel

### Drift sources

#### 1. OpenTofu drift (VM resource drift)

```bash
tofu plan -detailed-exitcode ENV=production
# exit 0 = no changes; exit 2 = drift detected
```

The Windmill workflow runs `make tofu-drift ENV=production` on the build server and parses the plan JSON output. Any planned change is drift.

#### 2. Ansible check-mode drift (service configuration drift)

```bash
ansible-playbook site.yml --check --diff \
  -l "{{ changed_hosts_only }}"
```

Run in `--check` mode against production hosts. Changed tasks are drift. The output is parsed by `scripts/parse_ansible_drift.py` to extract per-host, per-role, per-task changes.

#### 3. Docker image drift (container version drift)

Query the Docker daemon on each host for running container image digests, compare against the runtime image declarations in `config/image-catalog.json`. Any container running a different digest than declared is image drift.

```python
actual_digest = docker_inspect(container)["Image"]
expected_digest = catalog[service]["expected_image_digest"]
if actual_digest != expected_digest:
    emit_drift_event("image", service, actual_digest, expected_digest)
```

#### 4. DNS drift (subdomain catalog drift)

Query the internal DNS server for each subdomain in `config/subdomain-catalog.json` and compare to declared A/CNAME records. Missing or wrong DNS records are drift.

#### 5. Certificate drift (TLS expiry drift)

Check TLS certificate expiry for every service URL. Certificates expiring within 14 days are `warn`; within 7 days are `critical`. This complements the existing alert but adds a source-of-truth comparison against the expected issuer (step-ca vs Let's Encrypt vs self-signed).

### Drift classification

| Class | Meaning | Action |
|---|---|---|
| `expected` | Staged change in flight (an open ADR branch is being applied) | Suppress; log only |
| `warn` | Drift from declared state but service is healthy | Emit NATS `platform.drift.warn` |
| `critical` | Drift that indicates a broken service or security violation | Emit NATS `platform.drift.critical`; fire Grafana alert |

Expected drift is suppressed by checking the active workstreams from `workstreams.yaml`; if a service has a workstream in `status: in_progress`, its drift is expected.

### NATS event format

```json
{
  "event": "platform.drift.warn",
  "source": "ansible-check-mode",
  "host": "docker-runtime-lv3",
  "service": "openbao",
  "role": "openbao_runtime",
  "task": "ensure openbao config file",
  "detail": "content differs from declared template",
  "detected_at": "2026-03-22T10:15:00Z",
  "workstream_suppressed": false
}
```

### Windmill schedule

The `continuous-drift-detection` workflow runs:
- Every 6 hours (scheduled)
- On every merge to `main` (post-merge check)
- On demand via `lv3 diff --env production`

Each run produces a drift report written to `receipts/drift-reports/<timestamp>.json`.

### Ops portal integration

The ops portal (ADR 0074) displays a **Drift Status** panel:
- Green: last drift run found no actionable drift
- Yellow: warn-class drift items exist (with count and services)
- Red: critical-class drift (with service names and details)

The implemented portal view links to the latest drift receipt and surfaces the most recent records directly from `receipts/drift-reports/`.

### Reconciliation

Drift detection is read-only. Reconciliation is a separate, operator-approved action:

```bash
lv3 deploy <service> --env production   # re-applies the declared state
# or
make remote-tofu-apply ENV=production   # reconciles VM resource drift
```

Automatic reconciliation (auto-heal) is explicitly **out of scope** for this ADR. Auto-heal without human approval on a production homelab is high-risk; it will be revisited after the drift detection baseline is established.

## Consequences

**Positive**
- Operators can see at a glance whether the live platform matches the IaC repo — restoring trust in the repo as source of truth
- Drift is surfaced before it causes incidents, not discovered during one
- Expected drift suppression prevents alert fatigue during active ADR deployments
- `lv3 diff` gives an interactive "what would change?" before any deployment — reducing deployment anxiety

**Negative / Trade-offs**
- Ansible check-mode drift detection requires running `ansible-playbook --check` against production hosts; this is read-only but adds SSH traffic every 6 hours
- OpenTofu `plan` against the production state requires Proxmox API access from the build server; this is already required for `tofu apply`
- False positives from transient conditions (container restart in progress, health check timing) must be handled with retry logic to avoid noisy alerts

## Alternatives Considered

- **Manual periodic audits**: does not scale; operators forget; inconsistent depth of review
- **Full GitOps auto-reconciliation (ArgoCD-style)**: appropriate for Kubernetes; overkill and risky for a heterogeneous Proxmox/Docker/Ansible environment without a controller that understands all resource types
- **Just rely on monitoring alerts**: monitors service health but not configuration correctness; a misconfigured service can be "healthy" while drifting from declared intent

## Related ADRs

- ADR 0066: Mutation audit log (records changes made through the platform; drift detection covers out-of-band changes)
- ADR 0071: Agent observation loop (observations feed into drift classification)
- ADR 0074: Ops portal (surfaces drift status)
- ADR 0082: Remote build execution gateway (drift checks run on build server)
- ADR 0085: OpenTofu VM lifecycle (`tofu plan --detailed-exitcode` is the VM drift source)
- ADR 0090: Unified platform CLI (`lv3 diff` is the interactive drift entry point)
