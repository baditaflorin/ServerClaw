# ADR 0068: Container Image Policy And Supply Chain Integrity

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.67.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

Docker Compose stacks on this platform currently reference images in two unsafe ways:

- some services use `:latest` or unpinned minor tags (e.g. `grafana/grafana:10`)
- no image digests are recorded, so `docker compose pull` silently replaces an image with a different build
- there is no vulnerability scan step before a new image version is deployed
- the `docker-build` VM builds internal images but has no policy on what base images it may use
- several current upstream images already report critical Trivy findings, so the policy must make unavoidable upstream risk explicit instead of pretending the gate passed

This is a supply-chain risk. A compromised upstream image, a silent tag replacement, or an unreviewed base-image upgrade can introduce vulnerabilities without triggering any alert in the current workflow.

## Decision

We will define and enforce a container image policy covering pinning, provenance, and scanning.

Policy:

1. **digest pinning** — all images in Compose stacks and Ansible roles must be pinned to a specific digest (`image@sha256:<digest>`) in addition to a human-readable tag. The tag is for readability; the digest is what actually runs.
2. **image catalog** — `config/image-catalog.json` lists every managed image with its canonical tag, current digest, date pinned, and scan status. This is the machine-readable contract.
3. **scan gate** — before a digest is added to the catalog, it must be scanned with `trivy image --scanners vuln`. The scan result is stored as a receipt in `receipts/image-scans/`. Digests with critical findings are blocked by default and may only remain in the catalog behind an explicit, time-bounded exception record owned by platform operations.
4. **upgrade workflow** — image upgrades follow a named workflow in Windmill: pull new digest → scan → update catalog → update Compose file → apply. No ad hoc `docker pull` in production.
5. **build VM policy** — `docker-build` base images must be listed in `config/image-catalog.json`; the build role rejects unlisted base images at converge time.
6. **make target** — `make check-image-freshness` compares pinned digests in the catalog against current upstream digests and reports any images that have drifted.

## Consequences

- Silent upstream image changes no longer affect the running platform; only explicit catalog updates do.
- The image upgrade path is auditable and produces a receipt at every step.
- When an upstream image still ships critical CVEs, the exception path keeps the risk visible, reviewable, and date-bounded instead of hiding it behind mutable tags.
- Maintaining digest pins requires a regular maintenance workflow; stale pins accumulate security debt.
- Critical CVEs in a pinned image block the upgrade path until a clean version is available, which may require temporary mitigations.

## Boundaries

- Image policy applies to managed Compose stacks and build VM images only; one-off test containers on `docker-build` are exempt.
- The scan gate uses `trivy` vulnerability scanning; it does not enforce image signing or SBOM attestation in the first iteration.
- Kubernetes or other runtimes are out of scope; this is a Docker-specific policy.
