# Cleanup observability and final publication

The image cleanup scheduler needs both a service-failure alert and a timer
freshness alert so a safely refused or stopped cleanup cannot remain silent.
The monitoring source and its exact-main live receipt are integrated here
before the final sanitized public snapshot.

Public CI also found that sanitization changes captured configuration bytes
while leaving their private checksums in the exported manifest. The publisher
now regenerates that derived manifest in its disposable export after both
generation passes. The private capture and its operational hashes are unchanged.
An exact file-set comparison remains mandatory, and invalid paths, duplicate
entries, symlinked manifests, symlinked or invalid roots, and symlink descendants
fail publication instead of being accepted into a new manifest.

The regression exercises actual string sanitization, export checksum equality,
private byte preservation and repeatability, plus invalid file-set and root
cases. The existing strict captured-file tests remain enabled. Targeted tests
pass: 30 tests across the publisher, new export regression and private capture.

The prior public failure was the captured configuration checksum, after 1,393
fleet tests passed and 28 deployment/tool-dependent cases skipped. A newer
metadata-only pipeline was green while the primary push failed; this release
uses primary push and pull-request status contexts as its publication gate.

Plane registration was attempted; the fresh checkout has no private Plane
authentication overlay. The committed workstream shard is the Git fallback.

Monitoring source landed as `8e996667c15202c021a4cbac126e14d6653bab60`.
The final descendant `a0e84e298c18dc841e448a2fce319e7b8f152c57` also
retains only the builder artifact cleanup unit's failed bit and adds its
three-minute warning. Its full three-rule/twelve-scenario promtool suite passes;
the real zero-valued failed-state sample is ingested and all loaded rules are
healthy. No production cleanup was deliberately failed for this proof.
The final integration preserves the separately merged CI-cache alert changes.
Actual exporter-to-Prometheus comparisons confirmed that the Scanopy scrape
guard had discarded PostgreSQL cluster state on four database guests. Only
that already-required active-state bit and the image cleanup inputs are now
retained; unrelated systemd families remain dropped. Prometheus now sees six
active PostgreSQL clusters, including the existing static target and a proxy
guest's cluster. Their existing alerts remain inactive.

The broader merged-main check found one adopted-file catalog entry missing
from an otherwise correct role. The entry is fixed and the complete adopted
catalog is now an explicit CI gate alongside the new portable checksum tests.
The full focused integration passes 108 tests with 25 host-tool skips; actual
GC and PostgreSQL promtool suites pass on the monitoring guest.

Repository version advances to `0.179.56`. Platform version advances to
`0.179.59` only after the merged monitoring source was replayed exactly, both
real alert expressions and notification routing were checked without paging,
and the bounded cleanup timers were explicitly enabled after their canaries.
The final live-apply receipt records both first scheduled batch outcomes and
uses an empty application service scope. Nested release-track counters are
kept consistent with those two version fields.

Final independent review found a symlinked-ancestor boundary case. The exporter
now rejects symlinks at every capture-path component, requires resolved paths
to remain inside the resolved temporary export, refuses the source checkout
itself, and refuses hard-linked manifests. Regression cases preserve outside
private bytes on every refusal. All 19 capture tests pass on the Mac without private config. The source-root
identity check uses filesystem identity, including case aliases; that regression
skips on case-sensitive filesystems.

Final artifact preservation evidence is timestamped before the queued runner
install: 117 original protected records remain byte-identical, while the one
legitimate drift updater rotation preserves its original binary in the verified
self-update archive. The receipt records the exact helper source, binary hash,
normal successful retry and durable preservation record without claiming every
observed path remained unchanged.
