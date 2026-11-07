# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- Add guarded, no-restart Prometheus scraping for the 0own Proxmox host.
- Restore the remote validation gateway route to the declared build VM and cap pre-push validation concurrency.
- Enable least-privilege Gitea Authentik login and verify a non-admin browser session.
- Fix the Fleet build broker PKI renewal, which has failed every hour since 2026-10-05: verify the step-ca server leaf with its intermediate (the root alone cannot build the chain) and issue client leaves from a clientAuth-only template instead of the `--key-usage` flags that step 0.30 removed. Add regression tests that use a root, intermediate and leaf like step-ca does.
- Clear stale `failed` state on socket-activated Tailscale proxy services after the role runs, and mask `openipmi` in the VM base template.
- Install `logrotate` with the public edge nginx packages: nginx-lv3 had no logrotate at all, so `access.log` grew to 5.2 GB without ever rotating (first rotation done live on 2026-10-13).
- Remove the unused GitHub Actions workflow and point validation metadata at Woodpecker while retaining the self-hosted Gitea validator.
- Allow the Builder metrics peer to scrape docker-build node-exporter over the private tailnet without disrupting Docker-managed firewall rules.
- Allow the pve01, 0infer and 0mcp CI agents to reach only the shared Go build cache port on the 0own build worker.
- Remove the tailnet grant that let the pve01, 0infer and 0mcp CI agents reach the retired Go build cache port on the 0own build worker.
- Restore governed Plane API access through a loopback-only SSH forward and document the procedure.
- Resolve selected DNS catalog placeholders during guarded deployment preflight without changing the generic catalog or live DNS.
- Keep the sanitized ServerClaw host template consistent with active authenticated edge routes.
- Keep sanitized ServerClaw snapshots compatible with validation without publishing deployment-specific firewall exceptions.
- Allow an explicitly configured operator email to access Plausible through a dedicated Authentik OAuth client and proxy.
- Cap Plausible ClickHouse diagnostic system logs at one day without changing analytics event retention.

## Latest Release

- [0.179.59 release notes](docs/release-notes/0.179.59.md)

## Previous Releases

- [0.179.58 release notes](docs/release-notes/0.179.58.md)
- [0.179.57 release notes](docs/release-notes/0.179.57.md)
- [0.179.56 release notes](docs/release-notes/0.179.56.md)
- [0.179.55 release notes](docs/release-notes/0.179.55.md)
- [0.179.54 release notes](docs/release-notes/0.179.54.md)
- [0.179.53 release notes](docs/release-notes/0.179.53.md)
- [0.179.51 release notes](docs/release-notes/0.179.51.md)
- [0.179.50 release notes](docs/release-notes/0.179.50.md)
- [0.179.49 release notes](docs/release-notes/0.179.49.md)
- [0.179.48 release notes](docs/release-notes/0.179.48.md)
- [0.179.47 release notes](docs/release-notes/0.179.47.md)
- [0.179.46 release notes](docs/release-notes/0.179.46.md)
- [0.179.31 release notes](docs/release-notes/0.179.31.md)
- [0.179.30 release notes](docs/release-notes/0.179.30.md)
- [0.179.29 release notes](docs/release-notes/0.179.29.md)
- [0.179.27 release notes](docs/release-notes/0.179.27.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (569 releases)](docs/release-notes/index/2026.md)
