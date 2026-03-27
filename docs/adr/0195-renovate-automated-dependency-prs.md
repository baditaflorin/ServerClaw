# ADR 0195: Renovate Automated Dependency PRs

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.12
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

Container image digests, Python requirements, Ansible collection versions, and workflow action references drift silently. The existing security patch loop is reactive, but the platform has no proactive PR-based dependency hygiene for the internal Gitea repository path. Operators currently discover stale dependency pins only after a separate check or incident, and the private Gitea Actions runner on `docker-build-lv3` is underused for repository maintenance work.

## Decision

Run Renovate as a self-hosted Gitea Actions workflow on `docker-build-lv3`, scheduled daily and also runnable on demand for workflow or config validation changes. Keep the canonical Renovate configuration in `config/renovate.json`, validate it in the standard repository data-model gate, and use it to scan:

- `.gitea/workflows/*.yml` action versions
- `collections/requirements.yml`
- the managed `requirements.txt` files already present in the repository
- `config/image-catalog.json` through a regex manager that keeps `tag`, `digest`, and `ref` aligned

Patch, digest, and pin updates are grouped and auto-merged when the Gitea checks pass. Minor and major updates remain PR-only for human review. The Gitea converge path now also provisions a dedicated `renovate-bot` token, stores it in the repo-managed controller-local secret manifest, and writes it into the internal Gitea repository as the `RENOVATE_TOKEN` Actions secret.

Because the managed internal Gitea repository was still only bootstrapped and not yet carrying the full repository contents, the implementation also adds an explicit `publish-gitea-repo` automation surface so the controller can seed or refresh the internal Gitea default branch from the current checkout before relying on scheduled Actions workflows.

## Consequences

### Positive

- dependency maintenance becomes proactive and arrives as private Gitea PRs instead of ad hoc discovery
- the existing internal runner on `docker-build-lv3` now executes a concrete daily repository-maintenance workflow
- image-catalog digest drift can be reviewed in PR form without hand-editing the catalog
- the live platform now has an explicit, repeatable publish step for the internal Gitea repository path

### Trade-offs

- the initial live apply depends on the internal Gitea repository carrying a current checkout; the publish step is now explicit rather than implicit
- the first implementation uses the current Gitea runner plus existing validation signals, so Harbor- or Plane-specific enrichments remain future follow-up work when ADR 0193 and ADR 0201 land on the active mainline

## Boundaries

- Renovate manages dependencies declared in repository files only
- VM packages installed outside the repository remain outside this automation boundary
- auto-merge is limited to patch, digest, and pin updates

## Related ADRs

- ADR 0143: Gitea for self-hosted git and CI
- ADR 0175: Cross-workstream interface contracts
- ADR 0193: Plane kanban task board
- ADR 0201: Harbor container registry with CVE scanning
