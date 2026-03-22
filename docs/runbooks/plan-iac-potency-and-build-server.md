# Roadmap Runbook: IaC Potency, Build Server Offload, and User Ergonomics

Version: 0.51.0
Date: 2026-03-22
ADRs: 0082–0091

---

## Purpose

This runbook describes the delivery plan for ADRs 0082–0091. These ten ADRs form a coherent programme with three goals:

1. **Offload CPU-intensive work from the operator's laptop to the build server** — lint, validate, Packer builds, and OpenTofu plans should all run on `build-lv3`, not the laptop. The laptop's role becomes "editor and orchestrator", not "build machine".

2. **Make IaC dramatically more potent** — replace ad-hoc Ansible VM creation with OpenTofu declarative state, replace raw cloud images with Packer templates, restructure roles into a versioned Ansible collection, and enforce the whole thing with a validation gate.

3. **Make the platform usable as a human** — a unified `lv3` CLI replaces 60 `make` targets, continuous drift detection answers "is anything broken?", and the entire system is navigable from a single terminal command or the ops portal.

---

## Dependency Graph

```
ADR 0082 (remote build gateway)
    ├── ADR 0083 (docker check runner)   ← needs 0082 to run containers on build server
    │       ├── ADR 0087 (validation gate)  ← needs 0083 for parallel checks
    │       ├── ADR 0086 (ansible collection)  ← needs 0083 for ansible check runner
    │       └── ADR 0089 (build cache)  ← needs 0083 to cache Docker layers
    ├── ADR 0084 (packer pipeline)  ← needs 0082 to run Packer on build server
    │       └── ADR 0085 (opentofu vm lifecycle)  ← needs 0084 for VM templates
    │               └── ADR 0088 (ephemeral fixtures)  ← needs 0085 for fixture VMs
    │                       └── ADR 0091 (drift detection)  ← needs 0085 for tofu-drift
    └── ADR 0090 (platform CLI)  ← needs 0082 for routing; 0075 for service catalog

ADR 0089 (build cache) ← needs 0082 + 0083 before cache is useful
ADR 0091 (drift detection) ← needs 0085 (tofu-drift), 0074 (ops portal), 0058 (NATS)
```

---

## Parallel Delivery Lanes

These ADRs can be worked in parallel across lanes once their blockers are met.

### Lane A — Build Server Foundation (do first; everything depends on this)

| Order | ADR | Estimated effort | Blocking |
|---|---|---|---|
| 1 | 0082 Remote Build Gateway | 4 h | all other lanes |
| 2 | 0083 Docker Check Runner | 6 h | 0087, 0086, 0089 |
| 3 | 0089 Build Cache | 3 h | speed of all later work |

Lane A is strictly sequential. Deliver all three before starting other lanes.

### Lane B — IaC Pipeline (after Lane A)

| Order | ADR | Estimated effort | Blocking |
|---|---|---|---|
| 4 | 0084 Packer Pipeline | 8 h | 0085, 0088 |
| 5 | 0085 OpenTofu VM Lifecycle | 8 h (incl. VM import) | 0088, 0091 |
| 6 | 0088 Ephemeral Fixtures | 5 h | — |

### Lane C — Code Quality and Security (after Lane A; parallel with Lane B)

| Order | ADR | Estimated effort | Notes |
|---|---|---|---|
| 4 | 0086 Ansible Collections | 10 h | largest migration effort; coordinate with active branches |
| 5 | 0087 Validation Gate | 4 h | depends on 0083 being published to registry |

### Lane D — Human Navigation (after Lane A; parallel with Lanes B and C)

| Order | ADR | Estimated effort | Notes |
|---|---|---|---|
| 4 | 0090 Platform CLI | 6 h | depends on 0082 for routing, 0075 already done |
| 5 | 0091 Drift Detection | 6 h | depends on 0085 (tofu-drift) and 0058 (NATS) |

### Recommended sequence for a solo operator

```
Week 1: 0082 → 0083 → 0089 (Lane A)
Week 2: 0084 + 0086 in parallel (Lane B start + Lane C start)
Week 3: 0085 + 0087 + 0090 in parallel (Lane B + Lane C + Lane D)
Week 4: 0088 + 0091 (Lane B finish + Lane D finish)
```

---

## New Make Targets Introduced

The full set of new `make` targets across all ten ADRs:

### Remote execution
```makefile
make remote-lint
make remote-validate
make remote-pre-push
make remote-packer-build IMAGE=<name>
make remote-image-build SERVICE=<name>
make remote-tofu-plan ENV=<env>
make remote-tofu-apply ENV=<env>
make remote-exec COMMAND=<cmd>
make check-build-server
```

### Packer templates
```makefile
make remote-packer-build IMAGE=lv3-debian-base
make remote-packer-build IMAGE=lv3-docker-host
make remote-packer-build IMAGE=lv3-postgres-host
make remote-packer-build IMAGE=lv3-ops-base
make validate-packer
```

### OpenTofu
```makefile
make remote-tofu-plan ENV=production
make remote-tofu-plan ENV=staging
make remote-tofu-apply ENV=production
make remote-tofu-apply ENV=staging
make tofu-drift ENV=<env>
make tofu-import VM=<name>
```

### Ansible Collection
```makefile
make collection-build
make collection-publish
make collection-install
```

### Validation gate
```makefile
make install-hooks
make pre-push-gate
make gate-status
```

