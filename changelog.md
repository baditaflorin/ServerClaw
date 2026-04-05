# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- recovers the remaining degraded public services after the runtime-pool stabilization merges by re-materializing OpenBao-backed runtime env files, preventing docker.socket shutdown from restarting a live Docker daemon on runtime-control-lv3, and replaying the Harbor and Vaultwarden recovery paths safely
- implements ADR 0325 by replacing the monolithic ADR metadata catalog with shard-backed discovery manifests, adding a committed ADR reservation ledger, and validating reservation-aware query and generator workflows from exact main
- implements ADR 0327 by splitting the root agent-discovery registries into sectional source files, generating concise public-safe root entrypoints, tracking generated onboarding packs under build/onboarding, and validating the discovery artifacts plus public entrypoints through the rebased exact-main automation gates
- implements ADR 0328 by enforcing explicit line budgets for the root README, changelog, and release-note index, rolling older release and status rows into generated archive ledgers, and teaching the validation plus release automation to keep those bounded summaries current
- hardens ADR 0337 by normalizing the sharded workstream registry to repo-root-relative metadata, preserving canonical in-repo workstream doc links, hardening worktree creation and service scaffolding against out-of-repo paths, and re-verifying the portability gate from the latest realistic mainline

## Latest Release

- [0.178.7 release notes](docs/release-notes/0.178.7.md)

## Previous Releases

- [0.178.6 release notes](docs/release-notes/0.178.6.md)
- [0.178.5 release notes](docs/release-notes/0.178.5.md)
- [0.178.4 release notes](docs/release-notes/0.178.4.md)
- [0.178.3 release notes](docs/release-notes/0.178.3.md)
- [0.178.2 release notes](docs/release-notes/0.178.2.md)
- [0.178.1 release notes](docs/release-notes/0.178.1.md)
- [0.178.0 release notes](docs/release-notes/0.178.0.md)
- [0.177.153 release notes](docs/release-notes/0.177.153.md)
- [0.177.152 release notes](docs/release-notes/0.177.152.md)
- [0.177.151 release notes](docs/release-notes/0.177.151.md)
- [0.177.150 release notes](docs/release-notes/0.177.150.md)
- [0.177.149 release notes](docs/release-notes/0.177.149.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (346 releases)](docs/release-notes/index/2026.md)
