# Discovery Registry Maintenance Runbook

## Purpose

This runbook defines the ADR 0327 workflow for maintaining the repository's
sectional discovery registries, generated root onboarding entrypoints, and
generated onboarding packs.

## Canonical Sources

Edit these sources directly:

- `docs/discovery/repo-structure/*.yaml`
- `docs/discovery/config-locations/*.yaml`
- `docs/discovery/onboarding-packs.yaml`

Do not hand-edit these generated outputs:

- `.repo-structure.yaml`
- `.config-locations.yaml`
- `build/onboarding/*.yaml`

## Regeneration Command

Run the discovery generator from the repository root:

```bash
uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --write
```

This rewrites the root discovery entrypoints and the task-shaped onboarding
packs under `build/onboarding/`.

## Standard Update Flow

1. Edit the relevant section file under `docs/discovery/`.
2. If the task needs a new or changed onboarding bundle, update `docs/discovery/onboarding-packs.yaml`.
3. Regenerate the outputs with `scripts/generate_discovery_artifacts.py --write`.
4. Rebuild the ADR index if ADR metadata changed:

```bash
uv run --with pyyaml python3 scripts/generate_adr_index.py --write
```

5. Run the focused gate:

```bash
./scripts/validate_repo.sh agent-standards generated-docs
```

6. If broader automation changed, run the normal repo gate:

```bash
make validate
```

## What The Gate Enforces

- generated `.repo-structure.yaml` and `.config-locations.yaml` must match the section files in `docs/discovery/`
- generated onboarding packs in `build/onboarding/` must be current
- public onboarding surfaces must stay free of workstation-specific absolute paths
- public onboarding surfaces must stay free of deployment-specific hostnames, domains, and IPs

## Troubleshooting

- if `generate_discovery_artifacts.py --check` reports stale files, rerun with `--write` and review the resulting diff
- if `validate_public_entrypoints.py` fails, remove absolute paths or deployment-specific values from the discovery sources rather than suppressing the check
- if a new task area needs a smaller onboarding bundle, add a pack definition instead of expanding the root entrypoints back into monoliths
