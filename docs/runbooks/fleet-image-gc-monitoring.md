# Image cleanup failures

`FleetRunnerArtifactGcFailed` also watches the bounded runner artifact
retention step in `builder-disk-gc.service`. Only that unit's failed-state
sample is retained through the Scanopy cardinality guard. A failure lasting
three minutes uses the existing warning route; a healthy sample is zero.
Inspect its journal and retention report, preserving current, recent, active,
referenced and unrecognized bundles. The production job is not deliberately
failed for verification: use promtool failure/clear cases and confirm the
real zero-valued sample and healthy loaded rule.

`FleetImageGcFailed` uses the existing node-exporter systemd collector. A
`fleet-image-gc-*.service` unit that remains failed for three minutes alerts
through the existing warning route. Successful oneshot units are inactive;
inactivity is normal and does not alert. The failed state persists between
hourly attempts and clears after a successful attempt.

On the scheduler host, inspect `systemctl status <unit>` and
`journalctl -u <unit>`. The wrapper returns nonzero for command failures,
timeouts and registry-unavailable candidates, while continuing independent
repositories. Registry refusal preserves images: repair registry access and
repeat the bounded dry-run before applying. Keep the age floor, deletion cap,
container and rollback references, and digest recoverability checks.

`FleetImageGcTimerStale` covers stopped, disabled and missing timers after
intentional rollout. The private scheduler rollout helper atomically writes
`fleet_image_gc_timer_expected_since_seconds{name="<timer>"}` to the existing
textfile collector before enablement. Repeating arm preserves the timestamp.
Three hours after both rollout and boot, the expected timer must have a
`node_systemd_timer_last_trigger_seconds` in the previous three hours; a missing
timer series also alerts. The marker and timer must share `host`, `instance`
and exact `name` labels. A different timer's trigger cannot keep it healthy.
The alert waits a further ten minutes before notification.

Staged, unarmed timers do not alert. Intentional retirement disables/stops the
timer and explicitly disarms only its expectation marker. Verify the timer is
enabled and scheduled, the collector reports success, and the exact units
emit their systemd series when testing installation. Hosts without the
systemd collector need it enabled. Target-down alerts cover an unreachable exporter. Logs
use the host's capped journal; the scheduler does not create unbounded log
files. Check `journalctl --disk-usage` and effective journal limits at rollout.

The rule is copied by the existing monitoring role's adopted-file list. For a
Scanopy target, the role's metric relabel guard preserves cleanup service
state, cleanup timer triggers and the per-cluster active bit needed by existing
PostgreSQL alerts; other systemd metrics remain dropped to bound cardinality.
Verify ingestion as well as exporter output and loaded rules.

For a targeted apply, pin source bytes, keep a timestamped backup, install as
root:prometheus 0640, run `promtool check rules` and full `promtool check config`,
then send SIGHUP to Prometheus and verify the loaded rule's expression and
health through `/api/v1/rules`. Roll back the file and reload if validation or
loaded health fails. A synthetic failed unit may verify collection and the
expression, but reset it before the three-minute alert delay to avoid paging.
