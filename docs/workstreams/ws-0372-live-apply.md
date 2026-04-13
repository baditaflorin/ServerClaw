# WS-0372: ADR 0372 Live Apply and Automation Verification

## Goal

Close ADR 0372 from "code landed" to "governed live apply verified" on the
latest `origin/main` baseline.

## Scope

- verify the root `playbooks/` composition model that already exists on
  `origin/main`
- fix the governed `make live-apply-service` path so it loads
  `playbooks/vars/<service>.yml` when a descriptor exists
- restore any missing `playbooks/services/<service>.yml` wrappers required by
  the shared live-apply entrypoint
- align the affected playbook tests with the shared `_includes/` structure
- record branch-local validation and live-apply evidence for ADR 0372

## Findings

- `make converge-<service>` already passes `-e @playbooks/vars/<service>.yml`,
  but `make live-apply-service service=<service>` does not.
- Many root playbooks on `origin/main` already depend on shared `_includes/`
  and descriptor vars, so the governed service lane could drift from the
  operator-facing converge lane.
- `playbooks/services/keycloak.yml` and `playbooks/services/searxng.yml` are
  missing even though the root playbooks and related vars files exist.
- Several playbook tests still assert the pre-ADR inline boilerplate structure
  instead of the shared-import model now committed on `origin/main`.
- `make live-apply-service` preflight surfaced missing generated artifacts,
  schema drift in health probe data, and inconsistent service/subdomain
  bindings that required repo-side fixes before the live-apply path could
  proceed.

## Evidence

- `pytest -q tests/test_makefile_playbook_targets.py tests/test_directus_playbook.py tests/test_flagsmith_playbook.py tests/test_glitchtip_playbook.py tests/test_keycloak_playbook.py tests/test_label_studio_playbook.py tests/test_livekit_playbook.py tests/test_matrix_synapse_playbook.py tests/test_nextcloud_playbook.py tests/test_ntfy_playbook.py tests/test_plausible_playbook.py tests/test_sftpgo_playbook.py tests/test_superset_playbook.py` (pass after updates).
- `make syntax-check-directus syntax-check-flagsmith syntax-check-glitchtip syntax-check-label-studio syntax-check-livekit syntax-check-matrix-synapse syntax-check-nextcloud syntax-check-ntfy syntax-check-plausible syntax-check-sftpgo syntax-check-superset syntax-check-keycloak syntax-check-searxng` (pass after adding descriptor vars to syntax checks).
- `make generate-ops-portal` (now passes after loading host vars with identity substitution; earlier failures exposed catalog drift).
- `make generate-changelog-portal` (passes after aligning the Neko uptime monitor name with the health probe catalog).
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service directus` (passes after normalizing `config/service-redundancy-catalog.json`).
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service directus --allow-in-place-mutation`
  (passes with explicit in-place override; default gate rejects in-place mutation).
- `scripts/validate_repo.sh agent-standards` (fails because `inventory/group_vars/platform.yml` is newer than `scripts/topology-snapshot.json`, and public entrypoint validation flags deployment-specific references in `README.md`/`AGENTS.md`; both are outside this workstream’s allowed surfaces).
- `make live-apply-service service=directus env=production EXTRA_ARGS=--syntax-check`
  passes preflight and artifact bootstraps, then stops at `check-canonical-truth`
  because `changelog.md` and `versions/stack.yaml` are stale (protected files
  deferred to mainline integration).
- `make live-apply-service service=directus env=production` reaches the vulnerability
  budget gate and fails because `receipts/image-scans/2026-03-30-directus-runtime.json`
  is older than the 7-day policy window.
- `uv run --with pyyaml python scripts/security_posture_report.py --skip-lynis` fails
  with `docker-runtime: remote scan failed` because several running container tags
  (ex: `minio/minio:RELEASE.2025-07-23T15-54-02Z`) are not available locally and the
  host cannot resolve `auth.docker.io` to pull missing images.
- `python3 scripts/upgrade_container_image.py --image-id directus_runtime --write --skip-db-update`
  fails while attempting to fetch the artifact-cache mirror (`10.10.10.80:5001`);
  running with `--skip-artifact-cache` remains pending due to the same scan constraints.

## Blockers

- Vulnerability budget gates block production live applies until image scan receipts
  are refreshed or policy limits are adjusted; current receipts for the ADR 0372
  services are older than the 7-day edge-published window.
- The container image scan refresh workflow is currently blocked by missing image
  tags on docker-runtime and registry/DNS reachability for docker.io and the
  artifact-cache mirror.
