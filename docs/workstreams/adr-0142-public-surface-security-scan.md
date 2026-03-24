# Workstream ADR 0142: Public Surface Automated Security Scan

- ADR: [ADR 0142](../adr/0142-public-surface-automated-security-scan.md)
- Title: Weekly external validation of the public HTTP or HTTPS surface with receipts, TLS checks, header checks, and redirect scanning
- Status: merged
- Branch: `codex/adr-0142-public-surface-scan`
- Worktree: `.worktrees/adr-0142`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0057-mattermost-chatops`, `adr-0061-glitchtip-failure-signals`, `adr-0083-docker-check-runner`, `adr-0102-security-posture-reporting`
- Conflicts With: none
- Shared Surfaces: `config/public-surface-scan-policy.json`, `scripts/public_surface_scan.py`, `config/windmill/scripts/weekly-security-scan.py`, `config/workflow-catalog.json`, `config/control-plane-lanes.json`, `receipts/security-scan/`

## Scope

- add ADR 0142
- add the public-surface scan policy and controller-side scanner
- add the Windmill wrapper and workflow catalog entry
- write public-surface receipts under `receipts/security-scan/`
- publish summary plus high or critical findings on `platform.security.*`
- document the workflow and verification steps

## Non-Goals

- active exploitation or fuzzing against production
- authenticated security testing
- mail-port vulnerability scanning
- automatic remediation of scan findings

## Expected Repo Surfaces

- `docs/adr/0142-public-surface-automated-security-scan.md`
- `docs/runbooks/public-surface-security-scan.md`
- `docs/workstreams/adr-0142-public-surface-security-scan.md`
- `config/public-surface-scan-policy.json`
- `scripts/public_surface_scan.py`
- `config/windmill/scripts/weekly-security-scan.py`
- `config/workflow-catalog.json`
- `config/control-plane-lanes.json`
- `receipts/security-scan/`
- `tests/test_public_surface_scan.py`

## Expected Live Surfaces

- Windmill can run `weekly-security-scan` from a `main` checkout
- at least one production receipt exists under `receipts/security-scan/`
- `platform.security.*` receives the summary plus any high or critical findings when enabled

## Verification

- `python3 -m py_compile scripts/public_surface_scan.py config/windmill/scripts/weekly-security-scan.py`
- `python3 scripts/public_surface_scan.py --env production --skip-testssl --skip-nuclei --print-report-json`
- `uv run --with pytest --with pyyaml --with nats-py pytest -q tests/test_public_surface_scan.py`

## Merge Criteria

- the repo-managed scanner discovers targets from canonical catalog data instead of hardcoded hostnames
- a scan run writes a structured receipt under `receipts/security-scan/`
- the workflow catalog and control-plane lane metadata describe the new scheduled diagnostic surface
- the ADR, runbook, and workstream metadata all reflect implemented repository state

## Notes For The Next Assistant

- Repository implementation is complete on `main` in repo release `0.129.0`.
- The live weekly schedule still requires apply from `main`; do not claim a platform-version change until the Windmill worker checkout is updated and a production run completes there.
