# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- ADR 0447 + ws-0447: Phase 3 LLM ergonomics + traceability —
  `currently_describes` semantic axis added to every entry in the ADR
  index (current_state / goal_state / mixed_state / historical /
  unknown), driven from `implementation_status`. New
  `scripts/generate_traceability.py` joins workstream YAMLs ×
  ADR index into a single `build/traceability.yaml`; live signal
  resolves all 22 active workstreams to ADRs and surfaces 10 with
  dangling shared_surfaces. Both wired into `validate_repo.sh` as
  advisory steps.

## Latest Release

- [0.179.9 release notes](docs/release-notes/0.179.9.md)

## Previous Releases

- [0.179.8 release notes](docs/release-notes/0.179.8.md)
- [0.179.7 release notes](docs/release-notes/0.179.7.md)
- [0.179.6 release notes](docs/release-notes/0.179.6.md)
- [0.179.5 release notes](docs/release-notes/0.179.5.md)
- [0.179.4 release notes](docs/release-notes/0.179.4.md)
- [0.179.3 release notes](docs/release-notes/0.179.3.md)
- [0.179.2 release notes](docs/release-notes/0.179.2.md)
- [0.179.1 release notes](docs/release-notes/0.179.1.md)
- [0.179.0 release notes](docs/release-notes/0.179.0.md)
- [0.178.232 release notes](docs/release-notes/0.178.232.md)
- [0.178.231 release notes](docs/release-notes/0.178.231.md)
- [0.178.230 release notes](docs/release-notes/0.178.230.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (525 releases)](docs/release-notes/index/2026.md)
