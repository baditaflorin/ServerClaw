# ADR 0440: Per-Deployment Identity & Artifact Isolation

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Not Started
- Date: 2026-04-27
- Concern: forkability, multi-tenancy, agent-isolation, artifact-generation
- Tags: multi-deployment, generated-artifacts, identity, inventory, refactor
- Implements: ADR 0439 (Multi-Deployment Repo Architecture)
- Depends on:
  - ADR 0407 (Generic-By-Default — `.local/` Deployment Values)
  - ADR 0422 (`PLATFORM_IDENTITY_OVERLAY`)
  - ADR 0438 (Generative Cascade IaC)

---

## Context

ADR 0439 declares deployments first-class. This ADR defines the **physical
file layout** and the **loader/generator contract** that makes per-deployment
isolation real. After this ADR, no two concurrent agents can produce
overlapping diffs on identity, topology, or generated artifacts — because
those files no longer share a path.

The committed-and-shared artifacts that must move out of git and split
per-deployment:

| Today | Tomorrow |
|-------|----------|
| `.local/identity.yml` | `.local/deployments/<slug>/identity.yml` |
| `inventory/host_vars/proxmox-host.yml` | `.local/deployments/<slug>/topology.yml` |
| `inventory/group_vars/platform.yml` (committed, 192 KB) | `.local/deployments/<slug>/generated/platform.yml` (gitignored) |
| `inventory/hosts.yml` (committed) | `.local/deployments/<slug>/generated/hosts.yml` (gitignored) |
| `build/platform-manifest.json` (committed) | `.local/deployments/<slug>/generated/platform-manifest.json` (gitignored) |
| `build/onboarding/*.yaml` (committed) | `.local/deployments/<slug>/generated/onboarding/*.yaml` (gitignored) |

Today, `inventory/host_vars/proxmox-host.yml` is committed *and* gets
overlaid by `.local/identity.yml` at runtime. This ADR cleanly splits
concerns: the **committed** copy stays as a worked example of the schema
(under `publication/templates/`), and the **active** copy lives entirely
under `.local/deployments/<slug>/`.

---

## Decision

### File layout under `.local/deployments/<slug>/`

```
.local/deployments/<slug>/
├── identity.yml          # operator-authored: apex, operator, DNS, mail, networking CIDRs
├── topology.yml          # operator-authored: proxmox_guests, bridges, host IPs
├── profile.yml           # operator-authored: service allowlist (ADR 0441)
├── generated/            # tool-authored, gitignored, regenerated on demand
│   ├── platform.yml      # derived facts library (today's group_vars/platform.yml)
│   ├── hosts.yml         # ansible inventory (today's inventory/hosts.yml)
│   ├── platform-manifest.json
│   ├── adr-index.yaml    # generated index of ADRs scoped to this deployment's enabled services
│   └── onboarding/
│       ├── agent-core.yaml
│       ├── automation.yaml
│       ├── service-catalog.yaml
│       └── fork-bootstrap.yaml
├── secrets/              # operator-authored: per-service credentials, openbao snapshots
│   ├── openbao/
│   ├── keycloak/
│   └── ...
├── receipts/             # tool-authored: live-apply evidence per service
│   └── <service>-<date>-<slug>.json
└── state/                # tool-authored, ephemeral
    └── last-converge.json
```

### Identity loader contract (`scripts/deployment.py`)

A new module `scripts/deployment.py` becomes the single source of truth
for resolving "which deployment am I operating on?" Every other script
imports from it.

```python
# scripts/deployment.py
from pathlib import Path

REPO_ROOT: Path  # resolved by walking up to find pyproject.toml or .git
DEPLOYMENTS_DIR: Path  # = REPO_ROOT / ".local" / "deployments"

def resolve_active_slug(
    explicit: str | None = None,         # --deployment CLI flag
    env_var: str = "DEPLOYMENT",         # env var override
    worktree_marker: str = ".deployment", # .claude/worktrees/<name>/.deployment
    active_file: str = ".local/active-deployment",
) -> str:
    """
    Precedence:
      1. explicit (CLI flag)
      2. $DEPLOYMENT
      3. .deployment file in current worktree
      4. .local/active-deployment
      5. error if none — never silently default to "prod"
    """

def load(slug: str) -> Deployment:
    """Load identity + topology + profile, validate against schemas, return Deployment object."""

def list_all() -> list[str]:
    """Return all slugs that have a directory under .local/deployments/."""

class Deployment:
    slug: str
    identity: dict      # parsed identity.yml
    topology: dict      # parsed topology.yml
    profile: dict       # parsed profile.yml (ADR 0441)
    generated_dir: Path # .local/deployments/<slug>/generated
    secrets_dir: Path   # .local/deployments/<slug>/secrets
    receipts_dir: Path
```

