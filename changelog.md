# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- ADR 0476 + ws-0477: wire `make converge-nginx-edge` to `playbooks/fix-edge-certificate.yml`. ADR 0414's `cert_lifecycle_manager.py sync-missing --apply` referenced a target that didn't exist (`make: *** No rule to make target`); the new narrow target reconciles the shared NGINX edge SAN cert without the full `configure-edge-publication` converge. Surfaces the broader operator finding: the `prod` deployment is missing `connection.yml` and references a decommissioned nginx VM (vmid 110, 10.10.10.40 — not present on the live proxmox host `fork-pve-01`); operator action required to regenerate the deployment registry before sync-missing can reach an edge.
- ADR 0471: karakeep Coolify deploy + `coolify_tool.py` programmatic env-var injection. `deploy-repo` gains `--env KEY=VALUE` (repeatable) and `--env-file PATH` flags; bulk-upserts application env vars via Coolify API before triggering the deployment. Fixes `git_repository` double-prefix bug on redeploy. Documents Coolify runtime-recovery procedure (tmpfs secrets + API token via DB). Postmortem 2026-04-29 captures six key learnings.

## Latest Release

- [0.179.42 release notes](docs/release-notes/0.179.42.md)

## Previous Releases

- [0.179.41 release notes](docs/release-notes/0.179.41.md)
- [0.179.40 release notes](docs/release-notes/0.179.40.md)
- [0.179.39 release notes](docs/release-notes/0.179.39.md)
- [0.179.38 release notes](docs/release-notes/0.179.38.md)
- [0.179.37 release notes](docs/release-notes/0.179.37.md)
- [0.179.36 release notes](docs/release-notes/0.179.36.md)
- [0.179.35 release notes](docs/release-notes/0.179.35.md)
- [0.179.34 release notes](docs/release-notes/0.179.34.md)
- [0.179.33 release notes](docs/release-notes/0.179.33.md)
- [0.179.32 release notes](docs/release-notes/0.179.32.md)
- [0.179.28 release notes](docs/release-notes/0.179.28.md)
- [0.179.26 release notes](docs/release-notes/0.179.26.md)
- [0.179.31 release notes](docs/release-notes/0.179.31.md)
- [0.179.30 release notes](docs/release-notes/0.179.30.md)
- [0.179.29 release notes](docs/release-notes/0.179.29.md)
- [0.179.27 release notes](docs/release-notes/0.179.27.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (553 releases)](docs/release-notes/index/2026.md)
