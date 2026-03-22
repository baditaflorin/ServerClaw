# Workstream ADR 0078: Service Scaffold Generator

- ADR: [ADR 0078](../adr/0078-service-scaffold-generator.md)
- Title: make scaffold-service command that generates a complete new-service skeleton across all catalogs and docs
- Status: ready
- Branch: `codex/adr-0078-service-scaffold`
- Worktree: `../proxmox_florin_server-service-scaffold`
- Owner: codex
- Depends On: `adr-0062-role-composability`, `adr-0075-service-capability-catalog`, `adr-0076-subdomain-governance`, `adr-0077-compose-secrets-injection`
- Conflicts With: none
- Shared Surfaces: `scripts/`, `Makefile`, `roles/_template/`, all catalog files

## Scope

- write `scripts/scaffold_service.py` with all generation logic
- add `make scaffold-service NAME=... DESCRIPTION=... CATEGORY=... VM=... VMID=... PORT=... SUBDOMAIN=... EXPOSURE=... IMAGE=...` target
- extend `roles/_template/` with Compose template and OpenBao agent template
- add `TODO` string validation to `make validate` (errors if any catalog JSON value is the string `"TODO"`)
- document the scaffold usage in `docs/runbooks/scaffold-new-service.md`
- run the scaffold against a test service (`test-echo`) to validate all outputs are correct

## Non-Goals

- scaffold for non-Compose services (systemd-native services use `roles/_template/` directly)
- fully automated ADR writing (the ADR context and consequences are placeholders that require human input)

## Expected Repo Surfaces

- `scripts/scaffold_service.py`
- updated `roles/_template/` (Compose + OpenBao agent templates added)
- updated `Makefile` (`scaffold-service`, `pin-image` targets)
- `docs/runbooks/scaffold-new-service.md`
- updated `scripts/validate_repo.sh` (TODO value check)
- `docs/adr/0078-service-scaffold-generator.md`
- `docs/workstreams/adr-0078-service-scaffold.md`
- `workstreams.yaml`

## Expected Live Surfaces

- no live changes; this is a developer tooling workstream

## Verification

- `make scaffold-service NAME=test-echo DESCRIPTION="Echo test service" CATEGORY=infrastructure VM=docker-runtime-lv3 VMID=120 PORT=8181 SUBDOMAIN=test-echo.lv3.org EXPOSURE=private-only IMAGE=docker.io/hashicorp/http-echo:latest` completes without error
- all generated files are valid JSON and valid Ansible YAML
- `make validate` fails on the generated catalog entries (because they contain `TODO` markers) — this validates the guard is working
- after filling in TODOs, `make validate` passes

## Merge Criteria

- scaffold script generates all 12 required artifacts for a test service
- TODO guard is integrated into `make validate` and documented
- the generated Compose template includes the OpenBao Agent sidecar pattern from ADR 0077
- `docs/runbooks/scaffold-new-service.md` is accurate and covers the full post-scaffold checklist

## Notes For The Next Assistant

- the ADR number auto-increment requires reading the last number from `docs/adr/` filenames; handle this carefully if two scaffolds are run in rapid succession
- generate the role by copying `roles/_template/` rather than hardcoding role structure in the script — this keeps the scaffold in sync with the template automatically
- the `pin-image` make target (referenced in the post-scaffold checklist) can shell out to `docker pull` + `docker inspect` to get the digest — implement that as a separate small target
