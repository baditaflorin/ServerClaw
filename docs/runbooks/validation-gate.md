# Validation Gate Runbook

## Purpose

ADR 0087 adds a push-time repository validation gate on top of the existing `make validate` contract.

The gate has two layers:

- fast local `pre-commit` hooks for syntax and secret hygiene
- a remote-first `pre-push` gate that runs the heavier parallel check suite on `build-lv3`, with local Docker fallback when the build server is unavailable

## Initial Setup

Install both hook layers after cloning the repository:

```bash
make install-hooks
```

This target:

- installs the repo-managed `pre-push` hook from `.githooks/pre-push`
- installs the `pre-commit` hook from `.pre-commit-config.yaml` through `pre-commit`

## Manual Commands

Run the full push gate without pushing:

```bash
make pre-push-gate
```

Inspect the configured checks and the last recorded outcomes:

```bash
make gate-status
```

Run the fast local hook set across the whole checkout:

```bash
uvx --from pre-commit pre-commit run --all-files
```

## Gate Definition

The authoritative gate manifest is [config/validation-gate.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/validation-gate.json).

It defines these blocking checks:

- `ansible-lint`
- `yaml-lint`
- `type-check`
- `integration-tests`
- `schema-validation`
- `ansible-syntax`
- `tofu-validate`
- `packer-validate`
- `security-scan`
- `artifact-secret-scan`
- `service-completeness`

`scripts/run_gate.py` reads that manifest and executes the checks in parallel via [scripts/parallel_check.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/parallel_check.py).

The `integration-tests` stage runs [scripts/integration_suite.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/integration_suite.py) in `gate` mode against the `staging` environment. If the service catalog does not currently expose any active staging endpoints and no `LV3_INTEGRATION_*` overrides are supplied, the check records a structured skip and exits successfully instead of failing the gate.

The `artifact-secret-scan` stage runs [scripts/published_artifact_secret_scan.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/published_artifact_secret_scan.py) in the security runner image so published receipts and generated portal/search artifacts are checked with `gitleaks` before merge.

When the push starts from a Git worktree checkout, [scripts/remote_exec.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/remote_exec.sh) now mirrors the minimal worktree git metadata into the build-server workspace before running remote checks. That keeps `git ls-files` and similar repo-aware gate commands working on `build-lv3` instead of pointing back to a laptop-local `.git/worktrees/...` path.

## Bypass Model

The supported audited bypass is:

```bash
SKIP_REMOTE_GATE=1 git push
```

That path records a receipt under [receipts/gate-bypasses](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/gate-bypasses).

`git push --no-verify` still skips both hook layers, but native Git hooks cannot observe that bypass after the fact. Treat it as break-glass only and record the reason in the change notes if it is used.

## Status Files

The gate writes the last local or remote-triggered run to:

- `.local/validation-gate/last-run.json`

That payload now includes a `session_workspace` object so operators can tell which controller session or worktree produced the latest result.

The Windmill post-merge gate writes its most recent result to:

- `.local/validation-gate/post-merge-last-run.json`

`make gate-status` reads both files when present.

## Windmill Post-Merge Gate

Windmill should call:

```bash
python3 config/windmill/scripts/post-merge-gate.py --repo-path /srv/proxmox_florin_server
```

That workflow re-runs the same `config/validation-gate.json` manifest after merge on `main` and records the result in the worker checkout.

## Troubleshooting

- if `make install-hooks` fails during `pre-commit` bootstrap, rerun it with working internet access so `pre-commit` can fetch hook environments
- if the build server is unreachable, rerun `make pre-push-gate`; the wrapper already falls back to local Docker execution
- if two remote gate runs appear to reuse one checkout, set distinct `LV3_SESSION_ID` values and rerun so each session gets its own build-server workspace
- if a remote gate run fails with `fatal: not a git repository` from a worktree path, rerun on the updated `main`; the remote sync now rewrites worktree metadata into `.git-remote/` inside the build workspace
- if `packer-validate` falls back locally, inspect the build-worker plugin cache under `/opt/builds/.packer.d`; the remote gate expects the `github.com/hashicorp/proxmox` plugin to be prewarmed there when outbound GitHub access is unavailable
- if a local fallback fails because Docker is unavailable, fix the local Docker daemon or restore build-server reachability before pushing
- if `make gate-status` shows no results, run `make pre-push-gate` once to seed the local status file
