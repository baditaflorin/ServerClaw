# Platform Release Management

## Purpose

This runbook defines how LV3 prepares a repository release, verifies `1.0.0` readiness, and tags a release on `main`.

## Check Readiness

Run the readiness summary before cutting a release:

```bash
uv run --with pyyaml python scripts/release_manager.py status
```

Equivalent CLI entry point:

```bash
lv3 release status
```

This reports:

- the current repository and platform versions
- any release-blocking workstreams still in `status: in_progress`
- the `1.0.0` readiness checklist defined in `config/version-semantics.json`

## Prepare A Release

1. Merge the finished workstream to `main`.
2. Add the merged release notes to `## Unreleased` in `changelog.md`.
3. Cut the release artifacts:

```bash
uv run --with pyyaml python scripts/release_manager.py --bump minor --platform-impact "no live platform version bump; this release adds repository-side release tooling and metadata only"
```

Equivalent CLI entry point:

```bash
lv3 release --bump minor --platform-impact "no live platform version bump; this release adds repository-side release tooling and metadata only"
```

This updates:

- `VERSION`
- `versions/stack.yaml` repository-version fields
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/<version>.md`
- `docs/release-notes/README.md`

Use `--dry-run` first if the release contents need review.

## Tag The Release

After committing the release files on `main`, create the annotated tag:

```bash
uv run --with pyyaml python scripts/release_manager.py tag --push
```

Equivalent CLI entry point:

```bash
lv3 release tag --push
```

If `tag.gpgSign=true` is configured in git, the tag command signs the tag. Otherwise it creates an annotated tag.

## Notes

- Repository releases do not bump `platform_version`; that happens only after a verified live apply from `main`.
- `lv3 release status` uses local receipts plus lightweight URL probes. Missing future-facing inputs, such as SLO receipts, are reported as pending rather than guessed.
