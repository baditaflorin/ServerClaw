# Validate Repository Automation Runbook

## Purpose

This runbook defines the standard repository validation gate for infrastructure changes.

## Primary Command

Run the full validation pipeline from the repository root:

```bash
make validate
```

This is the required minimum gate before merging automation changes to `main`.

ADR 0087 adds an operator-facing push gate on top of this baseline:

```bash
make install-hooks
make pre-push-gate
```

See [docs/runbooks/validation-gate.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/validation-gate.md) for the hook installation, bypass, and post-merge workflow details.

ADR 0229 adds the private Gitea server-side replay of that gate plus the
runner-backed branch validation workflow:

```bash
export GITEA_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/admin-token.txt)"
export GITEA_BASIC_AUTH="$(printf '%s:%s' 'ops-gitea' "${GITEA_TOKEN}" | base64)"

git -c http.extraHeader="Authorization: Basic ${GITEA_BASIC_AUTH}" \
  push http://100.64.0.1:3009/ops/proxmox_florin_server.git \
  HEAD:refs/heads/codex/validation-smoke

curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  "http://100.64.0.1:3009/api/v1/repos/ops/proxmox_florin_server/actions/runs?limit=5" | \
  jq '{workflow_runs: [.workflow_runs[] | {id, status, conclusion, head_branch, head_sha}]}'
```

That push path only creates the branch ref after the server-side validation gate
passes. The subsequent workflow run executes `.gitea/workflows/validate.yml` on
runner `docker-build-lv3`.

## What The Pipeline Checks

- all managed playbooks pass Ansible syntax check
- generated platform vars are current with canonical stack and host inputs
- repository YAML files pass `yamllint`
- new or changed roles include `meta/argument_specs.yml`
- playbooks and roles pass the repo-managed `ansible-lint` policy
- shell scripts pass `shellcheck`
- repo-managed JSON artifacts pass syntax validation via `jq` when available, or a `python3` JSON parser fallback when `jq` is absent
- repo-managed Semgrep rules scan governed code surfaces and emit SARIF receipts under `receipts/sast/`
- service-owning roles ship and import explicit `tasks/verify.yml` contracts
- canonical repository data models pass schema validation
- declared-to-live attestation contracts stay covered by the focused runtime, API gateway, and ops-portal regression slice
- architecture fitness functions verify the governed replaceability scorecards and vendor exit plans for critical product ADRs
- provider-boundary anti-corruption guards keep raw provider payload selectors confined to the declared boundary translation step
- the ADR 0204 correction-loop catalog covers every governed mutating workflow exactly once
- reusable `platform/` modules do not import outward into `scripts/` composition roots or dynamically load script-only helpers
- generated status documents are current for their canonical inputs
- the workflow catalog, command catalog, control-plane lane catalog, and controller-local secret manifest cross-reference cleanly
- the API publication catalog classifies every governed API and webhook surface
- structured live-apply receipts reference valid workflows and files, and record exact source git hashes; clone-local object availability can be audited explicitly with `LV3_REQUIRE_RECEIPT_SOURCE_COMMIT_OBJECTS=1`

## Tooling Model

- validation bootstraps `uv` automatically when the host only has `python3` and not a preinstalled `uv` or `uvx` binary
- validation uses `uv tool run --from ...` for `ansible-core`, `ansible-lint`, and `yamllint`
- validation runs dependency-bearing repo Python validators through `uv run --with ... python3 ...`
- validation resolves the remaining direct `python3` validators through `LV3_VALIDATE_PYTHON_BIN` or a Python 3.10+ fallback search so `bash -lc` local fallback does not silently downgrade to an older login-shell interpreter such as macOS `/usr/bin/python3`
- the Windmill post-merge fallback reuses the worker-safe `validate_repo.sh` subset and then runs `scripts/provider_boundary_catalog.py --validate` explicitly so ADR 0207 still gets checked even when full runner-image-based manifest execution is unavailable
- the mirrored Windmill worker checkout must include `README.md`, `VERSION`, `changelog.md`, `mkdocs.yml`, `roles/`, `versions/`, and `workstreams.yaml` because the worker-safe `generated-docs` and `generated-portals` checks read those canonical inputs even when the checkout has no `.git` metadata
- repo-scoped `playbooks/windmill.yml` replays now mirror the active git worktree automatically because the worker-checkout archive dereferences the scoped-runner shard symlinks before upload
- the build-server `remote-validate` and `remote-pre-push` paths now stage one immutable content-addressed repository snapshot per run and execute from a fresh `.lv3-runs/<run_id>/repo` namespace instead of a mutable remote mirror
- `make converge-windmill` now pins `/srv/proxmox_florin_server` to the active repo worktree automatically via `windmill_worker_checkout_repo_root_local_dir=$(REPO_ROOT)`
- if a Windmill replay starts from an out-of-tree or temporary playbook path instead of the Makefile wrapper, pass `-e windmill_worker_checkout_repo_root_local_dir=/absolute/worktree/path` explicitly
- validation resolves tracked JSON files against the repo root, falls back to `python3` when `jq` is unavailable, and skips rsync-excluded generated JSON artifacts that are intentionally absent from mirrored remote workspaces
- required Ansible collections are installed from [collections/requirements.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/requirements.yml)
- validation collections are cached under `.ansible/validation/collections`
- lint-oriented stages operate on tracked repository files so unrelated local work-in-progress does not fail the repo gate
- CI runs the same contract through `make validate`
- `make validate-semgrep` replays the shared Semgrep wrapper directly and produces the same SARIF and summary artifacts used by the remote gate
- the private Gitea push gate replays the heavier validation contract remotely on `docker-build-lv3` before accepting a pushed ref
- successful branch pushes to private Gitea trigger `.gitea/workflows/validate.yml` on the same `docker-build-lv3` runner, giving a server-resident confirmation of the repo state that actually crossed the git boundary

