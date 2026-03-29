# Workstream ws-0255-main-integration

- ADR: [ADR 0255](../adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md)
- Title: Integrate ADR 0255 exact-main replay onto `origin/main`
- Status: `ready_for_merge`
- Included In Repo Version: 0.177.85
- Platform Version Observed During Integration: 0.130.58
- Release Date: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0255-main-integration-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0255-main-integration`
- Owner: codex
- Depends On: `ws-0255-live-apply`

## Purpose

Carry the verified ADR 0255 Matrix Synapse rollout onto the latest available
`origin/main`, refresh the protected release and canonical-truth surfaces for
repository version `0.177.85`, and record the exact-main production replay
that turns the branch-local live-apply evidence into the canonical mainline
receipt.

## Shared Surfaces

- `workstreams.yaml`
- `docs/adr/.index.yaml`
- `docs/adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md`
- `docs/workstreams/ws-0255-live-apply.md`
- `docs/workstreams/ws-0255-main-integration.md`
- `docs/runbooks/configure-matrix-synapse.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.85.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `scripts/https_tls_assurance_targets.py`
- `tests/test_https_tls_assurance_targets.py`
- `receipts/live-applies/2026-03-29-adr-0255-matrix-synapse-mainline-live-apply.json`

## Verification

- `git fetch origin --prune` confirmed the newest available `origin/main`
  baseline remained commit `430e364e2a810ccd6463e201fd8b7d41fed95676`
  before the final metadata and receipt integration work.
- The exact-main source commit
  `169d7e6549e539747d140497acd8a01e9049c330` preserved the Matrix runtime
  rollout and corrected the public HTTPS assurance path so
  `monitoring-lv3` now probes the internal edge target
  `https://10.10.10.10:443/_matrix/client/versions` while still validating
  host and TLS identity as `matrix.lv3.org`.
- `make converge-matrix-synapse` succeeded from the exact-main release tree
  with final recap `docker-runtime-lv3 ok=131 changed=5 failed=0 skipped=26`,
  `localhost ok=18 changed=0 failed=0 skipped=3`, `nginx-lv3 ok=38 changed=3
  failed=0 skipped=7`, `postgres-lv3 ok=51 changed=0 failed=0 skipped=11`,
  and `proxmox_florin ok=31 changed=4 failed=0 skipped=21`.
- `make converge-monitoring` succeeded after the assurance-path correction
  with final recap `monitoring-lv3 ok=397 changed=2 failed=0 skipped=76`,
  `nginx-lv3 ok=150 changed=3 failed=0 skipped=34`,
  `docker-runtime-lv3 ok=72 changed=2 failed=0 skipped=14`,
  `postgres-lv3 ok=38 changed=0 failed=0 skipped=16`,
  `proxmox_florin ok=100 changed=0 failed=0 skipped=47`,
  `backup-lv3 ok=14 changed=0 failed=0 skipped=2`,
  `coolify-lv3 ok=14 changed=0 failed=0 skipped=2`,
  and `docker-build-lv3 ok=46 changed=0 failed=0 skipped=4`.
- Public verification returned `status 200` from
  `https://matrix.lv3.org/_matrix/client/versions` and successful login for
  `@ops:matrix.lv3.org` from
  `https://matrix.lv3.org/_matrix/client/v3/login`, while the governed
  controller listener on `http://100.64.0.1:8015` returned the same account
  and homeserver identity after the exact-main replay.
- Prometheus verification on `monitoring-lv3` reported
  `matrix_https_probe_success=1`, `matrix_readiness_up=1`, and
  `matrix_liveness_up=1`, and the live file-SD target now records
  `display_url=https://matrix.lv3.org:443/_matrix/client/versions` with
  `probe_hostname=matrix.lv3.org` and internal edge connect target
  `https://10.10.10.10:443/_matrix/client/versions`.
- `uv run --with pytest --with pyyaml pytest -q tests/test_https_tls_assurance_targets.py tests/test_monitoring_vm_role.py tests/test_edge_publication_makefile.py tests/test_matrix_synapse_runtime_role.py tests/test_matrix_synapse_postgres_role.py tests/test_matrix_synapse_playbook.py tests/test_generate_platform_vars.py`
  passed with `42 passed in 2.59s`.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  `uv run --with pyyaml python scripts/canonical_truth.py --check`,
  `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`,
  `./scripts/validate_repo.sh agent-standards`, and `git diff --check`
  all passed from the integration worktree.
- `make pre-push-gate` passed from the corrected
  `ws-0255-main-integration` ownership manifest with all blocking checks
  green, including `workstream-surfaces`, `ansible-lint`,
  `generated-portals`, `schema-validation`, `security-scan`, and
  `integration-tests`.

## Outcome

- Release `0.177.85` carries ADR 0255's exact-main replay onto `main`.
- Platform version `0.130.58` remains the current integrated platform
  baseline because the exact-main replay re-verified Matrix Synapse on top of
  the already-advanced production mainline rather than introducing a newer
  platform version.
- `receipts/live-applies/2026-03-29-adr-0255-matrix-synapse-mainline-live-apply.json`
  is the canonical exact-main proof for `matrix_synapse`,
  `public_edge_publication`, and `https_tls_assurance`, while the earlier
  branch-local receipt remains preserved as the first isolated-worktree replay.
