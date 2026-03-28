# Immutable Guest Replacement

This runbook documents ADR 0191: for governed production guests, the default rollout path is immutable guest replacement instead of in-place mutation.

## Inputs

- guest policy catalog: `config/immutable-guest-replacement-catalog.json`
- redundancy catalog: `config/service-redundancy-catalog.json`
- service catalog: `config/service-capability-catalog.json`
- planner and guard: `scripts/immutable_guest_replacement.py`
- Make entrypoint: `make immutable-guest-replacement-plan`

## Inspect The Policy

List the governed guests:

```bash
uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --list
```

Inspect one service:

```bash
make immutable-guest-replacement-plan service=grafana
```

Inspect one guest directly:

```bash
make immutable-guest-replacement-plan guest=monitoring-lv3
```

The planner shows:

- the governed guest and its VM metadata from inventory
- why the guest is classified as `edge`, `stateful`, or `edge_and_stateful`
- which validation mode is required before cutover
- the rollback window and rollback method
- the documented exception rule for narrow in-place mutations

## Default Production Rule

For a service whose guest is governed by ADR 0191:

1. build or refresh the replacement source image or template
2. provision the replacement guest
3. validate it through the required preview, standby, or inactive-edge mode
4. cut over traffic, leadership, or operator entrypoints
5. keep the previous guest available through the declared rollback window

The bounded `make live-apply-service` path now fails before Ansible starts if the selected service belongs to a governed guest and no explicit exception is supplied.

## Narrow Exception Path

Use an in-place mutation only when:

- the change is an emergency security fix
- the change is narrow and already known to be reversible
- you record the exception in the live-apply receipt and workstream notes

To take that exception explicitly:

```bash
make live-apply-service service=grafana env=production ALLOW_IN_PLACE_MUTATION=true EXTRA_ARGS='-e bypass_promotion=true'
```

`ALLOW_IN_PLACE_MUTATION=true` is the acknowledgement that the run is intentionally bypassing the ADR 0191 default path for one documented reason.

## Validation

Run:

```bash
uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --validate
uv run --with pytest python -m pytest -q tests/test_immutable_guest_replacement.py
```

The repository data-model gate also validates the catalog through:

```bash
uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate
```
