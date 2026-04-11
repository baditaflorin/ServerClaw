# ADR 0297: Renovate Bot As The Automated Stack Version Upgrade Proposer

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.112
- Implemented In Platform Version: 0.130.74
- Implemented On: 2026-03-31
- Date: 2026-03-29

## Context

`versions/stack.yaml` is the canonical record of every service version deployed on
the platform. It is currently maintained by hand: an operator reads a release
announcement, decides a version bump is safe, edits the file, and opens a pull
request. This process has two recurring failure modes:

- **Lag**: services fall behind their upstream release streams for weeks or months
  because no operator noticed a new release.
- **Silent divergence**: the image digest pinned in an Ansible role drifts from
  the version string in `stack.yaml` because the two files are updated in separate
  commits with no cross-check.

The platform already tracks every service version in machine-readable form across
`versions/stack.yaml`, `config/image-catalog.json`, and individual Ansible role
defaults. Renovate Bot (`renovatebot/renovate`) can consume those files directly
and open governed pull requests whenever an upstream Docker image, GitHub release,
or Gitea release publishes a new version.

Renovate is MIT-licensed, written in Node.js, and ships as a single Docker image
(`ghcr.io/renovatebot/renovate`). It has been in production use since 2017, is
used by millions of repositories, and exposes a REST webhook callback API that
integrates with Gitea natively. It supports custom managers that parse
non-standard version files, meaning `versions/stack.yaml` and Ansible role
defaults can be taught to Renovate through a `renovate.json` configuration file
without modifying the source files.

## Decision

We will deploy **Renovate Bot** as a scheduled Gitea Actions job on
`docker-build` that proposes pull requests for stack version upgrades.

### Deployment rules

- Renovate runs as a Gitea Actions scheduled workflow (cron) on
  `docker-build`, not as a long-lived daemon; this avoids a new managed
  service and keeps it within the existing CI execution budget (ADR 0119)
- the Renovate Docker image is pulled through Harbor (ADR 0068) and pinned to a
  specific SHA digest
- the Gitea API token used by Renovate is a scoped, short-lived credential stored
  in OpenBao and injected at runtime (ADR 0077); it has write access only to the
  designated PR-creation scope on the platform repository
- Renovate's `renovate.json` configuration file lives at the repository root and
  is the single source of truth for manager configuration, versioning schemes, PR
  labels, automerge eligibility, and rate limits

### Version sources managed by Renovate

- Docker image tags and digests in `config/image-catalog.json` and Ansible role
  defaults (`roles/*/defaults/main.yml`)
- `versions/stack.yaml` service version strings, parsed via a custom Renovate
  regex manager keyed on the `version:` fields
- GitHub and Gitea release tags for toolchain binaries (e.g. OpenTofu, step-ca,
  Cosign)

### PR governance rules

- every Renovate PR targets the main branch and must pass the full validation gate
  (ADR 0087) before merge eligibility is granted
- Renovate is not permitted to automerge; all PRs require operator review
- PRs that change a pinned image digest must include the new digest value in the
  PR body alongside the version string, so the reviewer can verify both
- Renovate groups patch-level bumps for the same service into a single PR to
  reduce review noise
- major version bumps always produce a standalone PR with an explicit breaking
  change label
- a Renovate dashboard issue is created in the platform repository, giving
  operators a single consolidated view of all pending and deferred upgrades

### Digest cross-check rule

- after Renovate opens a PR that changes a version string in `stack.yaml`, the
  existing validation-gate fitness function (ADR 0213) asserts that any
  corresponding digest entry in `image-catalog.json` was updated in the same
  commit; a mismatch is a blocking gate failure

## Consequences

**Positive**

- version lag is reduced from weeks or months to hours; Renovate detects new
  releases on the day they are published
- the operator's upgrade work shifts from discovery to review, which is a safer
  and higher-value activity
- the digest cross-check rule closes the silent divergence failure mode that
  manual updates produce
- Renovate's PR history creates a machine-readable audit trail of every version
  bump considered and either merged or deferred

**Negative / Trade-offs**

- a steady stream of Renovate PRs requires operator triage capacity; without
  active review the PR queue grows and defeats the purpose
- the custom regex manager for `versions/stack.yaml` must be kept in sync with
  any schema changes to that file
- Renovate's own Docker image is a dependency that must be kept updated; a
  vulnerable Renovate image would have Gitea write access

## Boundaries

- Renovate proposes version changes; it does not deploy them. Deployment remains
  the responsibility of the existing Ansible and Windmill pipeline.
- Renovate does not manage OS package versions or Proxmox host-level packages;
  those remain governed by the Ansible role update cadence.
- Renovate does not replace the existing image digest verification in the
  check-runner (ADR 0083); it complements it by surfacing upstream changes before
  they are deployed.

## Related ADRs

- ADR 0068: Container image policy and supply chain integrity
- ADR 0077: Compose runtime secrets injection
- ADR 0083: Docker-based check runner
- ADR 0087: Repository validation gate
- ADR 0110: Platform versioning and upgrade path
- ADR 0119: Budgeted workflow scheduler
- ADR 0213: Architecture fitness functions in the validation gate
- ADR 0233: Signed release bundles via Gitea releases and Cosign

## References

- <https://github.com/renovatebot/renovate>
