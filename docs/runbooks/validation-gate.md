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

Inspect the lane catalog and the current lane selection for this checkout:

```bash
python3 scripts/validation_lanes.py --list
python3 scripts/validation_lanes.py --resolve
```

Run the fast local hook set across the whole checkout:

```bash
uvx --from pre-commit pre-commit run --all-files
```

## Gate Definition

The authoritative gate surfaces are:

- [config/validation-gate.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/validation-gate.json)
- [config/validation-lanes.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/validation-lanes.yaml)

`config/validation-gate.json` still declares the runnable checks, container images, and commands.
`config/validation-lanes.yaml` now maps changed repo surfaces to ADR 0264 validation lanes and keeps only a small fast set of global invariants blocking for every run.

The always-blocking fast global invariants are:

- `workstream-surfaces`
- `agent-standards`

The lane-scoped checks are grouped into these blocking lanes:

- `documentation-and-adr`
- `repository-structure-and-schema`
- `generated-artifact-and-canonical-truth`
- `service-syntax-and-unit`
- `remote-builder`
- `live-apply-and-promotion`

[scripts/run_gate.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/run_gate.py) now reads both files, resolves changed files against the lane catalog, and executes only the blocking lane checks plus the fast global invariants. If a changed file does not match any declared surface class, the gate widens safely back to all lanes instead of silently skipping protection.

[scripts/parallel_check.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/parallel_check.py) still performs the container-backed execution once the blocking check set is resolved.

ADR 0230 adds `policy-validation`, which runs [scripts/policy_checks.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/policy_checks.py) against the shared `policy/` bundle and verifies the OPA or Conftest toolchain cache under `LV3_POLICY_TOOLCHAIN_ROOT`. That check now participates in the `repository-structure-and-schema` lane across the controller path, the build-server `remote-validate` path, and the worker-side Windmill post-merge gate.

Repo-managed validation installs third-party Ansible collections from the public `release_galaxy` server by default, so local Docker fallback does not depend on resolving the private `galaxy.lv3.org` endpoint just to lint or syntax-check the checkout.

The `schema-validation` stage now also runs [scripts/provider_boundary_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/provider_boundary_catalog.py) so ADR 0207 provider-boundary guards fail the gate if a declared boundary leaks raw provider payload selectors beyond its translation step.

The `integration-tests` stage runs [scripts/integration_suite.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/integration_suite.py) in `gate` mode against the `staging` environment. If the service catalog does not currently expose any active staging endpoints and no `LV3_INTEGRATION_*` overrides are supplied, the check records a structured skip and exits successfully instead of failing the gate.

The `artifact-secret-scan` stage runs [scripts/published_artifact_secret_scan.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/published_artifact_secret_scan.py) in the security runner image so published receipts and generated portal/search artifacts are checked with `gitleaks` before merge.

When the push starts from a Git worktree checkout, [scripts/remote_exec.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/remote_exec.sh) now builds one immutable content-addressed repository snapshot, uploads that archive into the active build-server session workspace, and unpacks it into a fresh `.lv3-runs/<run_id>/repo` namespace before running remote checks. The remote gate therefore validates one consistent repository image without depending on mirrored `.git/worktrees/...` metadata.
[scripts/run_python_with_packages.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/run_python_with_packages.sh) now keeps Python-based gate checks runnable inside the registry-backed runner images even when those images do not ship `uv`; the helper uses `uv` when present and otherwise falls back to the runner's native Python plus pip-installed dependencies only when imports are missing.

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

That payload now includes:

- `session_workspace` so operators can tell which controller session or worktree produced the latest result
- `lane_selection` so operators can see which lanes and checks blocked for that run
- `lane_results` so passed lanes publish reusable green-path summaries
- `fast_global_results` so the always-blocking invariants are visible separately from the selected lanes

The Windmill post-merge gate writes its most recent result to:

- `.local/validation-gate/post-merge-last-run.json`

`make gate-status` reads both files when present.

## Windmill Post-Merge Gate

Windmill should call:

```bash
python3 config/windmill/scripts/post-merge-gate.py --repo-path /srv/proxmox_florin_server
```

That workflow is seeded into the `lv3` workspace as `f/lv3/post_merge_gate`, re-runs the same lane-aware validation catalog after merge on `main`, and records the result in the worker checkout.

If the worker cannot pull the registry-backed `check-runner` images and the manifest run fails with a runner-image error, the post-merge script falls back to a worker-safe local subset:

- `./scripts/validate_repo.sh workstream-surfaces agent-standards generated-vars role-argument-specs json alert-rules generated-docs generated-portals`
- `uv run --with pyyaml python3 scripts/provider_boundary_catalog.py --validate`

