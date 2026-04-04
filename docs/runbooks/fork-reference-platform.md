# Fork The Reference Platform

## Purpose

This runbook describes the supported fork-first path for turning the public
reference repository into a new environment without inheriting LV3-specific
hostnames, addresses, or controller-local file paths.

## Starting Point

Use these public-safe example surfaces together:

- [inventory/examples/reference-platform/README.md](../../inventory/examples/reference-platform/README.md)
- [config/examples/reference-provider-profile.yaml](../../config/examples/reference-provider-profile.yaml)
- [config/examples/reference-publication-profile.json](../../config/examples/reference-publication-profile.json)
- [config/examples/reference-controller-local-secrets.json](../../config/examples/reference-controller-local-secrets.json)

## Procedure

1. Copy the reference inventory files into your fork-local inventory surfaces and replace every sample hostname, address, and bridge value.
2. Copy the provider and publication example profiles into your own tracked config files or local planning notes, then replace the example domains, public IPs, and provider identifiers.
3. Materialize the controller-local overlay under `.local/` using the sample secret manifest as the contract for file-backed bootstrap material.
4. Keep live secret values out of git. Only the manifest shape and the `.local/...` file locations are committed.
5. Run `make preflight WORKFLOW=<workflow-id>` for the workflow you plan to execute first.
6. Run `make validate` before any live mutation.

## Replace Before Live Apply

Do not live-apply the sample values. Replace at least:

- `example.com` and `example.internal` domains
- `203.0.113.0/24` and `100.64.0.0/10` example addresses
- sample host ids such as `proxmox_reference`
- placeholder controller-local secret filenames if your bootstrap contract differs

## Notes

- The integrated LV3 deployment remains the canonical truth for the current platform, but it is no longer the only onboarding path.
- The public example surfaces are intentionally smaller than the live deployment. Add services incrementally after the first validation and dry-run cycle succeeds.
