# Workstream ADR 0049: Private-First API Publication Model

- ADR: [ADR 0049](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0049-private-first-api-publication-model.md)
- Title: Publication tiers for internal, operator-only, and public APIs
- Status: merged
- Branch: `codex/adr-0049-private-first-api-publication-model`
- Worktree: `../proxmox-host_server-adr-0049`
- Owner: codex
- Depends On: `adr-0045-communication-lanes`, `adr-0047-short-lived-creds`
- Conflicts With: none
- Shared Surfaces: NGINX edge, private API listeners, admin surfaces

## Scope

- define publication tiers for APIs
- prevent accidental exposure of internal admin surfaces
- align API exposure with the existing edge and private-network model

## Non-Goals

- publishing a new public application API
- treating every HTTPS endpoint as safe for the public edge

## Expected Repo Surfaces

- `config/api-publication.json`
- `scripts/api_publication.py`
- `docs/adr/0049-private-first-api-publication-model.md`
- `docs/workstreams/adr-0049-private-api-publication.md`
- `docs/runbooks/private-first-api-publication.md`
- `docs/runbooks/control-plane-communication-lanes.md`
- `config/control-plane-lanes.json`
- `scripts/generate_status_docs.py`
- `scripts/validate_repository_data_models.py`
- `Makefile`
- `workstreams.yaml`

## Expected Live Surfaces

- no direct live apply in this workstream
- explicit repo-enforced exposure classes for Proxmox, mail, secret, workflow, and webhook HTTP surfaces

## Verification

- `uvx --from pyyaml python /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/api_publication.py --validate`
- `uvx --from pyyaml python /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/control_plane_lanes.py --validate`
- `make validate`

## Merge Criteria

- the repo exposes a canonical publication-tier catalog with the default `internal-only` rule
- every governed API or webhook surface in the lane catalog is classified in that catalog
- README generation and repository validation both fail if the publication model drifts

## Notes For The Next Assistant

- keep Proxmox, OpenBao, and `step-ca` out of the public edge unless a future ADR says otherwise
- treat public-edge publication as an explicit change to both the lane catalog and the publication catalog, not just an NGINX config change