### Fixtures
```makefile
make fixture-up FIXTURE=<name>
make fixture-down FIXTURE=<name>
make fixture-list
```

### Cache
```makefile
make warm-cache
make cache-status
```

### CLI
```makefile
make install-cli
make update-cli
```

### Drift
```makefile
make drift-report ENV=<env>
```

### Setup (run once after clone)
```makefile
make setup   # installs hooks, CLI, checks build server connectivity, installs collection
```

---

## New Windmill Workflows Introduced

| Workflow | Trigger | Purpose |
|---|---|---|
| `packer-template-rebuild` | `packer/` changes on `main`; Sunday 02:00 | Rebuild all four Packer templates |
| `platform-check-runner-rebuild` | `docker/check-runners/` changes on `main` | Rebuild check runner images |
| `warm-build-cache` | `main` merge (if relevant files change); nightly 03:00 | Pre-warm all build server caches |
| `post-merge-gate` | Every `main` merge | Re-run validation gate post-merge |
| `fixture-expiry-reaper` | Every 15 minutes | Destroy expired ephemeral fixtures |
| `continuous-drift-detection` | Every 6 hours; every `main` merge | Run all 5 drift detectors |
| `collection-publish` | `collections/` changes on `main` | Build and publish `lv3.platform` |

---

## New Config Files Introduced

| File | Purpose |
|---|---|
| `config/build-server.json` | Build server host, SSH key, workspace root, command routing |
| `config/check-runner-manifest.json` | Maps check labels to Docker images and commands |
| `config/validation-gate.json` | Authoritative check definitions for pre-push gate and Windmill CI |
| `config/vm-template-manifest.json` | Packer template VMIDs, versions, build dates |
| `config/build-cache-manifest.json` | Cache component health: image digests, sizes, last-warm |
| `.rsync-exclude` | Paths excluded from build server workspace sync (secrets, receipts) |
| `.gitleaks.toml` | gitleaks false-positive exclusions |

---

## Build Server Setup Checklist

Before starting Lane A, verify the build server meets requirements:

- [ ] `build-lv3` VM is running on Proxmox (VMID in range 100–199)
- [ ] Tailscale is active on `build-lv3`; controller can SSH as `ops` user
- [ ] Docker CE is installed; `docker buildx` is available; BuildKit is enabled
- [ ] `/opt/builds/` directory exists with 200+ GB free space
- [ ] `/etc/buildkit/buildkitd.toml` configured with 50 GB GC policy
- [ ] `apt-cacher-ng` is installed and listening on `build-lv3:3142`
- [ ] Proxmox API token for Packer/OpenTofu is in OpenBao at `secret/build-server/proxmox-api-token`
- [ ] `registry.lv3.org` is reachable from `build-lv3` (pull + push confirmed)

Run `make check-build-server` after ADR 0082 is live to verify all of the above automatically.

---

## Ansible Collection Migration Risk Management

ADR 0086 (Ansible collection packaging) is the highest-risk workstream because it touches all 40+ roles and all playbooks. Mitigation:

1. **No functional changes during migration**: the migration PR is a pure structural rename (roles → FQCN, directory move). Zero logic changes.
2. **Coordinate with active branches**: check `workstreams.yaml` for any `status: in_progress` workstream that modifies `roles/`; either complete and merge those first, or rebase them on the collection structure after migration.
3. **Backwards compatibility symlink**: `roles/` → `collections/lv3/platform/roles/` is created at the same time as the migration PR, so any branch that still references the old path continues to work until it is updated.
4. **Syntax-check gate**: `ansible-playbook --syntax-check` must pass for all playbooks before the collection migration PR merges.

---

## Success Criteria for 0.51.0

All ten ADRs are considered delivered when:

1. `make remote-lint` from the laptop completes in < 20 s (warm cache) with output streaming from `build-lv3`
2. `make remote-packer-build IMAGE=lv3-debian-base` completes and the template is live in Proxmox
3. `make tofu-drift ENV=production` exits 0 (no VM drift after initial import)
4. `lv3 status` shows a clean health table for all services
5. `lv3 diff --env production` shows no actionable drift
6. `git push` is blocked by a deliberate `ansible-lint` violation (gate is live)
7. A fixture VM is provisioned, verified, and destroyed by `make fixture-up/down FIXTURE=docker-host`
8. `lv3.platform:1.0.0` is installable from `galaxy.lv3.org`
9. The Grafana platform overview dashboard has a green `Drift Status` panel
10. The laptop's fans do not spin up during a `make lint` run

---

## Runbook Cross-References

| Topic | Runbook |
|---|---|
| Remote build gateway setup and troubleshooting | `docs/runbooks/remote-build-gateway.md` |
| Packer template builds and rebuild schedule | `docs/runbooks/packer-vm-templates.md` |
| OpenTofu VM import procedure | `docs/runbooks/tofu-vm-import.md` |
| OpenTofu day-to-day operations | `docs/runbooks/tofu-vm-lifecycle.md` |
| Ansible collection development | `docs/runbooks/ansible-collection-development.md` |
| Validation gate usage and bypass | `docs/runbooks/validation-gate.md` |
| Ephemeral fixture lifecycle | `docs/runbooks/ephemeral-fixtures.md` |
| Platform CLI reference | `docs/runbooks/platform-cli.md` |
| Drift detection and resolution | `docs/runbooks/drift-detection.md` |
| Human navigation entry point | `docs/runbooks/plan-human-navigation-and-deployment-lifecycle.md` |
