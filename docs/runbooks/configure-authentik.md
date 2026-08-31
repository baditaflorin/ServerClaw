# Configure Authentik

## Purpose and safety boundary

This runbook converges the Authentik identity broker selected by
[ADR 0491](../adr/0491-authentik-for-operator-and-agent-sso.md). Authentik is
the authoritative platform identity provider at `https://id.example.com`.

The workflow manages:

- a self-contained PostgreSQL, Redis, Authentik server, and worker stack on
  `runtime-control`
- OpenBao-agent rendering of the Authentik runtime environment
- public DNS and shared-edge publication
- the repo-declared OAuth providers and applications in
  `config/authentik/oauth-clients.yaml`

It does not rotate an adopted Authentik secret or authorize an unreviewed
identity-client change. It reconciles only the manifest clients explicitly
selected by the role.

## Secret modes

`authentik_secret_bootstrap_mode` has three explicit modes:

- `preserve` is the default. All four canonical, root-owned `0600` secret
  files must already exist and remain byte-for-byte stable.
- `adopt_legacy` is a one-time migration for an existing deployment whose
  secrets are in `/opt/authentik/.env`. The role allowlists only the signing
  key, PostgreSQL password, bootstrap API token, and bootstrap password. It
  verifies both PostgreSQL password aliases match, writes missing canonical
  files with exclusive creation, and refuses any mismatch.
- `generate` is only for a genuinely new, empty deployment. The role refuses
  it when the legacy environment exists. Never use it with an existing
  Authentik database.

Partial canonical state is an error. Restore the complete verified set before
retrying; never fill a missing value by hand.

## Resolve controller-local paths

Linked worktrees intentionally have no `.local/` directory. Select the intended
deployment explicitly; the Authentik entrypoint refuses shared-overlay defaults.
Resolve the selected files and shared secret root once:

```bash
export PLATFORM_IDENTITY_OVERLAY=/absolute/path/to/identity.yml
export PLATFORM_TOPOLOGY_OVERLAY=/absolute/path/to/topology.yml
LOCAL_ROOT="$(scripts/resolve_local_overlay_root.sh)"
IDENTITY_FILE="${PLATFORM_IDENTITY_OVERLAY:?select the intended deployment identity}"
TOPOLOGY_FILE="${PLATFORM_TOPOLOGY_OVERLAY:?select the intended deployment topology}"
case "${IDENTITY_FILE}" in
  /*) ;;
  .local/*) IDENTITY_FILE="${LOCAL_ROOT}/${IDENTITY_FILE#.local/}" ;;
  *) IDENTITY_FILE="${LOCAL_ROOT}/${IDENTITY_FILE}" ;;
esac
case "${TOPOLOGY_FILE}" in
  /*) ;;
  .local/*) TOPOLOGY_FILE="${LOCAL_ROOT}/${TOPOLOGY_FILE#.local/}" ;;
  *) TOPOLOGY_FILE="${LOCAL_ROOT}/${TOPOLOGY_FILE}" ;;
esac
export PLATFORM_IDENTITY_OVERLAY="${IDENTITY_FILE}"
export PLATFORM_TOPOLOGY_OVERLAY="${TOPOLOGY_FILE}"
PLATFORM_DOMAIN="$(uv run --no-project --with pyyaml python -c \
  'import pathlib,sys,yaml; print(yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["platform_domain"])' \
  "${IDENTITY_FILE}")"
```

Leave `PLATFORM_INVENTORY_OVERLAY` unset to use the committed private
inventory. Set it only when an intentional alternate inventory has been
reviewed alongside both explicit selectors.

Do not print, source, or interpolate secret-file contents into command-line
arguments. Reconciliation accepts a token file and suppresses secret-bearing
responses.

