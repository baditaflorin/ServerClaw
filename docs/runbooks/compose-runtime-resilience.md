# Compose Runtime Resilience

## Purpose

Keep repo-managed compose services predictable during boot, converge, and
recovery by enforcing health-gated local dependencies instead of blind startup
ordering.

## Validate One Service

```bash
python3 scripts/validate_service_completeness.py --service dozzle
```

If the output reports `Dependency health gate: missing`, inspect the service's
compose template under `collections/ansible_collections/lv3/platform/roles/*/templates/docker-compose.yml.j2`.

## Preferred Fix Order

1. Add or reuse a safe dependency-local healthcheck.
2. Change the dependent service to `condition: service_healthy`.
3. Re-run `python3 scripts/validate_service_completeness.py --service <id>`.

Common safe patterns:

- OpenBao sidecars: `test -s <runtime env file>`
- Built-in service CLIs: e.g. `valkey-cli ping`
- Built-in health subcommands: e.g. `dozzle healthcheck`

## Bounded Exception Path

If the dependency image does not expose a safe in-container readiness signal
yet:

1. Add a short-lived `suppressed_checks.dependency_health_gate` date to the
   owning service in `config/service-completeness.json`.
2. Record the reason and follow-up in the workstream or ADR.
3. Keep the suppression short enough that the gap is reviewed deliberately.

Do not leave blind `depends_on` ordering undocumented.
