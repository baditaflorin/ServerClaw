# Workstream ws-0417-main-merge-edge-cert-and-sftpgo

- ADR: [ADR 0375](../adr/0375-certificate-validation-and-concordance-enforcement.md)
- Title: latest-main integration for edge certificate recovery and the SFTPGo dependency graph
- Status: `merged`
- Latest Reachable origin/main: `8e48b016a` with `VERSION=0.178.136`
- Branch: `codex/ws-0417-main-final`
- Worktree: `.worktrees/ws-0417-main-final`
- Owner: codex
- Merged in repo version: `0.178.137`

## Purpose

Land the already-verified edge certificate recovery fix onto the latest
reachable `origin/main`, preserve only the still-needed gate and generated
surface repairs, and cut the release closeout on top of `0.178.136`.

## Scope

- keep `playbooks/fix-edge-certificate.yml` aligned with the live DNS-01
  recovery flow that restored the shared edge certificate lineage
- preserve the latest-main metadata and generated-artifact repairs needed for
  the current validation bundle to pass from a clean release worktree
- repair branch-local validation blockers uncovered by the current gate:
  workstream registration, ADR index drift, generated discovery artifacts, SLO
  and HTTPS/TLS generated assets, service completeness metadata, and strict repo
  policy expectations for edge-published services
- cut `0.178.137`, archive `ws-0417`, verify the resulting release tree, and
  record the governed bypass evidence required to push `origin/main` without
  inventing false green status for unrelated baseline failures

## Verification

- release integration committed as `8335f92d2` / `0.178.137` on top of
  `origin/main@8e48b016a`
- focused validation on the final release tree passed for:
  `./scripts/validate_repo.sh data-models`
  `./scripts/validate_repo.sh cross-catalog`
  `./scripts/validate_repo.sh generated-docs`
  `CI=true ./scripts/validate_repo.sh agent-standards`
  `LV3_SNAPSHOT_BRANCH=HEAD ./scripts/validate_repo.sh workstream-surfaces`
  `python3 scripts/validate_service_completeness.py --validate`
  `uv tool run --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/fix-edge-certificate.yml --syntax-check`
  `uv tool run --from ansible-lint ansible-lint --offline playbooks/fix-edge-certificate.yml`
  `uv run pytest tests/test_edge_publication_makefile.py -q`
  `uv run pytest tests/test_ansible_execution_scopes.py -q`
- after refreshing `build/platform-manifest.json`, the exact schema-validation
  chain passed locally on `8335f92d2`:
  `./scripts/validate_repo.sh data-models >/dev/null && ./scripts/run_python_with_packages.sh pyyaml jsonschema -- scripts/platform_manifest.py --check >/dev/null && ./scripts/run_python_with_packages.sh pyyaml jsonschema -- scripts/stage_smoke_suites.py --validate >/dev/null`
- `./scripts/run_python_with_packages.sh pytest -- -m pytest tests/test_agent_tool_registry.py -q`
  passed with `11 passed`
- `./scripts/validate_repo.sh semgrep` passed locally on `8335f92d2` with
  `0` errors and `8` warnings
- the full primary-branch pre-push gate reduced to pre-existing or
  non-release-tree failures: whole-repo `ansible-lint` violations in untouched
  Ansible files, the expected archived-branch ownership mismatch, runner-image
  DNS failure for `tofu-validate`, and remote-only schema/integration/semgrep
  noise that did not reproduce in the focused local reruns above
- governed bypass receipt for the final `origin/main` push:
  `receipts/gate-bypasses/20260414T032406Z-codex-ws-0417-main-final-8335f92-skip-remote-gate.json`
- supporting evidence note:
  `receipts/live-applies/evidence/2026-04-14-ws-0417-post-merge-validation.txt`
