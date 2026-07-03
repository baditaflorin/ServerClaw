# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- Add `claude-ops` dedicated AI-automation admin identity: passwordless sudo + key-only SSH on the Proxmox host and all 18 lv3 guest VMs, `claude-ops@pam` with PVEAdmin, and a privilege-separated Proxmox API token (`claude-ops-automation@pve`) — independently auditable and revocable from the shared `ops` account
- Complete the 0mpc.com → 0mcp.com operator-apex migration: regenerate platform.yml and discovery artifacts against the renamed domain, update the sanitization BLOCKED list, and refresh the subdomain exposure registry
- Add the `lv3.platform.uptime_kuma_provision` role (monitors + public status page) with a `provision-uptime-kuma` Make target and playbook wiring
- Fix the bare-root `https://status.<domain>/` 404 by deriving the edge `root_proxy_path` status slug from `platform_domain` instead of a stale literal
- Deploy Woodpecker CI (ci.0mcp.com): fix OpenBao remote address for docker-runtime, add port 3003 Proxmox firewall rule for docker-runtime → runtime-control, bootstrap Gitea OAuth and seed repository

## Latest Release

- [0.179.49 release notes](docs/release-notes/0.179.49.md)

## Previous Releases

- [0.179.48 release notes](docs/release-notes/0.179.48.md)
- [0.179.47 release notes](docs/release-notes/0.179.47.md)
- [0.179.46 release notes](docs/release-notes/0.179.46.md)
- [0.179.45 release notes](docs/release-notes/0.179.45.md)
- [0.179.44 release notes](docs/release-notes/0.179.44.md)
- [0.179.43 release notes](docs/release-notes/0.179.43.md)
- [0.179.42 release notes](docs/release-notes/0.179.42.md)
- [0.179.41 release notes](docs/release-notes/0.179.41.md)
- [0.179.40 release notes](docs/release-notes/0.179.40.md)
- [0.179.39 release notes](docs/release-notes/0.179.39.md)
- [0.179.38 release notes](docs/release-notes/0.179.38.md)
- [0.179.37 release notes](docs/release-notes/0.179.37.md)
- [0.179.31 release notes](docs/release-notes/0.179.31.md)
- [0.179.30 release notes](docs/release-notes/0.179.30.md)
- [0.179.29 release notes](docs/release-notes/0.179.29.md)
- [0.179.27 release notes](docs/release-notes/0.179.27.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (560 releases)](docs/release-notes/index/2026.md)