ADR 0083 adds an alternative containerised execution path for the heavier lint and validation commands:

- `make build-check-runners` builds the pinned runner images under `docker/check-runners/`
- `make run-checks` executes manifest-backed Docker checks from [config/check-runner-manifest.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/check-runner-manifest.json)
- [docs/runbooks/docker-check-runners.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/docker-check-runners.md) records the image rebuild and publication procedure

## Optional Stage Commands

The same pipeline can be run in parts:

```bash
make validate-ansible-syntax
make validate-generated-vars
make validate-yaml
make validate-role-argument-specs
make validate-ansible-lint
make validate-shell
make validate-json
make validate-semgrep
make validate-data-models
make validate-architecture-fitness
make validate-dependency-direction
make validate-architecture-fitness
make validate-health-probes
make validate-generated-docs
```

Focused declared-to-live validation can also be replayed directly:

```bash
uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest -q tests/test_declared_live_attestation.py tests/test_api_gateway.py tests/test_interactive_ops_portal.py
uv run --with pyyaml python3 scripts/declared_live_attestation.py --repo-root . --service api_gateway --format json --timeout-seconds 5
```

`make validate-dependency-direction` enforces ADR 0208. It scans `platform/`
modules and fails when reusable code imports from `scripts/`, mutates
`sys.path` to reach script-only helpers, or dynamically loads script files
instead of receiving those dependencies from a composition root.

`make validate-role-argument-specs` enforces the ADR 0062 contract for role interfaces. It checks role directories that are new or changed relative to `origin/main`, plus any staged, unstaged, or untracked role changes in the current worktree, and fails if a touched role is missing `meta/argument_specs.yml`.

`make validate-data-models` validates the canonical machine-readable repository state, including:

- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)
- [inventory/group_vars/platform.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/platform.yml)
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json)
- [config/correction-loops.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0204-live-apply/config/correction-loops.json)
- [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json)
- [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json)
- [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/api-publication.json)
- [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json)
- [config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/health-probe-catalog.json)
- [config/provider-boundary-catalog.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/provider-boundary-catalog.yaml)
- [config/uptime-kuma/monitors.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/uptime-kuma/monitors.json)
- [config/immutable-guest-replacement-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/immutable-guest-replacement-catalog.json)
- [config/replaceability-review-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/replaceability-review-catalog.json)
- [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies)

`make validate-architecture-fitness` currently enforces ADR 0212 by checking that every governed critical product ADR carries the required `Replaceability Scorecard` and `Vendor Exit Plan` sections with non-placeholder values.

The correction-loop catalog can also be checked directly with:

```bash
python3 scripts/correction_loops.py --validate
```

## Troubleshooting

- if validation fails during collection bootstrap, rerun after confirming network access to Ansible Galaxy and package indexes
- if validation fails on generated vars, regenerate [inventory/group_vars/platform.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/platform.yml) from the canonical inputs instead of hand-editing the file
- if CI fails but local validation passes, rerun `make validate` from a clean working tree to catch unstaged or ignored-file drift
- if a local fallback or login shell picks up an older Python and direct validators fail on `int | None` or similar modern type syntax, export `LV3_VALIDATE_PYTHON_BIN=/absolute/path/to/python3.10+` and rerun
- if the build-server immutable snapshot is missing a generated JSON artifact that is intentionally excluded from `.rsync-exclude`, keep the artifact excluded and extend the validation contract only if the remote gate truly needs that file
- if a new file type needs validation, extend [scripts/validate_repo.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repo.sh) and keep `make validate` as the single top-level entry point
