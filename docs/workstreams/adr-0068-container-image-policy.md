# Workstream ADR 0068: Container Image Policy And Supply Chain Integrity

- ADR: [ADR 0068](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0068-container-image-policy-and-supply-chain-integrity.md)
- Title: Digest-pinned images, scan receipts, and an upgrade workflow for supply-chain safety
- Status: merged
- Branch: `codex/adr-0068-container-image-policy`
- Worktree: `../proxmox_florin_server-container-image-policy`
- Owner: codex
- Depends On: `adr-0023-docker-runtime`, `adr-0025-docker-compose-stacks`, `adr-0044-windmill`
- Conflicts With: none
- Shared Surfaces: all Docker Compose files, `config/`, Windmill workflows, `docker-build-lv3` role

## Scope

- audit all current Compose stacks and record existing images in `config/image-catalog.json`
- pin every image to a digest in its Compose file
- run `trivy image --scanners vuln` on each pinned image and store receipts in `receipts/image-scans/`
- create Windmill workflow `upgrade-container-image` as the approved upgrade path
- add `make check-image-freshness` target
- document the policy in `docs/runbooks/container-image-policy.md`

## Non-Goals

- image signing or SBOM attestation in the first iteration
- Kubernetes or non-Docker runtimes

## Expected Repo Surfaces

- `config/image-catalog.json`
- updated Docker Compose files (all images digest-pinned)
- `receipts/image-scans/` directory with initial scan receipts
- Windmill workflow definition for image upgrade
- `docs/runbooks/container-image-policy.md`
- `Makefile` updated with `check-image-freshness`
- `docs/adr/0068-container-image-policy-and-supply-chain-integrity.md`
- `docs/workstreams/adr-0068-container-image-policy.md`
- `workstreams.yaml`

## Expected Live Surfaces

- all managed containers running from digest-pinned images
- Windmill workflow available for future upgrades

## Verification

- `python3 -c "import json; json.load(open('config/image-catalog.json'))"` exits 0
- `make check-image-freshness` runs without error
- `python3 scripts/container_image_policy.py --validate` exits 0

## Merge Criteria

- no `:latest` or unpinned tags remain in any managed Compose file
- every image has a scan receipt and any remaining critical CVEs have an explicit time-bounded exception record in the catalog
- the upgrade workflow is documented and a test run receipt exists

## Notes For The Next Assistant

- `docker compose pull --quiet && docker inspect <image>` is the easiest way to get the current digest before pinning
- use `trivy image --scanners vuln --severity CRITICAL,HIGH` to stay focused on CVE gating instead of secret-scanning noise
