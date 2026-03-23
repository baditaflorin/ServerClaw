# ADR 0100: Formal RTO/RPO Targets and Disaster Recovery Playbook

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-23

## Context

ADR 0051 defined the concept of backup, recovery, and break-glass procedures for the control plane, but without measurable targets. As the platform matures and becomes the operator's primary tool for all other operations, the question "how long would it take to recover the full platform from a total loss event?" has no documented answer.

A total loss event could be:
- Proxmox host hardware failure (disk, motherboard, network)
- Hetzner datacenter-level incident
- Catastrophic operator error (accidental `rm -rf /var/lib/vz/`)
- Ransomware encrypting the host (unlikely but possible given public exposure)
- PBS backup VM failure coinciding with a host failure

Without an RTO/RPO definition, there is also no way to verify whether current backup and HA investments (ADR 0020, ADR 0098) actually achieve the platform's recovery goals, and there is no ordered recovery procedure that would allow a fresh operator (or the original operator in a panic) to rebuild the platform systematically.

## Decision

We will define formal **Recovery Time Objective (RTO)** and **Recovery Point Objective (RPO)** targets for the platform, document the ordered recovery sequence as an executable Windmill runbook, and publish it as the primary disaster recovery playbook in the docs site (ADR 0094).

### Targets

| Scenario | RTO | RPO | Notes |
|---|---|---|---|
| Single service failure (container crash) | < 5 min | 0 | Docker restart policy handles this automatically |
| VM failure (Postgres, with HA in ADR 0098) | < 1 min | 0 committed transactions | Patroni automatic failover |
| VM failure (stateless: nginx, monitoring) | < 30 min | 0 | Reprovisioned from IaC; no data loss |
| VM failure (stateful, no HA: docker-runtime) | < 2 h | < 24 h | Restore from last nightly PBS snapshot |
| Full host recovery from PBS off-site backup | < 4 h | < 24 h | Full re-provision required |
| Full host recovery from total loss (no backup) | < 8 h | unbounded | IaC rebuild from repo; data lost |

**Platform-wide RTO: < 4 hours.** The platform is fully functional, serving all edge-published services, within 4 hours of a total host loss given the nightly PBS backup is available.

**Platform-wide RPO: < 24 hours.** No more than 24 hours of operational data is lost in the worst case (single nightly backup cadence). Postgres data loss is bounded at < 24 h for unplanned failures; 0 transactions for planned failover with ADR 0098 in place.

### Recovery tiers

Recovery is ordered by dependency: a service cannot be recovered before the service it depends on.

#### Tier 0: Host re-provision (if hardware replaced)
1. Provision fresh Hetzner dedicated server with Debian 13 via `installimage` (ADR 0003)
2. Install Proxmox VE from Debian packages (ADR 0004)
3. Restore PBS backup VM from off-site backup (Hetzner Storage Box or similar)
4. Proceed to Tier 1

#### Tier 1: Identity and secrets (< 30 min from PBS restore)
Services that all other services depend on must be recovered first.

```
1. restore_vm(vmid=160)          # backup-lv3 (PBS) — restores backup catalog
2. restore_vm(vmid=150)          # postgres-lv3 — database for identity services
3. start_service("step-ca")      # TLS and SSH certificates (ADR 0042)
4. start_service("openbao")      # Secrets and dynamic credentials (ADR 0043)
5. verify: step-ca issues a test certificate
6. verify: openbao is unsealed and /v1/sys/health returns 200
```

OpenBao unseal keys are stored in the break-glass procedure from ADR 0051.

#### Tier 2: Identity services (< 60 min)
```
7. start_service("keycloak")     # SSO (ADR 0056)
8. verify: https://sso.lv3.org/health/ready returns 200
```

#### Tier 3: Platform services (< 90 min)
```
9.  restore_vm(vmid=120)         # docker-runtime-lv3
10. start_services([             # in parallel:
      "windmill",                # Workflow engine (ADR 0044)
      "netbox",                  # IPAM and inventory (ADR 0054)
      "mattermost",              # ChatOps (ADR 0057)
      "nats",                    # Event bus (ADR 0058)
    ])
11. verify: each service health probe returns 200
```

#### Tier 4: Observability and access (< 2 h)
```
12. restore_vm(vmid=140)         # monitoring-lv3
13. restore_vm(vmid=110)         # nginx-lv3
14. start_services([
      "grafana", "loki", "tempo", # Observability (ADR 0052, 0053)
    ])
15. verify: https://grafana.lv3.org is accessible
16. verify: https://ops.lv3.org is accessible
```

