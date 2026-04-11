# mattermost_runtime

Deploys Mattermost on `docker-runtime`, bootstraps the LV3 team and operator channels, and mirrors generated admin and webhook artifacts to `.local/mattermost/`.

Inputs: `mattermost_*`, `hostvars['postgres']`, and the mirrored database password from `roles/mattermost_postgres`.
Outputs: a private Mattermost runtime, repo-managed channels and incoming webhooks, plus `.local/mattermost/admin-password.txt` and `.local/mattermost/incoming-webhooks.json`.
