# Workstream ws-0374-live-apply: ADR 0374 Cross-Cutting Service Manifest

- ADR: [ADR 0374](../adr/0374-cross-cutting-service-manifest.md)
- Title: repair and live-apply the ADR 0374 cross-cutting manifest on the latest `origin/main`
- Status: live_applied
- Branch: `codex/ws-0374-live-apply`
- Worktree: `.worktrees/ws-0374-live-apply`
- Owner: codex
- Depends On: `ADR 0368`, `ADR 0373`
- Conflicts With: none

## Scope

- repair the merged ADR 0374 generator and validation path so a fresh worktree can regenerate and validate the cross-cutting artifacts without relying on hidden local state
- carry the generated hairpin, TLS, DNS, proxy, and SSO data into `platform.yml` so playbooks that only load generated platform vars can see the ADR 0374 outputs
- switch runtime compose templates that still duplicated hairpin/public-host overrides over to `platform_hairpin_nat_hosts`
- replay the affected production services from the isolated worktree and verify the shared hairpin resolution path end to end

## Verification Plan

- `uv run --with pyyaml python scripts/generate_cross_cutting_artifacts.py --write`
- `uvx --from pyyaml python scripts/generate_platform_vars.py --write`
- `uv run --with pytest --with pyyaml pytest -q tests/test_generate_cross_cutting_artifacts.py tests/test_generate_platform_vars_cross_cutting.py tests/test_adr_0374_hairpin_runtime_templates.py`
- `make validate-generated-cross-cutting`
- `./scripts/validate_repo.sh generated-vars`
- production live replay and post-apply probes recorded in branch-local evidence

## Live Apply

- `make live-apply-service service=librechat env=production`
- `make live-apply-service service=litellm env=production ALLOW_IN_PLACE_MUTATION=true`
- `python3 scripts/security_posture_report.py --env production --skip-lynis --skip-trivy`

Evidence:
- `receipts/live-applies/evidence/2026-04-12-ws-0374-librechat-live-apply.txt`
- `receipts/live-applies/evidence/2026-04-12-ws-0374-litellm-live-apply.txt`
- `receipts/live-applies/evidence/2026-04-12-ws-0374-security-posture-report.txt`

## Notes

- `config/generated/` and `inventory/group_vars/platform_hairpin.yml` remain ignored by design under ADR 0407, so this workstream records live-apply evidence and generated-platform integration rather than forcing those artifacts into Git.
- The generated validators still surface pre-existing catalog drift warnings for services outside the current ADR 0374 registry coverage. Those warnings are kept visible in the evidence rather than hidden.
- The Lynis playbook could not refresh apt cache due to stale Falco/Netdata repositories, so the security posture receipt was refreshed using cached reports and `--skip-lynis --skip-trivy` to unblock the vulnerability budget gate.
- `litellm` remains governed by the immutable guest replacement policy; this apply used `ALLOW_IN_PLACE_MUTATION=true` as a narrow exception.