Before any OpenBao, DNS, or service mutation, the Make entrypoint regenerates
the expected platform facts in memory from both selected files and requires an
exact match with tracked `platform_generation` and target-host facts. A mismatch
means the repository was generated for another deployment; stop and select the
correct files or regenerate reviewed repository state. Never proceed using the
unselected shared `.local/identity.yml` default.

## Preconditions

Before the first adoption apply:

1. Work from the reviewed commit and hold the governed `vm:192:apply` plus
   affected configuration-file locks. Start a workstream apply receipt.
2. Record the running compose definition, immutable image IDs, container IDs,
   and current Authentik provider/application object IDs without recording
   credentials.
3. Obtain a fresh, verified backup for the `pbs_vm_192` coverage object before
   any secret or compose mutation. The backup must include
   `/opt/authentik/data/postgres`. Record the backup identifier and restore
   verification in the apply receipt.
4. Confirm `/opt/authentik/.env` is a non-empty, root-owned, non-symlink regular
   file with mode `0600`. Inspect metadata only; do not display its contents.
5. Verify the current Authentik ready endpoint. Stop if it is unhealthy:

   ```bash
   curl --fail --silent --show-error \
     "https://id.${PLATFORM_DOMAIN}/-/health/ready/" >/dev/null
   ```

The role-created `/opt/authentik/.env.pre-openbao-adoption` protects the legacy
secret source, but it is not a database backup and does not replace the verified
`pbs_vm_192` recovery point.

## Guarded converge

### 1. Validate repository contracts

```bash
make syntax-check-openbao
make syntax-check-authentik
python3 scripts/workflow_catalog.py --validate
python3 scripts/command_catalog.py --validate
python3 scripts/service_definition_catalog.py --check
python3 scripts/validate_integrations.py --check-dead
```

### 2. Bootstrap and verify the narrow provisioner contract

Run the separately approved, bounded break-glass bootstrap before Authentik:

```bash
make preflight-authentik-deployment-selection env=production
make bootstrap-openbao-runtime-secret-provisioner env=production
PROVISIONER_FILE="${LOCAL_ROOT}/openbao/runtime-secret-provisioner-approle.json"
PROVISIONER_RECEIPT="${LOCAL_ROOT}/openbao/runtime-secret-provisioner-bootstrap-receipt.json"
python3 - "${PROVISIONER_FILE}" "${PROVISIONER_RECEIPT}" <<'PY'
import os
import stat
import sys

for path in sys.argv[1:]:
    metadata = os.lstat(path)
    assert stat.S_ISREG(metadata.st_mode)
    assert not stat.S_ISLNK(metadata.st_mode)
    assert metadata.st_size > 0
    assert stat.S_IMODE(metadata.st_mode) == 0o600
print("runtime-secret-provisioner artifact and receipt metadata verified")
PY
```

The bootstrap may create or verify only the registered runtime service policies,
AppRoles, narrow provisioner artifact, and non-secret capability-verification
receipt. It must not restart, recreate, initialize, or unseal OpenBao. Do not
run `converge-openbao` to satisfy this prerequisite: that workflow is unsafe
when bootstrap root or unseal state is stale. The init payload, root token, and
controller automation AppRole are not accepted as fallback provisioners.

The bootstrap validates the cataloged mTLS controller URL as topology
provenance, but controller-local automation does not send credentials to that
listener. It derives the public SSH jump host from the explicit identity,
derives the OpenBao owner guest and automation port from the explicit topology,
and opens a strict-host-key-checked loopback forward to guest
`127.0.0.1:8201`. The governed mode-`0600` bootstrap SSH key is required; do
not work around a tunnel failure with an arbitrary API URL or a less-privileged
host-key policy.

The metadata check does not read either file. Authentik preflight requires both
files; the receipt is emitted only after provisioner login and exact allow/deny
capability checks. If either artifact is absent, OpenBao is sealed, or bootstrap
verification fails, leave Authentik blocked and follow the governed OpenBao
recovery procedure.

### 3. Perform the one-time legacy adoption

Only after the backup and baseline checks pass:

