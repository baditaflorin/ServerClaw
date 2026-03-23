# ADR 0110: Platform Versioning, Release Notes, and Upgrade Path

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-23

## Context

ADR 0008 defines a versioning model for the repository and platform: semantic versioning, repo version bumped on `main` merge, platform version bumped on live apply. The mechanism works. What does not exist is the **meaning** of a version bump:

- What is the difference between a major, minor, and patch version bump?
- What obligations does a major version bump create? Are there migration steps? Can operators skip major versions?
- When is a change considered "breaking" at the platform level?
- What constitutes a release, and how is it communicated to platform users?

Without these definitions, version numbers are arbitrary counters. The repository is currently at `0.93.0`. This number means the repo has had 93 minor-level ADR merges, but it communicates nothing about stability, compatibility, or what changed between `0.92.0` and `0.93.0`.

As the platform approaches production-ready status (the goal of ADRs 0092–0111), a version `1.0.0` should be a meaningful milestone, not just the next increment. For `1.0.0` to be meaningful, version semantics must be defined.

## Decision

We will define platform-level semantic versioning semantics, a structured release process, machine-readable release notes, and an upgrade path document that specifies what operators must do to move between major versions.

### Version semantics

| Component | Meaning | Triggers |
|---|---|---|
| **MAJOR** (X.0.0) | A change that requires operator action before the platform can function correctly | VM removal, service removal, breaking API change in the platform gateway, secret format change, OS upgrade |
| **MINOR** (0.X.0) | A new capability or service added; backward compatible; no operator action required | New service deployed, new ADR implemented, new Grafana dashboard, new CLI command |
| **PATCH** (0.0.X) | A bug fix, configuration correction, or documentation update | Corrected Ansible template, fixed health probe URL, updated package version, typo fix in ADR |

A **breaking change** at the platform level is defined as any change that:
- Removes a service from `config/service-capability-catalog.json`
- Removes or renames an endpoint from `config/api-gateway-catalog.json`
- Removes a Keycloak realm or client that existing operators depend on
- Changes the OpenBao secret path or format of a secret that services read at startup
- Changes the VM network addressing (IP addresses)
- Requires a one-time operator action that cannot be automated

Breaking changes always bump MAJOR. Everything else follows the table above.

### Release definition

A **release** is a `main` branch state that has:
1. A version tag (`v0.93.0`)
2. A `RELEASE.md` file in the root with structured release notes
3. All changes from the `Unreleased` changelog section moved to a versioned section
4. A `versions/stack.yaml` entry recording the platform state at release

A release is created by:
```bash
lv3 release --version 1.0.0  # or: --bump minor | --bump patch
```

This command:
1. Validates that all workstreams are `merged` or `live_applied` (no in-progress work can be released)
2. Updates `VERSION`, `changelog.md`, and `versions/stack.yaml`
3. Creates a git tag `v1.0.0`
4. Pushes tag to the remote
5. Publishes the release notes to the docs site changelog page (ADR 0094)

### Structured release notes

`RELEASE.md` (overwritten on each release; historical versions are in `docs/release-notes/`):

```markdown
# Release v1.0.0 — Platform Product Release

Released: 2026-06-01

## What's New

### Breaking Changes
None.

### New Capabilities
- **Unified Platform API Gateway** (ADR 0092): All platform services accessible via api.lv3.org
- **Interactive Ops Portal** (ADR 0093): Browser-native platform operations
- **Public Status Page** (ADR 0109): status.lv3.org for external visibility
- **Postgres HA** (ADR 0098): Automatic failover for the database tier

### SLO Commitments
- Keycloak: 99.5% availability over 30 days
- API Gateway: 99.5% availability over 30 days
- Status Page: 99.9% availability over 30 days

### Platform Versions at Release
See versions/stack.yaml for full component version inventory.

## Upgrade from v0.x

v1.0.0 is backward compatible with v0.x deployments.
No manual migration steps are required.
```

Release notes are generated from `changelog.md` by `scripts/generate_release_notes.py`.

### Upgrade path policy

| Source version | Target version | Operator action required |
|---|---|---|
| Any 0.x | Any 0.x | No (all 0.x versions are additive) |
| Any 0.x | 1.0.0 | No (v1.0.0 is a stabilisation release, not a breaking change) |
| 1.x | 2.0.0 | Yes — see upgrade guide for 2.0.0 |
| Minor version skip (1.0 → 1.5) | Supported | Minor versions are cumulative |
| Major version skip (1.0 → 3.0) | Not supported | Must go through each major version in sequence |

Upgrade guides for each major version are published in `docs/upgrade/v<major>.md` and linked from the release notes.

### Platform 1.0.0 definition

Version `1.0.0` is defined as the state where all of the following are true:
- ADRs 0001–0111 are all in status `Implemented` or `Accepted`
- All edge-published services have an active SLO with > 99% error budget remaining
- The automated backup restore verification (ADR 0099) has passed at least two consecutive weekly runs
- The ops portal (ADR 0093) is deployed and accessible at `ops.lv3.org`
- The public status page (ADR 0109) is live at `status.lv3.org`
- The docs site (ADR 0094) is published at `docs.lv3.org`
- The disaster recovery playbook (ADR 0100) has been table-top reviewed

This defines "finished product" in machine-checkable terms.

### `lv3 release status` command

```bash
lv3 release status
# Platform 1.0.0 readiness:
#   ✅ ADRs 0001–0091: all implemented
#   ⏳ ADRs 0092–0111: 6/20 implemented (0.30 complete)
#   ✅ Backup restore verification: 2 consecutive passes
#   ⏳ Ops portal: not yet deployed
#   ⏳ Status page: not yet deployed
#   ⏳ Docs site: not yet deployed
#   ⏳ DR table-top review: not yet completed
```

## Consequences

**Positive**
- Version numbers become meaningful: `1.0.0` signals "this is a finished platform product", not just "the 93rd ADR merged"
- The 1.0.0 definition creates a clear finishing line; progress toward it is measurable
- Upgrade path policy prevents operators from skipping major versions inadvertently, protecting them from migration errors
- Structured release notes in the docs site give collaborators a concise changelog they can read without parsing git history

**Negative / Trade-offs**
- Defining breaking changes at the platform level requires judgment; reasonable people can disagree about whether an API change is "breaking" — the list of breaking change criteria above makes this explicit and overridable for edge cases
- Skipping major versions not being supported means a hypothetical upgrade from v1 to v3 requires stopping at v2; this is standard semantic versioning practice but must be communicated clearly in upgrade docs

## Alternatives Considered

- **Calendar versioning (2026.03, 2026.06, etc.)**: easier to understand chronologically; does not communicate breaking-change semantics; appropriate for rolling releases but not for a platform that has installation procedures
- **No formal version semantics; just increment**: the current state; `0.93.0` means nothing specific; `1.0.0` becomes just the next merge
- **Tags only, no RELEASE.md**: a lighter approach; loses the structured release notes that the docs site and changelog page depend on

## Related ADRs

- ADR 0008: Versioning model (this ADR extends it with semantic definitions)
- ADR 0017: ADR lifecycle (ADR status feeds into the 1.0.0 readiness check)
- ADR 0073: Environment promotion gate (releases go through the promotion gate)
- ADR 0081: Platform changelog (release notes feed into the changelog)
- ADR 0090: Unified platform CLI (`lv3 release` command)
- ADR 0094: Developer portal (release notes and upgrade guides published here)
