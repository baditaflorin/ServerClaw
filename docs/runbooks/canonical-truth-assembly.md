# Canonical Truth Assembly

This runbook documents ADR 0174: integration-only assembly of the top-level canonical truth files.

## Canonical Inputs

- `workstreams/policy.yaml`
- `workstreams/active/*.yaml`
- `workstreams/archive/**/*.yaml`
- generated compatibility assembly in `workstreams.yaml`
- `docs/workstreams/*.md`
- `receipts/live-applies/*.json`
- `docs/adr/*.md`
- `docs/runbooks/*.md`
- `inventory/host_vars/proxmox_florin.yml`

## Canonical Outputs

- `README.md`
- `VERSION`-aligned release fields in `versions/stack.yaml`
- `changelog.md`

## Workstream Metadata

Workstreams can opt into canonical-truth assembly with a `canonical_truth` block:

```yaml
canonical_truth:
  changelog_entry: implemented ADR 0174 canonical truth assembly
  release_bump: patch
  included_in_repo_version: null
  latest_receipts:
    api_gateway: 2026-03-26-adr-0163-retry-taxonomy-live-apply
```

Use the fields like this:

- `changelog_entry`: one release-note bullet for the workstream
- `release_bump`: the minimum semantic bump required when the workstream is released
- `included_in_repo_version`: `null` until the release is cut; the release manager sets it to the new repo version
- `latest_receipts`: capability-to-receipt mappings that should flow into `versions/stack.yaml.live_apply_evidence.latest_receipts` once the workstream is live

## Assemble

Regenerate canonical truth from the integrated repo state:

```bash
make assemble-canonical-truth
```

Or call the script directly:

```bash
uvx --from pyyaml python scripts/canonical_truth.py --write
```

## Verify

Check whether canonical truth is already current:

```bash
make check-canonical-truth
```

This check is part of `scripts/validate_repo.sh generated-docs` and is also executed before the live-apply make targets continue.

## Release Flow

1. Merge the workstream to the integration branch or `main`.
2. Ensure the workstream entry carries the correct `canonical_truth` metadata.
3. Run the release manager.
4. Update the ADR metadata with the released repo version.

The release manager now:

- assembles `changelog.md` before reading `## Unreleased`
- writes the new `VERSION`
- keeps `versions/stack.yaml.repo_version` and `release_tracks.repo_versioning.current` in sync
- marks pending workstreams as released in the shard source, moves completed shards from `workstreams/active/` into `workstreams/archive/<year>/`, and regenerates `workstreams.yaml`
- reruns canonical-truth assembly so `README.md` and `changelog.md` match the cut release

## Live Apply

The live-apply make targets now call `make check-canonical-truth` first. If the top-level canonical files are stale, the apply exits before any mutation begins.
