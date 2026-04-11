# Failure-Domain Labels And Anti-Affinity Policy

## Purpose

Use this runbook when adding, changing, or live-applying placement metadata governed by ADR 0184.

## Repo Truth

The authoritative placement declarations live in three places:

- `config/shared-policy-packs.json`
  - declares the canonical failure-domain kinds, statuses, placement classes, and reserved-capacity exclusion vocabulary used by the validators
- `inventory/host_vars/proxmox-host.yml`
  - `platform_failure_domains` declares the currently active and planned failure domains.
  - each `proxmox_guests[]` entry declares `placement.failure_domain`, `placement.placement_class`, `placement.anti_affinity_group`, and `placement.co_location_exceptions`.
- `config/environment-topology.json`
  - each non-production environment declares `placement` metadata plus `reserved_capacity_exclusions`.

## Update Procedure

1. Update the relevant guest or environment placement metadata in repo.
2. If the placement vocabulary itself changes, update `config/shared-policy-packs.json` instead of hand-editing duplicate enums in each consumer.
3. If a standby or recovery object still shares the only active failure domain, add an explicit `co_location_exceptions` entry with a clear rationale.
4. If a preview or fixture environment shares the primary host, keep `reserved_capacity_exclusions` at least `standby` and preferably `recovery` too.
5. Validate the policy and the wider repo models:

```bash
python3 scripts/failure_domain_policy.py --validate
uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate
```

## Live Apply

Proxmox guest labels are applied from the guest placement metadata during the normal guest converge:

```bash
ANSIBLE_HOST_KEY_CHECKING=False make provision-guests
```

The role derives these live Proxmox tags from repo truth:

- the failure-domain label from `platform_failure_domains[].live_label`
- `pc-<placement_class>`
- `aag-<anti_affinity_group>`
- `exc-same-domain` when a same-domain waiver is present

## Verification

Review the rendered policy report:

```bash
python3 scripts/failure_domain_policy.py
```

Verify the live Proxmox guest tags on the host:

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 ops@203.0.113.1 sudo qm config 151
ssh -i .local/ssh/hetzner_llm_agents_ed25519 ops@203.0.113.1 sudo qm config 160
```

The `tags:` line should include the repo-derived failure-domain and anti-affinity labels.

## Operator Notes

- Do not claim cross-domain HA until another failure domain is actually active.
- Keep temporary same-domain waivers explicit and reviewable instead of silently reusing the primary host.
- Do not update `README.md`, `VERSION`, `changelog.md`, or `versions/stack.yaml` on a workstream branch unless this is the final mainline integration step.
