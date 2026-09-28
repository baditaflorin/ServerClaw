# WS-0516: OpenBao completeness and pre-push gate blockers

## Status

`in_progress` — OpenBao's expired legacy suppression is removed in this branch.
The private readiness SLO, generated Prometheus rules/target, Grafana dashboard,
and Alertmanager rule are being added and tested. No production service was
changed by this repository-only work.

## Decision

Measure OpenBao availability from the monitoring network using its private HTTP
readiness listener on TCP/8201. The readiness endpoint returns success only
when OpenBao is initialized and unsealed, so it is an appropriate availability
indicator for secret reads and writes. Keep the management TLS/mTLS endpoint
private and do not route it through a public API gateway.

The service liveness/readiness listeners are local to their owning guest. The
monitoring Prometheus renderer now resolves remote `127.0.0.1` probe targets to
the owning inventory host's `ansible_host`, while retaining loopback for probes
owned by the monitoring guest itself. The OpenBao SLO target uses that same
runtime-control inventory address at Ansible render time, so the public catalog
does not pin a deployment-specific IP or stale subnet.

Keep `requires_secrets: true`: OpenBao has controller-local AppRole material and
manages secret-bearing backend credentials. Set `requires_compose_secrets: false`
because the OpenBao server container has no Compose `env_file` or secret-bearing
environment; the database credential is submitted to OpenBao's authenticated
API by the role with task output suppressed. Do not add a synthetic env file to
make the checklist green.

## Scope

- Remove OpenBao's expired `legacy-service` completeness suppression.
- Add its 99.5% / 30-day private readiness SLO and regenerate the Prometheus
  recording rules, burn alerts, blackbox target, and shared SLO overview panel
  from the catalog.
- Add a Grafana dashboard for readiness, availability, remaining error budget,
  probe latency, and HTTP status.
- Add an immediate readiness-failure alert with the OpenBao runbook.
- Add regression tests that prove OpenBao passes without grandfathered checks.
- Resolve remote local-listener probes from inventory at render time and retain
  local monitoring probes on loopback.

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_openbao_completeness.py tests/test_validate_service_completeness.py tests/test_generate_slo_rules.py tests/test_validate_alert_rules.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_service_completeness.py --service openbao`
- `uv run --with pyyaml --with jsonschema python scripts/generate_slo_rules.py --check`
- `uv run --with pyyaml --with jsonschema python scripts/validate_alert_rules.py`
- `LV3_VALIDATION_CHANGED_FILES_JSON='["config/service-completeness.json","config/slo-catalog.json","config/grafana/dashboards/openbao.json","config/alertmanager/rules/openbao.yml"]' uv run --with pyyaml --with jsonschema python scripts/validate_service_completeness.py --changed --validate`
- Complete the repository push gate and required Woodpecker PR/push checks before merge.

Live diagnosis on 2026-09-28 confirmed that the OpenBao container and its
cross-guest private readiness endpoint returned HTTP 200, while Prometheus
reported the readiness probe down because the rendered target was loopback.
The branch changes only repository-managed monitoring inputs; they have not
been applied to production.

The branch push gate also exposed two unrelated baseline defects, which are
included here only because they prevented this branch from reaching review:

- The PostgreSQL R2 declaration named `postgres-replica`/VMID 151, while its
  planned capacity entry was still a generic `postgres-replica-yourname`
  example at VMID 120. The capacity model now reserves the declared guest
  identity and retains `status: planned`; it does not claim that replication or
  failover is live. A regression test pins this contract.
- Exposure-registry generation used the machine's shared `.local/identity.yml`
  even though validation uses the tracked `platform_generation.identity_overlay`
  snapshot. The generator now uses the tracked snapshot for writing, matching
  validation and preventing workstation-specific domains/certificate paths
  from leaking into the public artifact. The registry was regenerated from
  that tracked snapshot and has a regression test.
- The full push-gate fallback found stale generated ADR indexes, architecture
  diagrams, and the platform manifest. These generated artifacts are refreshed
  from their tracked source data; no hand-edited topology or deployment values
  are introduced.
- Service definition files under `catalog/services/` were missing from the
  changed-path validation catalog, so a single service change widened the
  branch gate to every lane. They now select the repository/service validation
  lanes, including completeness, without triggering unrelated Packer/OpenTofu
  or full-repository scans.
- The remote builder validates a source snapshot without the caller's Git
  history. The caller now computes affected service IDs while it still has the
  merge-base and forwards that validated scope to the remote completeness
  check. Unknown, malformed, or unrecognized scopes still fail closed to a
  repository-wide check; the remote validator also rejects IDs absent from its
  current service catalog.
- The weekly HTTPS/TLS workflow catalog listed generated target/rule files and
  receipts as implementation sources. Those are outputs; the workflow now
  references its generator, runner, wrapper, runbook, and catalog instead, with
  a regression test for that distinction.
- The same schema lane then found four workflows treating ignored generated
  Uptime Kuma monitor JSON as source. Matrix Synapse, n8n, Nextcloud, and
  Uptime Kuma management now reference the tracked health-probe catalog and
  generator/consumer code instead; a regression test covers all four.
- Exposure-registry generation also resolved two private upstream addresses
  into a tracked public-facing artifact. When a route uses a private literal
  but its owning service has a portable `private_ip` inventory template, the
  generator now emits that template for the route and any prefix-proxy
  upstreams; regression coverage checks both affected services.
- The workstream surface registry now records the remote scope handoff and
  workflow-catalog changes under their existing shared contracts, and uses the
  same release-artifact contract as the other active owner of those generated
  release surfaces.

These gate remediations do not extend service-completeness suppressions or
weaken changed-service validation. A separate live database audit found both
PostgreSQL VMs writable with Patroni inactive; the capacity entry therefore
remains planned pending a safe, verified replication/failover apply.
