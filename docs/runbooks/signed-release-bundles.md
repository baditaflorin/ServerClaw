# Signed Release Bundles

This runbook covers ADR 0233 signed control-plane release bundles produced inside the private Gitea boundary and verified with Cosign.

## Purpose

Use this path when a server-resident workflow needs an immutable, signed control input instead of depending on a mutable workstation checkout.

The current ADR 0233 implementation:

- assembles a repo-managed control bundle with `scripts/release_bundle.py`
- signs the bundle with a Cosign key pair mirrored only under `.local/gitea/`
- publishes the bundle, Sigstore bundle, and SHA256 sidecar into a private Gitea Release
- re-downloads and verifies the same release assets through the private Gitea API

## Bootstrap Signing Material

Generate the signing material once from a clean worktree:

```bash
python3 scripts/release_bundle.py init-signing
```

This writes:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/release-bundle-cosign.key`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/release-bundle-cosign.password.txt`
- `keys/gitea-release-bundle-cosign.pub` in the current checkout

Treat the `.local/gitea/` files as controller-only secrets. Commit the matching public key update in the same branch when the signing material is rotated.

## Seed The Private Gitea Repo Secrets

Re-run the managed converge after the local signing files exist:

```bash
make converge-gitea
```

The `gitea_runtime` bootstrap seeds these private repo Actions secrets when they are missing:

- `RELEASE_BUNDLE_COSIGN_PRIVATE_KEY`
- `RELEASE_BUNDLE_COSIGN_PASSWORD`
- `RELEASE_BUNDLE_REPO_TOKEN`

`RELEASE_BUNDLE_REPO_TOKEN` is seeded from the managed Gitea admin token mirror so the server-resident publish and verify jobs can download private release assets through the authenticated release endpoints. The ephemeral workflow `github.token` is not sufficient for that private asset replay path.

## Build And Publish A Bundle Locally

Use this path when you need an operator-driven dry run outside the Gitea workflow:

```bash
python3 scripts/release_bundle.py publish \
  --gitea-url http://100.64.0.1:3009 \
  --repository ops/proxmox-host_server \
  --ref-name main \
  --ref-type branch \
  --commit "$(git rev-parse HEAD)" \
  --output-dir /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/release-bundles \
  --public-key-path keys/gitea-release-bundle-cosign.pub \
  --private-key-path /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/release-bundle-cosign.key \
  --password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/release-bundle-cosign.password.txt \
  --api-token "$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/admin-token.txt)"
```

## Dispatch The Server-Resident Workflow

The repo-managed workflow lives at `.gitea/workflows/release-bundle.yml` and consumes the seeded `RELEASE_BUNDLE_REPO_TOKEN` secret for both publish and verify steps.

Dispatch it against a branch ref that already exists in the private Gitea repo:

```bash
curl -sS \
  -X POST \
  -H "Authorization: token $(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/admin-token.txt)" \
  -H 'Content-Type: application/json' \
  -d '{"ref":"codex/ws-0233-live-apply"}' \
  http://100.64.0.1:3009/api/v1/repos/ops/proxmox-host_server/actions/workflows/release-bundle.yml/dispatches
```

Inspect recent runs:

```bash
curl -sS \
  -H "Authorization: token $(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/admin-token.txt)" \
  http://100.64.0.1:3009/api/v1/repos/ops/proxmox-host_server/actions/runs
```

## Verify A Published Bundle

Download the private release assets and verify the published Sigstore bundle with the committed public key:

```bash
python3 scripts/release_bundle.py verify-release \
  --gitea-url http://100.64.0.1:3009 \
  --repository ops/proxmox-host_server \
  --release-tag bundle-branch-main-<commit12> \
  --output-dir /tmp/lv3-release-bundle-verify \
  --public-key-path keys/gitea-release-bundle-cosign.pub \
  --api-token "$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/gitea/admin-token.txt)"
```

The verifier checks:

- the release exists in the private Gitea repo
- the expected `.tar.gz`, `.sigstore.json`, and `.sha256` assets are present
- `cosign verify-blob` succeeds with the committed public key and the published Sigstore bundle
- the detached SHA256 sidecar matches the downloaded bundle
- the embedded `release-bundle-manifest.json` can be read from the archive

## Notes

- Non-`main` branch bundles are intentionally published as prereleases.
- The current live Gitea repo is not automatically synced from `origin/main`, so branch-safe verification should push the workstream branch into Gitea instead of assuming the live Gitea `main` already contains the latest GitHub state.
- When Cosign also emits a detached `.sig`, the workflow uploads it as an optional compatibility asset, but verification relies on the Sigstore bundle.
- The `publish` command now prunes older `bundle-*` releases before uploading new assets. Use `--retain-count` to control how many bundle releases remain in Gitea when attachment storage is tight.
- Rotate the signing key pair deliberately. A new private key requires committing the matching public key update and re-running `make converge-gitea`.
