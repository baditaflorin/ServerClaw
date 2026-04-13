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
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service directus` (passes after normalizing `config/service-redundancy-catalog.json`).
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service directus --allow-in-place-mutation`
  (passes with explicit in-place override; default gate rejects in-place mutation).
- `scripts/validate_repo.sh agent-standards` (fails because `inventory/group_vars/platform.yml` is newer than `scripts/topology-snapshot.json`, and public entrypoint validation flags deployment-specific references in `README.md`/`AGENTS.md`; both are outside this workstream’s allowed surfaces).
- `make live-apply-service service=directus env=production EXTRA_ARGS=--syntax-check`
  passes preflight and artifact bootstraps, then stops at `check-canonical-truth`
  because `changelog.md` and `versions/stack.yaml` are stale (protected files
  deferred to mainline integration).
