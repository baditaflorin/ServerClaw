# Preserve log-shipping alert identity

The freshness collector runs on a guest. Its scrape target supplies `host`
and `role="guest"`, while each collected timestamp identifies a different
hypervisor. Using `shipper_host` for that identity avoids the scrape-label
collision. The alert must group by `shipper_host` and select the log stream
without requiring the collector itself to have `role="hypervisor"`.

The live audit found five fresh `shipper_host` series and a healthy probe,
but the installed alert's `role="hypervisor"` selector returned no series.
The producer was already corrected live; the private source still carried
the older labels. This work preserves the existing pull request's history,
updates both source surfaces, and tests two shippers sharing one guest's
actual scrape labels. Alert thresholds and delays remain unchanged.

The reviewed alert was applied at 2026-11-06 23:52:41 UTC with an atomic,
hash-checked replacement and a timestamped backup. Native `promtool` rule,
fixture and full configuration validation passed. A main-process SIGHUP
kept the Prometheus PID unchanged. Both loaded rules report healthy and
inactive, and the age expression now returns all five shippers. No probe
process or credential was changed and no synthetic notification was sent.

PR650 passed primary pipeline2410 and merged as
`d486d02754a41ad88f9376376541c0c280b6fde0`; exact-main pipeline2412 also passed.
At 2026-11-07 00:08 UTC both installed files matched freshly fetched main
byte for byte. The producer's existing timer remained active and its last
natural run succeeded. The release receipt records the exact hashes and
no-change replay. Repository release0.179.58 and platform0.179.60 record
this infrastructure-only correction, followed by the official sanitized
public export. No catalog application deployment dates change.

Release metadata follows the scoped patch workflow documented in
`ws-0514-repository-release-0-179-47`: explicit release notes for this change,
generated artifacts, enforced release readiness, and primary CI. The global
`release_manager.py` invocation refused 101 unrelated in-progress workstreams
and repeated waiver blockers before changing any version files. That refusal
is retained as a limitation; release-gate configuration and waiver records
are unchanged. This patch does not assert global product readiness or fold
unrelated Unreleased entries into its release notes.
