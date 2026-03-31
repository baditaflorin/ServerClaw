# changedetection_runtime

Purpose: deploy the private Changedetection.io runtime, derive notification
routes from the existing ntfy and Mattermost control plane, and reconcile the
repo-managed watch catalogue over the live API.

Use case: run from `playbooks/changedetection.yml` whenever ADR 0280 watch
catalogue, runtime image, or notification routing changes.

Inputs: the pinned image reference, private service topology, the controller
local ntfy password, the remote Mattermost webhook manifest, and the declared
watch catalogue in `defaults/main.yml`.

Outputs: a named Docker volume-backed Changedetection.io runtime, a mirrored
controller-local API token, and a converged watch/tag set that matches repo
truth.

Idempotency: Yes. The role re-renders the compose and secret artifacts, then
re-runs the API sync in check-only mode during verification to prove no drift
remains after converge.

Dependencies: ADR 0280 for the product boundary, ADR 0086 for backup scope,
ADR 0124 for ntfy routing, and the shared docker runtime baseline on
`docker-runtime-lv3`.
