# NGINX2Root fleet response postmortem

**Incident date:** 2026-11-19
**Status:** Internal draft prepared for operator review and publication
**Scope:** NGINX fleet remediation and the CI reachability follow-up

## Summary

A disclosure covered five NGINX vulnerabilities: CVE-2026-123007,
CVE-2026-123634, CVE-2026-123633, CVE-2026-121810, and CVE-2026-113425.
The fixed upstream releases are NGINX stable 1.30.7 and mainline 1.31.9. The
reported NGINX2Root chain can start with an unauthenticated request; code
execution from the NGINX flaws runs with the NGINX worker's privileges. A
root-level outcome depends on an additional privilege-escalation path and host
conditions, so it is not an automatic consequence on every affected host.

The fleet response updated all 15 identified NGINX runtime instances across
eight NGINX-bearing hosts. Every runtime reported a fixed version and passed
`nginx -t`; configured container health checks were green. On eight hosts,
SCTP module autoload was disabled after confirming there were no SCTP sockets
or listeners. This is temporary containment for the separate kernel privilege
escalation path while its kernel fix remains pending.

No evidence of exploitation was established by this remediation record. The
workstream focused on patching and post-deploy checks; it did not perform a
fleet-wide forensic review, so it cannot establish that no prior exploitation
occurred.

## Response

- Installed official NGINX packages on managed Debian edge hosts and pinned
  container images to fixed vendor digests.
- Applied a verified NGINX 1.30.7 binary overlay to Harbor proxy and portal
  containers while retaining the supported Harbor release and migration path.
- Updated NGINX runtime image references, preserving dated Compose backups and
  package configuration backups for rollback.
- Disabled SCTP module autoload only on hosts where SCTP was unused; verified
  the module was unloaded and no SCTP sockets/listeners appeared afterward.
- Verified all 15 NGINX instances. Three system services were active, configured
  container health checks passed, and containers without health checks were
  confirmed running with valid NGINX configuration.

The detailed host and runtime evidence is in the
[live-apply receipt](../../receipts/live-applies/ws-20261119-nginx2root-remediation-apply-receipt.yaml),
[Grype scan receipt](../../receipts/cve/4d1d4ce08432-20261119T110658Z.grype.json),
and [patched-image scan summary](../../receipts/image-scans/2026-11-19-dify-nginx-runtime.json).

## Timeline (UTC, 2026-11-19)

| Time | Event |
| --- | --- |
| 11:06:58 | Earliest retained Grype scan receipt. This is the first timestamped artifact, not a proven incident-discovery time. |
| 12:08:07 | First recorded source commit for the fleet remediation. |
| 12:10:02 | Live-apply receipt completed. Its original start time was lost by the JSON/YAML receipt-reader defect, so patch execution duration cannot be calculated exactly. |
| 12:43:12 | PR #707 opened. |
| 14:15:45 | PR #707 merged with the fleet remediation. |
| 14:44:23 | PR #708 merged the repository integration record and version 0.179.66. |
| 16:30:23 | PR #710 restored loading of managed NGINX edge sites, including the public Woodpecker virtual host. |
| 17:35:00 | PR #711 recorded a fresh mainline converge and verification; Woodpecker push and PR checks passed. |

From the earliest retained scan artifact to the live-apply completion was
1 hour, 3 minutes, and 4 seconds. From that artifact to the security
integration merge (PR #708) was 3 hours, 37 minutes, and 25 seconds. These are
elapsed wall-clock intervals, not active engineering hours. The missing apply
start time means the actual patch run time is unknown.

The CI outage follow-up took a measured 4 minutes and 45 seconds for its
mainline reapply. Its first apply's retained Ansible window was 2 minutes and
44 seconds; diagnosis and setup were not timestamped. The CI incident record is
[`ws-20261119-ci-edge-reachability.md`](../workstreams/ws-20261119-ci-edge-reachability.md).

## Cost

No server, VM, storage volume, or other cloud resource was added or resized.
The response incurred **$0 in incremental provider charges** based on the
changes made. Package and container image downloads used existing capacity and
are not separately metered in the available billing evidence. Operator labor
and local compute/power were not tracked, so no supportable labor-cost figure
is available.

## Validation and limitations

- The remote repository gate for PR #707 reported all 26 blocking checks
  passed. GitHub recorded no Woodpecker status checks for PRs #707 or #708
  because the CI endpoint was unreachable at that time.
- The reachability defect was a missing
  `/etc/nginx/sites-enabled/*` include in the main NGINX configuration. PR #710
  fixed it. PR #711 then reapplied the merged configuration from a fresh
  `origin/main` worktree; all 36 edge certificates validated, `nginx -t`
  passed, the health endpoint returned HTTP 204 with TLS verification, and the
  unauthenticated API returned HTTP 401 as expected.
- The Woodpecker push and PR contexts passed on PRs #710 and #711. This proves
  the CI path works after the repair; it does not retroactively validate the
  security code in PR #707.
- The GitHub API returned HTTP 403 when required status checks were requested
  for this private repository because its current plan does not provide that
  branch-protection feature. The passing CI evidence remains available, but
  GitHub does not enforce it as a required merge check on this plan.
- The repository release manager still reports 105 in-progress workstreams
  and 12 repeated expired `pre_existing_gate_failures` waivers. The security
  changes are merged at repository version 0.179.66, but a new release tag has
  not been cut because these repository-wide gates remain open.
- A separate critical image-library finding remained outside the NGINX patch
  scope and is tracked under its own private scan exception. The NGINX fix does
  not resolve it.

## References

- [NGINX security advisories](https://nginx.org/en/security_advisories.html)
- [CERT-EU Security Advisory 2026-022](https://cert.europa.eu/publications/security-advisories/2026-022/pdf)
