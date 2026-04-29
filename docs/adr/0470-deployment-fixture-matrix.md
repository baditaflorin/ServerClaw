# ADR 0470: Per-Deployment Fixture Inventory + Matrix CI

- Status: Accepted
- Implementation Status: Implemented (`tests/fixtures/deployments/<slug>/`, `tests/test_ws0472_deployment_fixture_matrix.py`)
- Date: 2026-04-29
- Concern: schema-drift, multi-deployment-correctness, regression-coverage
- Tags: testing, fixtures, deployment-v1, ci, matrix
- Implements: improvement #10 from the 2026-04-29 reliability review (final improvement of the sweep)
- Depends on: ADR 0440 (per-deployment registry), ADR 0457 (host pinning), ADR 0469 (vault key pull)

---

## Context

The deployment-v1 contracts (`identity.yml`, `topology.yml`, `profile.yml`, `connection.yml`) accumulated rapidly through ws-0440…ws-0471. Each schema bump landed with a per-script unit test, but no test exercises the **whole quartet for a representative deployment**. A schema rev that broke `host-pinned` while keeping `minimal` happy would slip past unit tests.

Real `.local/deployments/<slug>/` directories aren't usable as fixtures — they're gitignored, contain real secrets, and exist only on operator workstations. The CI runner has no `.local/`.

## Decision

Three synthetic deployments live under `tests/fixtures/deployments/<slug>/`:

| Slug | Purpose |
|---|---|
| `minimal` | Single-VM deployment with a literal-string SSH key. Cheapest legal fixture. |
| `multi-host` | Three VMs (gateway / postgres / runtime) with **ADR 0469 vault key references** for both `proxmox_host.key` and `guest_ssh.key`. |
| `host-pinned` | Two VMs both carrying **ADR 0457 `deployment_owner`** so the host-pinning surface gets exercised. |

Together they cover:

- string vs `{vault: ...}` SSH key forms
- single-host vs multi-host topology
- legacy (no `deployment_owner`) vs pinned (`deployment_owner: <slug>`)
- empty vs populated `extra_services` / `disabled_services` / `service_overrides`

`tests/test_ws0472_deployment_fixture_matrix.py` parametrises over the slug and contract names so each new schema field is automatically exercised across every deployment shape:

```python
@pytest.mark.parametrize("slug", DEPLOYMENT_SLUGS)
@pytest.mark.parametrize("contract", ["identity", "topology", "profile", "connection"])
def test_fixture_validates_against_schema(slug, contract): ...
```

The matrix also asserts cross-file invariants the individual schemas can't (every guest IP falls inside the identity's `platform_guest_network_cidr`, vmids are unique within a topology) — the kind of bug a schema bump can't catch but a typo will.

## What this ADR explicitly defers

- **Live converge against fixtures.** Fixtures are static YAML; running Ansible against them would require a Proxmox stub host. Out of scope.
- **Property-based generation.** A hypothesis-style generator that synthesises new fixture combinations is a worthwhile follow-up but adds CI runtime that this sweep doesn't justify yet.
- **Auto-sweep over `.local/deployments/`.** Operators may run a separate matrix locally that points at their real deployments; CI stays on the synthetic three.

## Test surface

28 tests. Each schema validation runs once per (slug × contract) pair = 12 of those 28. Adding a fourth deployment slug adds 4 more parametrisations automatically.

## References

- [ADR 0440 — Per-Deployment Identity and Artifact Isolation](0440-per-deployment-identity-and-artifact-isolation.md)
- [ADR 0457 — Host Pinning / deployment_owner](0457-host-pinning-deployment-owner.md)
- [ADR 0469 — connection.yml vault key pull](0469-connection-yml-vault-key-pull.md)
