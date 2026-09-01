# Runbook: Platform Service Watchdog

## Grafana Shadow-Recovery Pilot

The first host-native recovery pilot is deliberately narrow:
`grafana-shadow-watchdog.yml` targets the monitoring host only. It first hands
Grafana off from the active `lv3-monitoring-watchdog` instance, retaining
Alertmanager observation while excluding its automatic recovery, then creates
`lv3-grafana-shadow-watchdog.timer` in a separate play.

The handoff is ordered and fail-closed: Grafana must be healthy, its native unit
must be loaded, and the legacy timer must be active before the legacy timer and
oneshot service are quiesced. The legacy script is re-rendered without a Grafana
block and its timer is verified active before the shadow timer is enabled. This
prevents two watchdogs from owning or recovering Grafana at the same time.

It probes Grafana every 30 seconds with this policy:

```yaml
recovery_driver: systemd
recovery_mode: shadow
systemd_unit: grafana-server.service
```

After two failed probes, shadow mode logs and notifies the `systemctl restart`
command that would be used. It never executes a recovery command, changes the
restart counter, or clears the failure count. The role rejects systemd
`enforce` mode, so a future systemd restart requires a separate reviewed change.

The handoff modifies only the existing monitoring watchdog's Grafana ownership
and changes Alertmanager to probe-and-alert only; neither service can be
restarted by this workflow. It does not modify
Prometheus, Docker workloads, DNS, Proxmox resources, or any client-facing
service.

## Canonical Commands

Run these only from the trusted controller checkout with the intended private
overlay:

```bash
# Read-only rendered-plan check for the Grafana-only playbook.
make check-grafana-shadow-watchdog env=production

# Apply the Grafana-only shadow policy after the check is reviewed.
make converge-grafana-shadow-watchdog env=production
```

Both targets are fixed to `playbooks/grafana-shadow-watchdog.yml`; they do not
accept a tag or extra-variable override that could broaden the pilot.

The check target performs only safe preconditions and renders the planned diff;
it does not require a newly created timer to be active. The apply target performs
the legacy handoff, verifies it, and only then enables the shadow timer.

## Preconditions

The role verifies `grafana-server.service` has `LoadState=loaded` before it
renders the watchdog script. It fails closed if the native unit is absent. The
pre-apply target service must be healthy.

The existing `lv3-monitoring-watchdog.timer` must also be active. If it is not,
stop and repair that monitoring policy before attempting a Grafana ownership
handoff.

## Failed Handoff

If the first play fails after it quiesces the legacy timer, the second play does
not run. The legacy timer may therefore remain stopped (or, if rendering
completed, it may be active with Alertmanager-only observation). Treat that as a
failed governed change: do not enable the shadow timer manually and do not edit
the rendered script. Capture both timer states and the Ansible failure, then
either correct and rerun the same governed source convergence or roll back
through the trusted controller to the last reviewed source state.

## Check Status

```bash
systemctl is-active grafana-server.service \
  lv3-monitoring-watchdog.timer \
  lv3-grafana-shadow-watchdog.timer
systemctl list-timers lv3-grafana-shadow-watchdog.timer
journalctl -u lv3-grafana-shadow-watchdog.service -n 50 --no-pager
cat /var/lib/lv3-grafana-shadow-watchdog/status.json
grep -F 'svc_name="grafana"' /usr/local/libexec/lv3-monitoring-watchdog.sh
```

For a healthy Grafana, the status entry shows `status: healthy` and
`recovery_action: none`. After two failed probes it shows
`status: unhealthy`, `recovery_mode: shadow`, and
`recovery_action: would_restart`.

The `grep` command must return no match. A match means the legacy timer still
owns Grafana; stop and re-run the governed source convergence rather than
editing the rendered script or systemd units manually.

## Trigger One Probe Cycle

```bash
systemctl start lv3-grafana-shadow-watchdog.service
journalctl -u lv3-grafana-shadow-watchdog.service -n 30 --no-pager
```

## Read a Shadow Receipt

Look for a journal line similar to:

```text
SHADOW recovery — would run 'systemctl restart grafana-server.service'
```

That line is evidence of detection and policy selection, not evidence that
Grafana was restarted. `restarts_this_hour` must remain unchanged for a shadow
receipt.

## Criteria Before Proposing Systemd Enforcement

Do not propose a systemd enforcement implementation until all of the following
are true:

1. The Grafana probe and `grafana-server.service` are verified on the intended
   target host.
2. A deliberately simulated failure has produced shadow receipts without a
   restart count or service restart.
3. An operator has accepted the two-failure threshold and six-per-hour budget.
4. Post-restart checks are defined: systemd active state, local health endpoint,
   and dashboard query availability.

## Stop or Disable the Pilot

Use only during maintenance. Disabling the shadow timer leaves Grafana without a
watchdog, because the legacy monitoring timer intentionally no longer owns it.
Do not restore legacy ownership by editing a rendered script; make a reviewed
source-level handoff change instead.

```bash
systemctl stop lv3-grafana-shadow-watchdog.timer
systemctl disable lv3-grafana-shadow-watchdog.timer
```

Re-enable it after maintenance:

```bash
systemctl enable --now lv3-grafana-shadow-watchdog.timer
```

## Related

- ADR 0421: `docs/adr/0421-platform-wide-service-watchdog.md`
- Identity-core precedent: `docs/runbooks/identity-core-watchdog.md`
