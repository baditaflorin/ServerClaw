# ADR 0102: Security Posture Reporting and Benchmark Drift

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-23

## Context

The platform has a defined security baseline for the Proxmox host (ADR 0006) and Docker guests (ADR 0024), but neither baseline is continuously verified. Security baseline checks are performed manually when initially applying a role and then assumed to remain in place. This assumption is unreliable because:

- OS packages accumulate vulnerabilities between manual audits
- Security-relevant kernel parameters can drift from their set values (sysctl drift)
- New CVEs affect packages installed on VMs without triggering any alert
- Docker images running on `docker-runtime-lv3` are built from third-party base images that may have vulnerabilities at the time of deployment that were not present at build time
- The guest firewall rules (ADR 0067) can drift from the declared policy without detection (covered by ADR 0091 at the config level, but not at the vulnerability level)

Without a continuous security scan, the platform's security posture degrades silently over time. The gap between "secure when deployed" and "secure today" widens with every month that passes without a fresh audit.

## Decision

We will implement a **weekly automated security posture report** using two complementary tools — Lynis for host/guest OS-level hardening checks and Trivy for container image vulnerability scanning — with results written to the ops portal (ADR 0093), GlitchTip (ADR 0061) for critical findings, and the mutation audit log (ADR 0066).

### Tool selection

| Tool | Scope | Output |
|---|---|---|
| Lynis | OS hardening: sysctl, file permissions, SSH config, PAM, auditd, kernel modules | Hardening index (0–100), finding list |
| Trivy | Container image CVEs: HIGH and CRITICAL only | CVE ID, severity, affected package, fixed version |
| Gitleaks | Secrets in the git history (already in the validation gate, ADR 0087) | Secret type, file, line number |

Lynis is run on: `proxmox host`, `docker-runtime-lv3`, `postgres-lv3`, `nginx-lv3`, and `monitoring-lv3`.
Trivy is run on: all running containers on `docker-runtime-lv3` and `docker-build-lv3`.

### Weekly scan workflow

A Windmill workflow `security-posture-scan` runs every Monday at 01:00 UTC:

```python
@windmill_flow(name="security-posture-scan", schedule="0 1 * * 1")
def run_security_scan():
    # Run Lynis on each VM via Ansible
    lynis_results = run_ansible_playbook(
        playbook="playbooks/tasks/security-scan.yml",
        hosts=["proxmox_host", "docker-runtime-lv3", "postgres-lv3", "nginx-lv3", "monitoring-lv3"]
    )

    # Run Trivy against all running images
    trivy_results = run_remote(
        host="docker-build-lv3",
        command="scripts/trivy_scan_running_images.sh"
    )

    report = SecurityPostureReport(lynis=lynis_results, trivy=trivy_results)
    write_report(report, path=f"receipts/security-reports/{today()}.json")
    post_to_mattermost(format_summary(report), channel="#platform-security")

    for finding in report.critical_findings():
        create_glitchtip_issue(finding)
        emit_nats_event("platform.security.critical-finding", finding)
```

### Lynis integration

Lynis is installed on each VM via the Ansible `security_baseline` role. The scan is run remotely via `ansible-playbook`:

```yaml
# playbooks/tasks/security-scan.yml
- name: Run Lynis security audit
  hosts: "{{ target_hosts }}"
  tasks:
    - name: Run Lynis
      command: lynis audit system --quiet --report-file /tmp/lynis-report.dat
      become: yes

    - name: Fetch Lynis report
      fetch:
        src: /tmp/lynis-report.dat
        dest: "/tmp/lynis-reports/{{ inventory_hostname }}.dat"
        flat: yes
```

The `scripts/parse_lynis_report.py` script parses the `.dat` report into structured JSON:

```json
{
  "host": "docker-runtime-lv3",
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

A finding that appears in the current report but not in the previous week's report is a **new finding** and creates a GlitchTip issue.

### Trivy integration

Trivy runs on the build server against the remote Docker daemons:

```bash
#!/usr/bin/env bash
# scripts/trivy_scan_running_images.sh

DOCKER_HOST=tcp://docker-runtime-lv3:2376 docker ps -q | while read cid; do
  image=$(docker inspect "$cid" --format '{{.Config.Image}}')
  trivy image --severity HIGH,CRITICAL --format json "$image"
done | jq -s '.'
```

Results include CVE ID, package name, installed version, fixed version, and severity. Only HIGH and CRITICAL CVEs are reported; MEDIUM and LOW are suppressed to avoid noise.

### Security posture report schema

```json
{
  "schema_version": "1.0",
  "scan_date": "2026-03-30T01:00:00Z",
  "hosts": [
    {
      "host": "docker-runtime-lv3",
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

### Ops portal integration

The ops portal (ADR 0093) displays a **Security Posture** panel showing:
- Lynis hardening index per host (bar chart)
- Total HIGH/CRITICAL CVEs across all images
- Trend: better/worse/same vs last week
- Link to the full report

A Grafana alert fires if the hardening index of any host drops more than 10 points below its previous value (unexpected hardening regression).

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

## Related ADRs

- ADR 0006: Security baseline for Proxmox host (Lynis validates this)
- ADR 0024: Docker guest security baseline (Lynis validates this)
- ADR 0061: GlitchTip (critical findings create issues here)
- ADR 0066: Mutation audit log (scan results recorded here)
- ADR 0068: Container image policy (Trivy validates the image policy)
- ADR 0087: Repository validation gate (Gitleaks already covers secrets in code)
- ADR 0093: Interactive ops portal (security posture panel)
- ADR 0097: Alerting routing (critical security findings alert through this model)
