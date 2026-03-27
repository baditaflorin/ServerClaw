# Configure Renovate

## Purpose

This runbook covers the repo-managed Renovate workflow introduced by ADR 0195 for the internal Gitea repository.

## Managed Surfaces

- Renovate config: [config/renovate.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/renovate.json)
- Config schema: [docs/schema/renovate-config.schema.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/renovate-config.schema.json)
- Workflow: [.gitea/workflows/renovate.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.gitea/workflows/renovate.yml)
- Publish entrypoint: [scripts/publish_gitea_repo.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/publish_gitea_repo.py)
- Mirrored token artifact: `$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.local/gitea/renovate-token.txt`

## Converge

Refresh the internal Gitea bootstrap so the `renovate-bot` token and `RENOVATE_TOKEN` Actions secret exist:

```bash
make converge-gitea
```

Publish the current checkout into the internal Gitea default branch so the workflow exists on-platform:

```bash
make publish-gitea-repo SOURCE_REF=HEAD TARGET_REF=main
```

## Verify

Validate the repo-managed Renovate configuration:

```bash
make validate-renovate-config
```

Confirm the internal repository has the workflow file after publish:

```bash
python3 scripts/publish_gitea_repo.py --source-ref HEAD --target-ref main --verify-path .gitea/workflows/renovate.yml
```

Confirm the Gitea repository secret exists:

```bash
export LV3_GIT_COMMON_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
export GITEA_TOKEN="$(tr -d '\n' < "${LV3_GIT_COMMON_ROOT}/.local/gitea/admin-token.txt")"
curl -sS -H "Authorization: token ${GITEA_TOKEN}" \
  http://100.64.0.1:3009/api/v1/repos/ops/proxmox_florin_server/actions/secrets
```

## Notes

- the first live apply for ADR 0195 also seeds the previously empty internal Gitea repository path
- the daily workflow runs from the internal Gitea default branch, so publishing the workflow there is part of the operational contract
- the mirrored Gitea controller-local tokens live under the shared git common-root `.local/gitea/` path so the publish and verification steps work from dedicated worktrees
- Harbor- or Plane-specific PR enrichment remains follow-up work tied to ADR 0193 and ADR 0201