**No more silent defaults to `prod`**. If no deployment is resolvable,
the loader raises `DeploymentNotResolvedError` with a message instructing
the operator to run `make use-deployment slug=<slug>` or pass
`deployment=<slug>` on the CLI.

### Generator contract changes

Every script that generates an artifact now takes `--deployment <slug>`
and writes to `.local/deployments/<slug>/generated/`. List of scripts to
update (from the survey):

| Script | Today's output | New output |
|--------|----------------|------------|
| `scripts/generate_platform_vars.py` | `inventory/group_vars/platform.yml` | `.local/deployments/<slug>/generated/platform.yml` |
| `scripts/generate_inventory.py` | `inventory/hosts.yml` | `.local/deployments/<slug>/generated/hosts.yml` |
| `scripts/platform_manifest.py` | `build/platform-manifest.json` | `.local/deployments/<slug>/generated/platform-manifest.json` |
| `scripts/generate_discovery_artifacts.py` | `build/onboarding/*.yaml` | `.local/deployments/<slug>/generated/onboarding/*.yaml` |
| `scripts/generate_release_notes.py` | `docs/release-notes/` | unchanged (release notes are repo-scoped, not deployment-scoped) |
| `scripts/generate_adr_index.py` | `docs/adr/.index.yaml` | unchanged (ADR catalog is repo-scoped) |
| `scripts/workstream_registry.py` | `workstreams.yaml` | unchanged (repo-scoped, but each entry now carries a `deployment` field — ADR 0442) |
| `scripts/audit_sanitization_coverage.py` | scans `.local/identity.yml` | scans every `.local/deployments/*/identity.yml` |
| `scripts/publish_to_serverclaw.py` | reads `.local/identity.yml` for leak markers | reads union of all `.local/deployments/*/identity.yml` |

### Ansible loader contract

Ansible playbooks today load identity from
`inventory/group_vars/all/identity.yml` (the generic seed) plus the
`-e @<overlay-path>` extra-vars injected by the Makefile. The new contract:

- `inventory/group_vars/all/identity.yml` keeps the generic placeholders
  exactly as today (this is what publishes to the public repo unchanged).
- The Makefile passes **two** extra-vars files for every play:
  ```
  -e @.local/deployments/<slug>/identity.yml
  -e @.local/deployments/<slug>/topology.yml
  ```
- The Makefile additionally passes:
  ```
  -e platform_deployment_slug=<slug>
  -e platform_deployment_dir=<absolute-path>
  ```
  so any role that needs to read/write deployment-scoped state knows
  the path. (Used by receipts, openbao snapshot dirs, etc.)
- The active inventory is `.local/deployments/<slug>/generated/hosts.yml`
  (Makefile threads `-i <path>`).
- `inventory/group_vars/platform.yml` is no longer loaded as a static
  group_vars file; instead, `.local/deployments/<slug>/generated/platform.yml`
  is loaded as `-e @<path>`. This is a behaviour change: facts that today
  are "group_vars/platform.yml-defined" become "extra-vars-defined",
  which raises Ansible variable precedence one tier. We accept this —
  no role currently overrides those facts intentionally, and the
  precedence change makes per-deployment overrides cleaner.

### Validation

`scripts/deployment.py::Deployment.validate()` runs JSON Schema
validation against three schemas, all stored in
`config/contracts/deployment-v1/`:

- `identity.schema.json` — required: `platform_domain`,
  `platform_operator_email`, `platform_operator_name`,
  `hetzner_dns_zone_name`, `hetzner_dns_zone_id`, `tailscale_tailnet`.
- `topology.schema.json` — required: `proxmox_guests` (non-empty list),
  `network_bridges`, `host_public_ipv4`.
- `profile.schema.json` — defined in ADR 0441.

Validation runs at `make generate` time (fail fast before writing any
generated artifact) and as part of the pre-push gate.

---

## Consequences

### Positive

- Two agents on two deployments cannot collide on identity, topology, or
  generated artifacts — the paths are disjoint by construction.
- The committed view of the repo gets *smaller and more generic*:
  192 KB `platform.yml` and the entire `build/` directory leave the
  index. Diffs become reviewable.
- Adding a new deployment is `mkdir .local/deployments/<slug>/` plus
  three YAML files. No code changes.
