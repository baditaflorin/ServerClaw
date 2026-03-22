# Workstream ADR 0047: Short-Lived Credentials And Internal mTLS

- ADR: [ADR 0047](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0047-short-lived-credentials-and-internal-mtls.md)
- Title: Credential lifetime and mTLS policy
- Status: merged
- Branch: `codex/adr-0047-short-lived-creds`
- Worktree: `../proxmox_florin_server-short-lived-creds`
- Owner: codex
- Depends On: `adr-0042-step-ca`, `adr-0043-openbao`, `adr-0046-identity-classes`
- Conflicts With: none
- Shared Surfaces: SSH certificates, API tokens, internal HTTPS, service auth

## Scope

- define default credential lifetimes and issuer boundaries
- prefer short-lived machine and human credentials over static secrets
- define when internal mTLS should be required

## Non-Goals

- full implementation in this planning workstream
- preserving long-lived static secrets as the default

## Expected Repo Surfaces

- `docs/adr/0047-short-lived-credentials-and-internal-mtls.md`
- `docs/workstreams/adr-0047-short-lived-creds.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- short-lived SSH and API credentials for new control-plane components
- mTLS on internal APIs that cross trust boundaries

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0047-short-lived-credentials-and-internal-mtls.md`

## Merge Criteria

- issuer boundaries and credential lifetime intent are explicit
- the ADR clearly prefers short-lived credentials by default

## Notes For The Next Assistant

- do not implement this before the identity taxonomy and issuer choices are settled