#### Tier 5: Build infrastructure (< 4 h)
```
17. restore_vm(vmid=130)         # docker-build-lv3
18. verify: remote build gateway responds (ADR 0082)
19. run: make health-check-all   # full platform health sweep
```

### Windmill runbook

Each tier is implemented as a Windmill workflow step in `disaster-recovery-runbook`:

```python
@windmill_step(name="tier_1_identity_secrets")
def recover_tier_1(proxmox_api: ProxmoxAPI, pbs_api: PbsAPI) -> StepResult:
    pbs_api.restore_vm(vmid=160, target_node="florin", timeout=600)
    pbs_api.restore_vm(vmid=150, target_node="florin", timeout=600)
    wait_for_service("step-ca", "https://ca.internal.lv3:9443/health", timeout=120)
    wait_for_service("openbao", "http://openbao:8200/v1/sys/health", timeout=120)
    return StepResult.ok(message="Tier 1 recovered: step-ca and OpenBao are healthy")
```

The runbook can be triggered from Windmill's UI or `lv3 runbook disaster-recovery --tier all`. It records each step result in the mutation audit log (ADR 0066) with timestamps.

### Off-site backup

The current PBS instance backs up to local disk on `backup-lv3`. For a total host loss, the backup itself is gone. Off-site backup is therefore required:

We will configure PBS to sync the most recent 7 backup snapshots of each VM to a **Hetzner Storage Box** (external NFS/SFTP endpoint) using the PBS remote sync job. Storage Box sync runs daily at 04:00 UTC.

Total off-site storage required: ~7 × (sum of VM disk sizes) ≈ 7 × 340 GB = ~2.4 TB deduped (PBS deduplication significantly reduces this in practice).

### Break-glass documentation

A physical printed card (and an encrypted PDF in a personal password manager) contains:
- Hetzner account credentials for server reinstallation
- OpenBao unseal keys (ADR 0051)
- Hetzner Storage Box credentials for off-site backup access
- step-ca root certificate fingerprint
- Proxmox `root@pam` emergency credential

This information is documented in `docs/runbooks/break-glass.md` with instructions to keep the physical copy up-to-date when credentials change.

### Recovery drill

The recovery procedure is tested once per quarter as a table-top exercise:
- Walk through each tier step by step
- Verify that every credential and tool referenced in the runbook is still valid
- Record any deviations from the documented procedure in the mutation audit log

A full live recovery drill (restoring from off-site backup to a temporary Hetzner server) is performed annually.

## Consequences

**Positive**
- The platform has a defined, measurable recovery commitment for the first time; `< 4 h RTO, < 24 h RPO` is a statement of design intent and operational preparation
- The ordered recovery sequence prevents the "which service do I start first?" paralysis during an actual incident
- Off-site PBS sync to Hetzner Storage Box closes the total host loss gap in the backup strategy
- The Windmill runbook makes the recovery procedure executable, not just documented

**Negative / Trade-offs**
- Hetzner Storage Box for off-site backup adds a monthly cost (~€3–8/month for the required capacity)
- The < 4 h RTO assumes the operator has access to the break-glass credentials and can provision a fresh Hetzner server immediately; in a true emergency, delays in any of these prerequisites extend the RTO
- PBS to Storage Box sync adds nightly network traffic; on a shared Hetzner uplink this may impact other services between 04:00 and 05:00 UTC

## Alternatives Considered

- **No formal RTO/RPO; rely on PBS snapshots**: the current state; a disaster recovery attempt would be improvised, slow, and error-prone
- **Replicate all VMs to a second Hetzner server in real time**: full active-standby; eliminates the recovery time but costs ~2× the monthly hosting budget; disproportionate for a homelab
- **Use Restic for off-site backup instead of PBS sync**: Restic is flexible and supports multiple backends; but PBS's native sync to a PBS-compatible remote is better integrated with the existing backup workflow and supports incremental sync efficiently

## Related ADRs

- ADR 0020: Storage and backup model (PBS backups are the source)
- ADR 0029: Backup VM (PBS runs on backup-lv3)
- ADR 0042: step-ca (first Tier 1 dependency to recover)
- ADR 0043: OpenBao (first Tier 1 dependency to recover)
- ADR 0051: Control-plane backup and break-glass (this ADR supersedes it with concrete targets)
- ADR 0094: Developer portal (recovery runbook is published here)
- ADR 0098: Postgres HA (eliminates the most common unplanned recovery scenario)
- ADR 0099: Backup restore verification (provides evidence that the recovery path works)
