# Current figures for the Drive refresh

The audit found a fresh aggregate on the application's cron host while the
periodically committed report was eleven days old. The daily Drive job read
the committed snapshot, rejected it before reading its credential pipe, and
then reported the upstream broken pipe as a credential failure.

The wrapper now reads the existing cron container's current aggregate through
a configured SSH target. The read has a local 1 MiB limit and a 30-second
deadline, then validates JSON, catalogue counts, dates and the existing eight-day
freshness limit before building the tool or reading a credential. The tool and
document manifest remain sourced from reviewed origin/main. Invalid exports
fail closed and retain the last success time in the failure metrics.

The installer verifies with an explicit `--dry-run` argument. This overrides
even an apply setting in its normal EnvironmentFile, without relying on the
system manager forwarding a temporary environment setting. No document writes
are part of deployment verification. Shared release files are integrated after
the source change lands.

Plane registration was attempted once. This fresh checkout has no private
Plane authentication overlay; the workstream shard is the authoritative fallback.

PR680 merged as `3be779b38813e0f1826841deb83303b26f347e76`. The official
installer applied the wrapper, helper and unit from that main commit; their
installed hashes match source. A complete dry run at 2026-11-06 17:41 UTC
validated the current live aggregate, planned nine documents/twelve phrase
replacements, exited zero and left refresh metrics unchanged. The private
target defaults were committed separately in fleet-state PR707 and installed
with mode 0600. The release integration supplies explicit root/HOME context
for transient installer verification, matching the normal service. The
mainline receipt records the details; platform version advances to 0.179.58.
