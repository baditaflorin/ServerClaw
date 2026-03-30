# Configure Renovate

## Purpose

This runbook covers the ADR 0297 Renovate proposal path that runs as a
scheduled or manually dispatched Gitea Actions workflow on `docker-build-lv3`.

The current implementation uses:

- a repo-root `renovate.json` contract
- a Harbor-pinned Renovate runtime image
- a dedicated `renovate-bot` Gitea identity
- an OpenBao-rendered bootstrap env file mounted into the Gitea runner
- a short-lived scoped Gitea token minted at workflow runtime

## Managed Surfaces

- workflow file: `.gitea/workflows/renovate.yml`
- repo config: `renovate.json`
- runtime helper: `scripts/renovate_runtime_token.py`
- validation hooks:
  - `scripts/validate_renovate_contract.py`
  - `scripts/renovate_stack_digest_guard.py`
- Gitea runtime bootstrap on `docker-runtime-lv3`
- OpenBao runtime and private HTTP listener on `docker-runtime-lv3`
- Gitea runner runtime on `docker-build-lv3`

## Preconditions

1. Harbor, OpenBao, Gitea, and the Gitea runner have already been converged from the current checkout.
2. `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/renovate-password.txt` exists on the controller.
3. `docker-build-lv3` can pull `registry.lv3.org/check-runner/renovate`.

## Converge

Replay the shared Gitea path from the current checkout:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/gitea.yml
```

If the workflow image has not yet been mirrored into Harbor, publish the pinned
runtime image before the first workflow run:

```bash
export HARBOR_ROBOT_JSON=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/harbor/check-runner-robot.json
export RENOVATE_UPSTREAM_REF=ghcr.io/renovatebot/renovate:42.76.4@sha256:d203eba7da7a5d198363c3d96ac6f917a4ec630b3fc2bd12501efbb2b3aa8c7d
export RENOVATE_HARBOR_REF=registry.lv3.org/check-runner/renovate:42.76.4
docker pull "${RENOVATE_UPSTREAM_REF}"
docker tag "${RENOVATE_UPSTREAM_REF}" "${RENOVATE_HARBOR_REF}"
docker login registry.lv3.org \
  --username "$(jq -r '.username' "${HARBOR_ROBOT_JSON}")" \
  --password "$(jq -r '.secret' "${HARBOR_ROBOT_JSON}")"
docker push "${RENOVATE_HARBOR_REF}"
```

## Verify

1. Confirm the Renovate bootstrap env exists on `docker-build-lv3`:

```bash
ansible docker-build-lv3 -i inventory/hosts.yml -b -m stat -a "path=/opt/gitea-runner/credentials/renovate/renovate.env"
```

2. Confirm the runner container sees the mounted credential file:

```bash
ansible docker-build-lv3 -i inventory/hosts.yml -b -m command -a "docker exec lv3-gitea-runner test -s /var/run/lv3/renovate/renovate.env"
```

3. Confirm `renovate-bot` can be discovered by the Gitea admin API:

```bash
export GITEA_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/admin-token.txt)"
curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  http://100.64.0.1:3009/api/v1/users/renovate-bot | \
  jq '{login, full_name, email, restricted, active}'
```

4. Trigger the workflow manually through the Gitea UI or API and verify the
   latest run:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -d '{"ref":"main"}' \
  "http://100.64.0.1:3009/api/v1/repos/ops/proxmox_florin_server/actions/workflows/renovate.yml/dispatches" \
  -X POST

curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  "http://100.64.0.1:3009/api/v1/repos/ops/proxmox_florin_server/actions/runs?workflow=renovate&limit=1" | \
  jq '{workflow_runs: [.workflow_runs[] | {id, status, conclusion, event, head_branch, head_sha}]}'
```

## Notes

- The bootstrap env mounted into the runner contains the durable Gitea bot
  password and scope list only. The actual PAT used by Renovate is minted at
  workflow runtime and revoked at the end of the run.
- If a Renovate, validate, or release-bundle workflow fails before repo checkout
  while pulling its Harbor-pinned job image, verify `https://registry.lv3.org`
  and a direct `docker-build-lv3` image pull before debugging the workflow
  itself. The live 2026-03-30 replay showed that stale Harbor publication drift
  can surface as `502 Bad Gateway` on the job container pull until
  `make converge-docker-publication-assurance env=production` restores the
  registry publication path.
- The private Gitea repository `ops/proxmox_florin_server` is a managed
  internal snapshot, not a mirror of GitHub `origin`. If the workflow file is
  missing from the live repo, push the intended ref to Gitea first and then
  dispatch against that explicit branch ref instead of assuming a GitHub push
  updated the internal repo.
- The private OpenBao HTTP listener for this path is intentionally reachable
  only from `docker-build-lv3`; do not widen that firewall scope without a new
  ADR-backed review.
- `versions/stack.yaml` remains protected on workstream branches. ADR 0297's
  digest cross-check is enforced through `scripts/renovate_stack_digest_guard.py`
  when a supported stack version field changes on a non-main branch.
