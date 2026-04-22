# Workstream WS-0396: Deterministic Service Decommissioning Live Apply

- ADR: [ADR 0396](../adr/0396-deterministic-service-decommissioning.md)
- Title: Deterministic Service Decommissioning
- Status: live applied
- Branch: `codex/ws-0396-live-apply`
- Worktree: `.worktrees/ws-0396-live-apply`
- Owner: `codex`
- Started: 2026-04-21

## Scope

- replay ADR 0396 from latest `origin/main`
- close live-apply gaps found by destructive smoke testing in a disposable copy
- verify the active SLO and HTTPS/TLS generation paths
- apply the monitoring-facing generated Prometheus assets through the governed live path
- leave branch-local evidence without touching protected release integration files

## Non-Goals

- no `VERSION` bump on the workstream branch
- no release-section edits in `changelog.md` on the workstream branch
- no top-level `README.md` integrated status summary changes on the workstream branch
- no `versions/stack.yaml` update until the verified main integration step

## Branch Fixes

- `scripts/decommission_service.py`
  - current `subdomain-catalog.json` records using `service_id`/`fqdn` are now included in runtime plans and catalog rewrites
  - `--validate-registry` keeps stdout machine-readable JSON and sends human status to stderr
  - JSON list-item registries such as `config/agent-tool-registry.json` and `config/serverclaw/approved-port-refs.json` are cleaned structurally
  - fallback line deletion skips structured JSON/YAML files
  - purge regeneration now uses `python3` and refreshes SLO, HTTPS/TLS, manifest, discovery, and workstream artifacts
- `scripts/generate_slo_rules.py`
  - the active SLO generator now wraps SLO rule and target entries in `# BEGIN SERVICE:` / `# END SERVICE:` markers
- `scripts/platform_ops.py`
  - decommission preview reports SLO and HTTPS/TLS marker files plus JSON list-item registry removals
- `scripts/uptime_contract.py`
  - generated Uptime Kuma monitor entries now carry `service_id`, matching the ADR 0396 structural cleanup contract
- `Makefile` / `tests/test_uptime_contract.py`
  - fresh worktree validation now materializes the ignored Uptime Kuma monitor artifact before checking it, and tests no longer assume the ignored artifact is already present
- tests now cover the ADR 0396 gaps found during this replay.

## Verification

Completed before live apply:

```bash
make generate-https-tls-assurance
make generate-slo-rules
make validate-generated-slo
make validate-generated-https-tls-assurance
uv run --with pytest --with pyyaml python -m pytest -q \
  tests/test_decommission_service.py \
  tests/test_data_catalog.py \
  tests/test_generate_slo_rules.py \
  tests/test_slo_tracking.py \
  tests/test_https_tls_assurance_targets.py \
  tests/test_monitoring_vm_role.py
```

Disposable destructive smoke:

```bash
python3 scripts/decommission_service.py \
  --service browser_runner \
  --purge-code \
  --confirm browser_runner \
  --validate-registry
```

Result in the disposable copy:

- `code_purged=true`
- `registry_warnings=[]`
- `integrity_errors=[]`
- regenerated SLO assets, HTTPS/TLS assurance assets, platform manifest, discovery artifacts, and workstream registry

Preview proof:

```bash
python3 scripts/platform_ops.py decommission-preview --service keycloak
```

The preview reports marker removals for:

- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/prometheus/file_sd/https_tls_targets.yml`

## Live Apply Result

Completed on 2026-04-21 from `codex/ws-0396-live-apply` based on
`origin/main` `04638e669`.

Live command:

```bash
make live-apply-service service=grafana env=production \
  ALLOW_IN_PLACE_MUTATION=true \
  EXTRA_ARGS='-e bypass_promotion=true'
```

Result:

- Grafana monitoring apply passed with `monitoring ok=254 changed=39 unreachable=0 failed=0 skipped=54 rescued=0 ignored=0`.
- Prometheus API verification passed:
  - `slo_recording_rules`: 378 rules
  - `slo_alert_rules`: 126 rules
  - `https_tls_assurance`: 165 rules
- Deployed marker verification passed:
  - `/etc/prometheus/rules/slo-rules.yml`: 42 service blocks
  - `/etc/prometheus/rules/slo-alerts.yml`: 42 service blocks
  - `/etc/prometheus/file_sd/slo-targets.yml`: 42 service blocks
  - `/etc/prometheus/rules/https-tls-alerts.yml`: 52 service blocks
  - `/etc/prometheus/file_sd/https-tls-targets.yml`: 52 service blocks
- Restic live-apply backup hook passed with receipt `receipts/restic-backups/20260421T114502Z.json`.

Branch-local live-apply evidence:

- `receipts/live-applies/2026-04-21-adr-0396-deterministic-service-decommissioning-live-apply.json`
- `receipts/live-applies/evidence/2026-04-21-ws-0396-live-apply.txt`

Final merge readiness replay on 2026-04-22 applied the PR branch to
`origin/main` `467fe6eef5b1159e5d25c3d0515083018b8274fe` in
`.worktrees/ws-0396-merge-check`. The focused pytest slice passed with
`46 passed`, and `make validate-generated-uptime-kuma-monitors` now passes from
a fresh worktree after materializing the ignored generated monitor artifact.

Note: the first live-apply attempt was blocked before Ansible by a stale
vulnerability-budget host scan. A host-only security posture refresh was recorded
at `receipts/security-reports/20260421T112535Z.json`, after which
`python3 scripts/vulnerability_budget.py --service grafana` approved the replay.

## Merge-To-Main Remainder

After this branch is merged through the PR flow:

- replay the same monitoring verification from merged `main`
- update protected integration surfaces as part of the final integration step:
  - `VERSION`
  - `changelog.md`
  - `README.md`
  - `versions/stack.yaml`
- rerun `./scripts/validate_repo.sh generated-docs`; the workstream-branch run
  truthfully failed only because `canonical_truth.py --check` wants the protected
  `changelog.md` update deferred to merge-to-main