```bash
HETZNER_DNS_API_TOKEN=... \
EXTRA_ARGS='-e authentik_secret_bootstrap_mode=adopt_legacy' \
make converge-authentik env=production
```

The target requires the separately bootstrapped provisioner artifact and
verification receipt in Authentik preflight, preserves the legacy environment at
`/opt/authentik/.env.pre-openbao-adoption` with `force: false`, adopts the four
allowlisted values, provisions the registered OpenBao runtime contract, and
requires a fresh root-owned `0600` agent render before application services
start.

### 4. Return to preserve mode

Every subsequent apply uses the default `preserve` mode:

```bash
HETZNER_DNS_API_TOKEN=... make converge-authentik env=production
```

Do not leave `adopt_legacy` or `generate` in a persistent inventory override.

### 5. Prove OAuth reconciliation is idempotent

The role applies the selected GlitchTip and Outline manifest clients and then performs a separate,
read-only `--check --expect-no-change` pass. It adopts existing
provider/application objects and the existing client secret; it must not
replace object identities or rotate client material.

The same no-change assertion can be repeated from any linked worktree without
putting a token value in argv:

```bash
uv run --no-project --with pyyaml python scripts/reconcile_authentik_oauth.py \
  --base-url "https://id.${PLATFORM_DOMAIN}" \
  --platform-domain "${PLATFORM_DOMAIN}" \
  --token-file "${LOCAL_ROOT}/authentik/bootstrap-token.txt" \
  --client glitchtip \
  --client outline \
  --check \
  --expect-no-change
```

## Verification and evidence

After the apply, verify the identity provider and record only non-secret
results:

```bash
curl --fail --silent --show-error \
  "https://id.${PLATFORM_DOMAIN}/-/health/ready/" >/dev/null
```

The receipt must include the source commit, lock IDs, backup and restore-check
identifier, old and new immutable image IDs, preserved legacy-environment path,
stable provider/application IDs, successful second no-change reconciliation,
and fresh OpenBao render and Authentik-health evidence. Never include tokens,
passwords, client secrets, rendered environments, or authorization URLs
containing state.

### Browser sign-in and edge CSP

Authentik supplies its per-request browser configuration through an inline
`window.authentik` bootstrap script. The shared edge must therefore keep the
host-specific `id.{{ platform_domain }}` CSP override with
`script-src 'self' 'unsafe-inline'`; the global default is intentionally
stricter for services that do not need this compatibility exception. If that
override is removed, Authentik's browser flow can remain on **Loading** after a
successful password check because the post-login redirect has no bootstrap
configuration.

After an Authentik or edge change, complete one clean browser OIDC sign-in to a
declared relying party such as Outline. Verify that password entry returns to
the protected application without a manual URL change, then record only the
success result in the apply receipt.

## Rollback

Rollback is ordered and preserves evidence:

1. Stop the Authentik application containers if the runtime is unhealthy.
2. Preserve failed-run logs and metadata without secret values.
3. Restore the last known-good compose definition and immutable Authentik
   images. If returning to the legacy compose contract, restore
   `/opt/authentik/.env` from the protected
   `/opt/authentik/.env.pre-openbao-adoption`, retaining root ownership and
   mode `0600`.
4. Reuse the existing PostgreSQL bind mount when it is healthy. If it is not,
   restore the verified pre-apply `pbs_vm_192` recovery point before starting
   Authentik; never generate replacement secrets over the restored database.
5. Verify Authentik readiness again. For a client-specific recovery, follow
   that service's runbook and restore only its reviewed Authentik configuration.
   The retired provider is an archive-only emergency recovery path and must not
   be restarted as part of an ordinary service rollback.
6. Mark the apply receipt failed or rolled back with the recovery evidence.

Do not delete the adopted canonical files, OpenBao payload, provisioner
artifact, or provider objects during rollback. They are required to explain the
failed state and make the next governed attempt deterministic.