- The `--deployment` flag becomes the one-knob operator surface; once
  set (or active), every script does the right thing.

### Negative

- All scripts and the Makefile gain a `--deployment` parameter. The
  CI gate must thread it through too.
- Existing CI pipelines that diff against `inventory/group_vars/platform.yml`
  to detect topology drift must move to
  `.local/deployments/<slug>/generated/platform.yml`, which is *not* in
  git. New approach: regenerate in CI, then diff against a
  per-deployment SHA-256 sum that *is* committed (one line per
  deployment in `config/deployments-checksums.yaml`).
- Ansible variable precedence shift (group_vars → extra_vars for
  platform.yml). One-time audit needed to confirm no role intentionally
  overrides those facts at a higher tier.

### Neutral

- `inventory/group_vars/all/*.yml` (generic seed) survives unchanged.
- Roles, playbooks, and templates do not change. They continue to read
  `platform_domain`, `proxmox_guests`, `lv3_service_topology` etc. from
  whatever tier provides them.

---

## Migration plan

Implementation Phase 1 (one PR, lands behind a feature flag):

1. Add `scripts/deployment.py` and the JSON Schemas under
   `config/contracts/deployment-v1/`.
2. Add `scripts/migrate_to_multi_deployment.py` with two modes:
   `--dry-run` (default) and `--apply`. It:
   - Reads `.local/identity.yml`, `inventory/host_vars/proxmox-host.yml`,
     `inventory/group_vars/platform.yml`, `inventory/hosts.yml`,
     `build/platform-manifest.json`, `build/onboarding/*`.
   - Writes them under `.local/deployments/prod/` per the layout above.
   - Generates `.local/deployments/prod/profile.yml` from the live
     `lv3_service_topology` (every currently-running service →
     allowlist entry).
   - Writes `.local/active-deployment` with `prod`.
3. Add the new `--deployment` flag to every generator script (default:
   resolve via `deployment.py`). Old behaviour preserved if no
   `--deployment` and `.local/active-deployment` exists.
4. Add `MULTI_DEPLOYMENT_ENABLED=1` env var: when set, the Makefile
   threads `--deployment` everywhere; when unset, behaves as today.
   This is the feature flag.

Phase 2 (one PR, flips the flag):

5. Operator runs `python scripts/migrate_to_multi_deployment.py --apply`.
6. Set `MULTI_DEPLOYMENT_ENABLED=1` as the default in the Makefile.
7. Delete the old paths from git:
   - `inventory/host_vars/proxmox-host.yml` (move template to `publication/templates/topology.example.yml`)
   - `inventory/group_vars/platform.yml`
   - `inventory/hosts.yml`
   - `build/platform-manifest.json`
   - `build/onboarding/*`
8. Update `.gitignore` to ignore `.local/deployments/*/generated/`.

Phase 3 (one PR):

9. Add `make new-deployment slug=<slug> apex=<apex>` scaffolding target.
10. Bootstrap `.local/deployments/0fork/` from the existing
    `.local/identity.yml.0fork` and `.local/0fork/`.
11. Verify `make generate deployment=0fork` and `make generate deployment=prod`
    produce non-overlapping artifact trees.

### Rollback

Phase 1 is reversible: revert the PR, delete `.local/deployments/`.
Phase 2 is reversible by re-running migration in reverse mode
(`--rollback` flag on the migrate script copies generated files back to
the old paths).

---

## Open Questions

1. **Where do `.local/<service>/` per-service secret directories migrate to?**
   `.local/openbao/`, `.local/keycloak/`, `.local/gitea/` etc. become
   `.local/deployments/<slug>/secrets/<service>/`. But many services
   today read paths via Jinja templating that hardcodes `.local/<svc>/`.
   A second sweep replaces these with `{{ platform_deployment_dir }}/secrets/<svc>/`.
   Tracked in implementation Phase 4 (out of scope for this ADR's main
   migration).

2. **How does `inventory/group_vars/proxmox_hosts.yml` interact with
   per-deployment topology?** Today it contains values that are arguably
   per-deployment (Proxmox API credentials path, datastore names). They
   move into `topology.yml`. *Tentative*: yes, single round of edits
   moving Proxmox-API specifics into per-deployment topology.

3. **Receipts for live-apply evidence.** Today they live in
   `versions/stack.yaml::live_apply_evidence`. They become
   `.local/deployments/<slug>/receipts/`, and `versions/stack.yaml`
   gains a per-deployment block. Tracked in ADR 0442.
