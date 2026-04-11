# ADR 0102: Security Posture Reporting and Benchmark Drift

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.109.0
- Implemented In Platform Version: 0.130.21
- Implemented On: 2026-03-26
- Date: 2026-03-23

## Context

The platform has a defined security baseline for the Proxmox host (ADR 0006) and Docker guests (ADR 0024), but neither baseline is continuously verified. Security baseline checks are performed manually when initially applying a role and then assumed to remain in place. This assumption is unreliable because:

- OS packages accumulate vulnerabilities between manual audits
- Security-relevant kernel parameters can drift from their set values (sysctl drift)
- New CVEs affect packages installed on VMs without triggering any alert
- Docker images running on `docker-runtime` are built from third-party base images that may have vulnerabilities at the time of deployment that were not present at build time
- The guest firewall rules (ADR 0067) can drift from the declared policy without detection (covered by ADR 0091 at the config level, but not at the vulnerability level)

Without a continuous security scan, the platform's security posture degrades silently over time. The gap between "secure when deployed" and "secure today" widens with every month that passes without a fresh audit.

## Decision

We will implement a **weekly automated security posture report** using two complementary tools — Lynis for host or guest OS-level hardening checks and Trivy for container image vulnerability scanning — with results written to committed receipts, surfaced in the current ops portal (ADR 0074) and Grafana dashboard, and optionally forwarded to Mattermost, GlitchTip, NATS, and the mutation audit log.

### Tool selection

| Tool | Scope | Output |
|---|---|---|
| Lynis | OS hardening: sysctl, file permissions, SSH config, PAM, auditd, kernel modules | Hardening index (0–100), finding list |
| Trivy | Container image CVEs: HIGH and CRITICAL only | CVE ID, severity, affected package, fixed version |
| Gitleaks | Secrets in the git history (already in the validation gate, ADR 0087) | Secret type, file, line number |

Lynis is run on: `proxmox host`, `docker-runtime`, `postgres`, `nginx-edge`, and `monitoring`.
Trivy is run on: all running containers on `docker-runtime` and `docker-build`.

### Weekly scan workflow

A Windmill wrapper `security-posture-scan` runs the controller-side report workflow on a weekly schedule:

```python
def run_security_scan():
    subprocess.run(
        [
            "python3",
            "scripts/security_posture_report.py",
            "--env",
            "production",
            "--audit-surface",
            "windmill",
            "--publish-nats",
        ],
        check=True,
    )
```

### Lynis integration

Lynis is installed on-demand by the dedicated scan playbook and its report files are fetched back to the controller checkout:

```yaml
# playbooks/tasks/security-scan.yml
- name: Run Lynis security audit
  hosts: all
  become: true
  tasks:
    - name: Ensure Lynis is installed
      apt:
        name: lynis
        state: present

    - name: Run Lynis
      command: lynis audit system --cronjob --quiet --report-file /var/tmp/lv3-security-posture/{{ inventory_hostname }}-lynis-report.dat

    - name: Fetch the generated Lynis report
      fetch:
        src: "/var/tmp/lv3-security-posture/{{ inventory_hostname }}-lynis-report.dat"
        dest: ".local/security-posture/lynis/"
        flat: yes
```

The `scripts/parse_lynis_report.py` script parses the `.dat` report into structured JSON:

```json
{
  "host": "docker-runtime",
  "hardening_index": 72,
  "findings": [
    {
      "id": "KRNL-6000",
      "severity": "warning",
      "description": "Kernel is not compiled with stack protection",
      "suggestion": "Consider recompiling the kernel with stack protection"
    }
  ]
}
```

A finding that appears in the current report but not in the previous receipt is a **new finding** and is counted in the report summary. Critical findings may also be forwarded to GlitchTip and NATS when those integrations are configured.

### Trivy integration

Trivy runs as a container on each Docker host and scans the set of currently running images:

```bash
#!/usr/bin/env bash
# scripts/trivy_scan_running_images.sh

docker ps --format '{{.Image}}' | sort -u | while read image; do
  docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /var/tmp/lv3-trivy-cache:/root/.cache/trivy \
    docker.io/aquasec/trivy:0.63.0 \
    image --format json --scanners vuln --severity HIGH,CRITICAL "$image"
done
```

Results include CVE ID, package name, installed version, fixed version, and severity. Only HIGH and CRITICAL CVEs are reported; MEDIUM and LOW are suppressed to avoid noise.

### Security posture report schema

```json
{
  "schema_version": "1.0",
  "scan_date": "2026-03-30T01:00:00Z",
  "hosts": [
    {
      "host": "docker-runtime",
      "lynis_hardening_index": 72,
      "lynis_findings_count": {"warning": 5, "suggestion": 12},
      "new_findings_since_last_scan": 1
    }
  ],
  "images": [
    {
      "image": "keycloak/keycloak:25.0",
      "cves": [
        {
          "cve_id": "CVE-2026-1234",
          "severity": "HIGH",
          "package": "libc6",
          "installed": "2.36-9",
          "fixed_in": "2.36-10"
        }
      ]
    }
  ],
  "summary": {
    "total_critical_cves": 0,
    "total_high_cves": 3,
    "lowest_hardening_index": 68,
    "new_lynis_findings": 1
  }
}
```