That fallback intentionally omits the full `data-models` stage because mirrored worker checkouts can lack the complete historical git ancestry needed to validate every live-apply receipt `source_commit`, even when the ADR 0207 provider-boundary contract itself is healthy.
The mirrored worker checkout still needs the canonical generated-doc inputs (`README.md`, `VERSION`, `changelog.md`, `mkdocs.yml`, `roles/`, `versions/`, and `workstreams.yaml`) because the fallback keeps `generated-docs` and `generated-portals` enabled even without `.git`.
The mirrored worker checkout also needs the ADR 0230 policy surfaces (`policy/`, `scripts/policy_checks.py`, `scripts/policy_toolchain.py`, `scripts/command_catalog.py`, `scripts/gate_status.py`, and `config/windmill/scripts/gate-status.py`) because the worker-side approval and gate-status wrappers evaluate the same shared policy bundle after each sync.
The worker mirror is file-backed rather than git-backed, so `role-argument-specs` now skips empty role directories in no-git mode and `windmill_runtime` prunes stale empty directories from synchronized roots before the fallback runs.
The worker currently evaluates `generated-portals` with its local Python `3.11` interpreter, so repo-managed portal generators must remain compatible with that parser as well as the newer controller-side Python runtimes.
When the replay starts from a repo-scoped non-primary git worktree, `playbooks/windmill.yml` now mirrors that active worktree automatically because the worker-checkout archive dereferences the scoped-runner shard symlinks before upload. If the replay starts from an out-of-tree or temporary playbook path instead, rerun it with `-e windmill_worker_checkout_repo_root_local_dir=/absolute/worktree/path` so the worker mirror still reflects the branch under verification.

## Troubleshooting

- if `make install-hooks` fails during `pre-commit` bootstrap, rerun it with working internet access so `pre-commit` can fetch hook environments
- if the build server is unreachable, rerun `make pre-push-gate`; the wrapper already falls back to local Docker execution
- if the local Docker fallback is running on an emulated platform such as Apple Silicon with amd64 runner images, expect the `ansible-lint` and `ansible-syntax` stages to take several minutes; the manifest timeout budget is intentionally higher for those checks than for the lighter Python-only stages
- if two remote gate runs appear to reuse one checkout, set distinct `LV3_SESSION_ID` values and rerun so each session gets its own build-server workspace
- if a remote gate run fails with `fatal: not a git repository`, treat it as a validator regression rather than a checkout-shape requirement; the build-server path now uses immutable no-git snapshots and the affected check should be fixed to reason about repository content instead
- if the Windmill post-merge gate points at an older mirrored worker tree without the canonical generated-doc inputs, replay `windmill_runtime` first so `/srv/proxmox_florin_server` includes the full worker-safe validation surface before rerunning the gate
- if `policy-validation` fails on the build server or worker because OPA or Conftest binaries are missing, rerun the same entrypoint after clearing the cached toolchain root and ensure `LV3_POLICY_TOOLCHAIN_ROOT` points at a writable directory
- if the Windmill worker mirror picked up files from the shared checkout instead of the branch worktree, verify the replay came from the repo worktree and not a temporary playbook path; otherwise rerun `playbooks/windmill.yml` with `-e windmill_worker_checkout_repo_root_local_dir=/absolute/worktree/path` before rerunning the gate
- if the mirrored worker policy tree contains `._*` or `.DS_Store` files from a macOS checkout, replay `playbooks/windmill.yml`; ADR 0230 strips those metadata files during the repo sync before rerunning the worker gate
- if the worker-local fallback reports a removed role as missing `meta/argument_specs.yml`, replay `playbooks/windmill.yml` from the current worktree so the worker mirror prunes stale empty directories before rerunning `f/lv3/post_merge_gate`
- if the Windmill post-merge gate falls back locally because runner images cannot be pulled, treat the build-server `remote-validate` run as the authoritative full-manifest proof and use the fallback output to confirm the worker-safe ADR 0207 boundary checks still passed
- if a remote or worker-local fallback fails on `int | None` or another modern type annotation, export `LV3_VALIDATE_PYTHON_BIN=/absolute/path/to/python3.10+` before rerunning so the direct Python validators do not inherit an older login-shell interpreter
- if `packer-validate` falls back locally, inspect the build-worker plugin cache under `/opt/builds/.packer.d`; the remote gate expects the `github.com/hashicorp/proxmox` plugin to be prewarmed there when outbound GitHub access is unavailable
- if a local fallback fails because Docker is unavailable, fix the local Docker daemon or restore build-server reachability before pushing
- if `make gate-status` shows no results, run `make pre-push-gate` once to seed the local status file
