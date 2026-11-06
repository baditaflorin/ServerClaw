# WS-20261030: Activate a GitHub repository in Woodpecker by script; correct the Gitea statements

## Status

In progress. Pull request open, not merged. Nothing is applied: no Woodpecker API was called, no host was contacted, no vault entry was read. No `[live-apply]` marker.

## Why

On 2026-10-30 `baditaflorin/0pipe` was activated on `ci.0mcp` by hand (Woodpecker repo id 6). The repo had no script for it: `scripts/woodpecker_tool.py activate-repo` assumes a Gitea client and `.local/woodpecker/admin-auth.json`, and `docs/runbooks/configure-woodpecker.md` and ADR 0287 described a Gitea forge. Both production planes (`ci.0mcp`, `ci.0exec`) use GitHub (`/api/user` avatar on `avatars.githubusercontent.com`, `admin: true`; repositories with a `https://github.com/...` `forge_url`).

## Change

- `scripts/woodpecker_activate_repo.sh PLANE OWNER/REPO [--run BRANCH]`: asks the server first and refuses a non-GitHub forge, looks the repository up, activates it only when missing, optionally triggers a pipeline, waits and prints each step. The API calls run in CT108; the fleet-vault token is read there and reaches curl on stdin only. The activation response (it carries hook fields) is never printed.
- `tests/test_woodpecker_activate_repo.py`: runs the real script with shims for `ssh`, `gh` and `curl`: already activated is a no-op, activation, the `ci.0exec` entry and proxy, non-GitHub refusal, the run and its step output, a failed pipeline, bad usage, and that the token and hook marker never appear in output, command lines or logs.
- Runbook: sections "Which forge" (verified and not verified) and "Activate a repository"; the Gitea statements corrected.
- ADR 0287: a dated correction note; status fields unchanged.
- `scripts/woodpecker_tool.py`: only a comment and the help text marking `activate-repo` as the Gitea-era path. No behaviour change.

## Verification and rollback

`pytest tests/test_woodpecker_activate_repo.py tests/test_woodpecker_tool.py`, `shellcheck scripts/woodpecker_activate_repo.sh`. Roll back by reverting the change; nothing else depends on it.

## Not verified

The script has never talked to a real Woodpecker. The `--run` polling uses `GET /api/repos/<id>/pipelines/<number>`; the activation, lookup and trigger calls are the ones used by hand on 2026-10-30. Whether the `woodpecker_runtime` role still matches any running plane is not known; it was not changed.