### Status surface integration

The current generated ops portal (ADR 0074) displays a **Security Posture** panel showing:
- the latest committed receipt link
- total HIGH and CRITICAL CVEs across the scanned runtime images
- the lowest current hardening index
- per-host hardening index deltas and new finding counts

The managed Grafana platform overview dashboard also exposes security posture panels backed by the `platform_security_posture_*` Influx measurements when the workflow is configured to write metrics.

### Response policy

| Finding | Response |
|---|---|
| CRITICAL CVE in a running container image | Update the image within 48 hours; create an ADR worktree if a version pin change is needed |
| HIGH CVE in a running container image | Review within 7 days; update at next maintenance window |
| New Lynis warning finding | Review within 7 days; create an Ansible task to remediate |
| Hardening index drops > 10 points | Investigate immediately; may indicate a configuration drift or security incident |

## Consequences

**Positive**
- Security posture is measured weekly and trended; regressions are detected before they become incidents
- CRITICAL CVEs in running images trigger GlitchTip issues and are actionable within 48 hours
- The hardening index trend provides a lagging indicator of overall security health — useful for understanding whether platform changes are improving or degrading security
- The report covers both OS-level (Lynis) and container-level (Trivy) attack surfaces; neither is invisible

**Negative / Trade-offs**
- Lynis scans take 2–3 minutes per host; scanning 5 hosts sequentially adds 10–15 minutes to the Monday morning window (run in parallel via Ansible to reduce to ~4 minutes)
- Trivy image scanning requires pulling image metadata from the registry; if the registry is unreachable, the scan fails partially
- Lynis generates suggestions for improvements that are not worth addressing (e.g., enabling compiler-level stack protection on a pre-built package); a suppression list (`config/lynis-suppressions.json`) must be maintained to prevent permanent noise from known-acceptable findings

## Alternatives Considered

- **OpenSCAP / OSCAP-Ansible**: more rigorous CIS benchmark alignment; higher complexity to configure and maintain; Lynis achieves the same practical outcome with lower operational overhead
- **Wazuh (SIEM + vulnerability management)**: full SIEM platform; appropriate for enterprise; overkill for a homelab; adds 4+ GB RAM for a service that duplicates what Lynis and Trivy provide separately
- **Manual security reviews quarterly**: insufficient frequency; CVEs are published daily; a quarterly review would miss a critical CVE for up to 90 days

## Implementation Notes

- The first verified production security posture receipt was generated on 2026-03-26 and is recorded in [`receipts/security-reports/20260326T140237Z.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/security-reports/20260326T140237Z.json).
- A full worker-executed replay from `windmill-windmill_worker-1` was later verified on 2026-03-26 and wrote [`receipts/security-reports/20260326T170143Z.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/security-reports/20260326T170143Z.json) from the mirrored checkout.
- The branch-local live-apply evidence for that rollout is recorded in [`receipts/live-applies/2026-03-26-adr-0102-security-posture-live-apply.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/live-applies/2026-03-26-adr-0102-security-posture-live-apply.json).
- The live apply also hardened the repo-managed retry path: `playbooks/tasks/security-scan.yml` now removes stale Lynis pid files before a rerun, and `scripts/security_posture_report.py` can reuse cached Lynis artifacts with `--skip-lynis` when a later aggregation or publication retry is needed.
- Windmill worker portability was improved by mirroring the bootstrap SSH key into the worker checkout, preferring the Proxmox internal bridge address for guest SSH jumps from the runtime VM, and purging stale Python bytecode from the mirrored worker checkout after sync so updated repo modules are actually loaded.
- The 2026-03-26 worker replay completed end to end after that cleanup and wrote a fresh receipt from the worker checkout. Its wrapped `security_posture_report.py` process still returned `1` because the generated report summary status was `critical`, but the automation path itself completed successfully and emitted the expected `REPORT_JSON=` payload.

## Related ADRs

- ADR 0006: Security baseline for Proxmox host (Lynis validates this)
- ADR 0024: Docker guest security baseline (Lynis validates this)
- ADR 0061: GlitchTip (critical findings create issues here)
- ADR 0066: Mutation audit log (scan results recorded here)
- ADR 0068: Container image policy (Trivy validates the image policy)
- ADR 0087: Repository validation gate (Gitleaks already covers secrets in code)
- ADR 0074: Platform operations portal (security posture receipt panel)
- ADR 0093: Interactive ops portal (future interactive surface for this data)
- ADR 0097: Alerting routing (critical security findings alert through this model)
