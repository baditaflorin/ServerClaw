# Public Status Page

## Purpose

This runbook manages the public `status.lv3.org` surface introduced by ADR 0109.

It covers:

- the Uptime Kuma status page definition served at `https://status.lv3.org`
- maintenance-window publication into the public page
- independent Uptime Robot monitoring for last-resort outage detection

## Repo Surfaces

- `config/uptime-kuma/status-page.json`
- `config/uptime-robot/public-status-monitoring.json`
- `scripts/uptime_kuma_tool.py`
- `scripts/uptime_robot_tool.py`
- `scripts/maintenance_window_tool.py`

## Primary Commands

Reconcile the Uptime Kuma status page definition:

```bash
make uptime-kuma-manage ACTION=ensure-status-page
```

List the live Uptime Kuma maintenance records:

```bash
make uptime-kuma-manage ACTION=list-maintenances
```

Reconcile the external Uptime Robot contacts and monitors:

```bash
make uptime-robot-manage ACTION=ensure
```

List the external Uptime Robot monitors:

```bash
make uptime-robot-manage ACTION=list-monitors
```

## Expected Result

- `status.lv3.org` proxies the Uptime Kuma status page slug `lv3-platform`
- the public page shows the repo-managed public monitor groups
- `make open-maintenance-window ...` posts or updates a matching Uptime Kuma maintenance entry for the affected public monitor set
- Uptime Robot keeps three 5-minute monitors active for SSO, Grafana, and the public status page itself

## Verification

Confirm the public page route responds:

```bash
curl -I https://status.lv3.org
```

Confirm the Uptime Kuma page definition is present:

```bash
make uptime-kuma-manage ACTION=ensure-status-page
```

Confirm the independent monitors exist:

```bash
make uptime-robot-manage ACTION=list-monitors
```

Open a short maintenance window and confirm it appears in Uptime Kuma:

```bash
make open-maintenance-window SERVICE=keycloak REASON="status-page verification" DURATION_MINUTES=5
make uptime-kuma-manage ACTION=list-maintenances
make close-maintenance-window SERVICE=keycloak
```

## Notes

- The public page intentionally excludes private-only services and avoids recursive self-monitoring from Uptime Kuma itself. Independent coverage for `status.lv3.org` comes from Uptime Robot.
- `uptime_robot_api_key` and `uptime_robot_mattermost_webhook` are controller-local mirrors. Keep them outside git and source them from the approved secret store.
- The Uptime Robot wrapper uses the documented legacy `/v2/` API endpoints because they publicly expose the monitor, alert-contact, and status-page contract needed by this repo automation.
