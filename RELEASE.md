# Release 0.104.0

- Date: 2026-03-23

## Summary
- implemented ADR 0110 in repository automation with machine-readable version semantics, breaking-change criteria, and upgrade policy stored in `config/version-semantics.json`
- added `scripts/release_manager.py` and `scripts/generate_release_notes.py`, wired `lv3 release` into the platform CLI, and documented the release workflow in `docs/runbooks/platform-release-management.md`
- extended the generated ops portal with ADR 0110 release-readiness reporting and added repository validation coverage for the new release-policy schema surfaces
- updated ADR 0110, its workstream, and the release process documentation to mark the repository implementation complete in `0.104.0`

## Platform Impact
- no live platform version bump; this release adds repository-side release semantics, notes generation, upgrade guidance, and readiness reporting only

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
