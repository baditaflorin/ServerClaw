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

The `schema-validation` stage now also runs [scripts/provider_boundary_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/provider_boundary_catalog.py) so ADR 0207 provider-boundary guards fail the gate if a declared boundary leaks raw provider payload selectors beyond its translation step.

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

That workflow is seeded into the `lv3` workspace as `f/lv3/post_merge_gate`, re-runs the same `config/validation-gate.json` manifest after merge on `main`, and records the result in the worker checkout.

If the worker cannot pull the registry-backed `check-runner` images and the manifest run fails with a runner-image error, the post-merge script falls back to a worker-safe local subset:

- `./scripts/validate_repo.sh generated-vars role-argument-specs json alert-rules generated-docs generated-portals`
- `uv run --with pyyaml python3 scripts/provider_boundary_catalog.py --validate`

That fallback intentionally omits the full `data-models` stage because mirrored worker checkouts can lack the complete historical git ancestry needed to validate every live-apply receipt `source_commit`, even when the ADR 0207 provider-boundary contract itself is healthy.
The mirrored worker checkout still needs the canonical generated-doc inputs (`README.md`, `VERSION`, `changelog.md`, `mkdocs.yml`, `roles/`, `versions/`, and `workstreams.yaml`) because the fallback keeps `generated-docs` and `generated-portals` enabled even without `.git`.
When the replay starts from a non-primary git worktree, rerun `playbooks/windmill.yml` with `-e windmill_worker_checkout_repo_root_local_dir=/absolute/worktree/path` so the worker mirror reflects the branch under verification instead of the shared top-level checkout.

## Troubleshooting

- if `make install-hooks` fails during `pre-commit` bootstrap, rerun it with working internet access so `pre-commit` can fetch hook environments
- if the build server is unreachable, rerun `make pre-push-gate`; the wrapper already falls back to local Docker execution
- if two remote gate runs appear to reuse one checkout, set distinct `LV3_SESSION_ID` values and rerun so each session gets its own build-server workspace
- if a remote gate run fails with `fatal: not a git repository` from a worktree path, rerun on the updated `main`; the remote sync now rewrites worktree metadata into `.git-remote/` inside the build workspace
- if the Windmill post-merge gate points at an older mirrored worker tree without the canonical generated-doc inputs, replay `windmill_runtime` first so `/srv/proxmox_florin_server` includes the full worker-safe validation surface before rerunning the gate
- if the Windmill worker mirror picked up files from the shared checkout instead of the branch worktree, replay `playbooks/windmill.yml` with `-e windmill_worker_checkout_repo_root_local_dir=/absolute/worktree/path` before rerunning the gate
- if the Windmill post-merge gate falls back locally because runner images cannot be pulled, treat the build-server `remote-validate` run as the authoritative full-manifest proof and use the fallback output to confirm the worker-safe ADR 0207 boundary checks still passed
- if a remote or worker-local fallback fails on `int | None` or another modern type annotation, export `LV3_VALIDATE_PYTHON_BIN=/absolute/path/to/python3.10+` before rerunning so the direct Python validators do not inherit an older login-shell interpreter
- if `packer-validate` falls back locally, inspect the build-worker plugin cache under `/opt/builds/.packer.d`; the remote gate expects the `github.com/hashicorp/proxmox` plugin to be prewarmed there when outbound GitHub access is unavailable
- if a local fallback fails because Docker is unavailable, fix the local Docker daemon or restore build-server reachability before pushing
- if `make gate-status` shows no results, run `make pre-push-gate` once to seed the local status file
