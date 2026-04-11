# Dependency Wave Parallel Apply

## Purpose

Run a reviewed dependency-wave manifest through the repo-managed live-apply surface so each wave acquires its locks up front, executes its internal playbooks in parallel, and stops cleanly when a blocking wave fails.

## Files

- manifest example: [config/dependency-waves/security-observability-bootstrap.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/dependency-waves/security-observability-bootstrap.yaml)
- playbook metadata catalog: [config/dependency-wave-playbooks.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/dependency-wave-playbooks.yaml)
- executor: [scripts/dependency_wave_apply.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/dependency_wave_apply.py)
- orchestration library: [platform/ansible/dependency_waves.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/ansible/dependency_waves.py)

## Manifest Rules

- every manifest declares one `plan_id`
- each wave has one unique `wave_id`
- every `parallel` item must be a `playbooks/*.yml` path
- `depends_on` may point at earlier or later-declared waves, but the full graph must stay acyclic
- a `partial_safe: true` wave may fail without blocking later waves

## Catalog Rules

- catalog entries override the fallback resolver for top-level playbooks
- `mutation_scope: host` requires `target_hosts`
- `mutation_scope: lane` requires `execution_lane`
- `mutation_scope: platform` should declare the shared surfaces used for wave-level conflict checks
- `lock_resources` should be stable resource identities, not ephemeral task names

## Dry Run

```bash
make live-apply-waves manifest=config/dependency-waves/security-observability-bootstrap.yaml WAVE_ARGS="--dry-run"
```

Review the emitted JSON before a real apply:

- `waves[].status` shows the planned order
- each result includes the resolved `make` command
- `metadata.lock_resources` shows the exclusive locks the wave will pre-acquire

## Live Apply

```bash
make live-apply-waves manifest=config/dependency-waves/security-observability-bootstrap.yaml env=production
```

Execution model:

- the executor topologically orders waves from `depends_on`
- before a wave starts, every item must pass the shard check and acquire its declared locks
- all commands inside the wave start together
- a non-`partial_safe` failure blocks later waves
- lock heartbeats run until the wave finishes, then every holder is released

## Adding A New Playbook

1. Add the playbook path to the manifest.
2. If the fallback resolver is too generic, add an explicit entry to [config/dependency-wave-playbooks.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/dependency-wave-playbooks.yaml).
3. Pick stable `shared_surfaces` and `lock_resources`.
4. Run the manifest once with `--dry-run`.
5. Only then run the real apply.

## Verification

```bash
uv run --with pytest --with pyyaml python -m pytest tests/test_dependency_wave_apply.py -q
make live-apply-waves manifest=config/dependency-waves/security-observability-bootstrap.yaml WAVE_ARGS="--dry-run"
```
