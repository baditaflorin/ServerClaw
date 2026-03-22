# monitoring_mattermost_notifications

Configures Grafana on `monitoring-lv3` to use the repo-managed Mattermost incoming webhook as an alerting contact point.

Inputs: the remote Grafana admin password and the local `.local/mattermost/incoming-webhooks.json` manifest.
Outputs: a managed Grafana contact point that targets the `platform-alerts` Mattermost channel.
