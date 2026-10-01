# Configure OpenBao

## Purpose

This runbook converges ADR 0043 by deploying a private OpenBao service on `runtime-control`, seeding the current platform secret sets into OpenBao, enabling Transit, and wiring PostgreSQL dynamic credentials through `postgres`.

## Entry Point

Preferred workflow:

```bash
make converge-openbao
```

Equivalent syntax check:

```bash
make syntax-check-openbao
```

## Preconditions

1. The controller SSH key exists at `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`.
2. `runtime-control` and `postgres` are reachable through the Proxmox jump path.
3. The existing controller-local mail, monitoring, and Proxmox API artifacts are present so the workflow can seed them into OpenBao.

## What The Workflow Changes

1. Reuses the shared ADR 0067 guest network policy that allows `runtime-control` to reach `postgres`, while this workflow manages PostgreSQL authentication through `pg_hba.conf`.
2. Creates the `openbao_rotator` PostgreSQL role with the minimum privileges needed to issue dynamic read-only credentials.
3. Starts a Compose-managed OpenBao container under `/opt/openbao` with integrated Raft storage, a loopback-published HTTP listener on `127.0.0.1:8201`, an optional guest-IP-published private HTTP listener for bounded automation consumers such as `docker-build` and `runtime-comms`, and a managed step-ca-backed TLS listener on `:8200`.
4. Initializes and unseals OpenBao once, then mirrors the bootstrap init payload to `.local/openbao/init.json` on the controller.
5. Enables `kv`, `transit`, `database`, `userpass`, and `approle` paths.
6. Creates named human and machine identities:
   - `ops` userpass for routine administration
   - `breakglass` userpass for emergency use
   - `controller-automation` AppRole
   - `mail-platform` AppRole
   - `secret-rotation` AppRole reserved for the future Windmill-side scheduler path
7. Seeds current controller, Windmill, and mail secrets into OpenBao under scoped KV paths.
8. Configures the PostgreSQL database secrets engine and verifies that OpenBao can mint working dynamic credentials.

## Controller-Local Artifacts

The converge creates these controller-local files:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/init.json`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/ops-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/breakglass-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/postgres-rotator-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/controller-automation-approle.json`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/mail-platform-approle.json`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/secret-rotation-approle.json`

Treat the entire `.local/openbao/` subtree as recovery material and keep it out of git.

The persisted AppRole JSON artifacts now carry reusable secret IDs within their
existing `15m` TTL so concurrent controller-side automation and parallel agent
worktrees do not invalidate each other by consuming a shared single-use file.

## Verification

Basic runtime checks:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'ssh -o StrictHostKeyChecking=no ops@10.10.10.92 docker compose --file /opt/openbao/docker-compose.yml ps'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'ssh -o StrictHostKeyChecking=no ops@10.10.10.92 curl -fsS http://127.0.0.1:8201/v1/sys/health'
```

Routine operator login over an SSH port forward:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -L 8201:127.0.0.1:8201 ops@100.64.0.1 'ssh -o ExitOnForwardFailure=yes -N -L 8201:127.0.0.1:8201 ops@10.10.10.92'
curl --request POST --data "{\"password\":\"$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/ops-password.txt)\"}" http://127.0.0.1:8201/v1/auth/userpass/login/ops
```

Controller AppRole login and dynamic credential fetch:

```bash
role_id="$(jq -r '.role_id' /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/controller-automation-approle.json)"
secret_id="$(jq -r '.secret_id' /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openbao/controller-automation-approle.json)"
token="$(curl -fsS --request POST --data "{\"role_id\":\"$role_id\",\"secret_id\":\"$secret_id\"}" http://127.0.0.1:8201/v1/auth/approle/login | jq -r '.auth.client_token')"
curl -fsS --header "X-Vault-Token: $token" http://127.0.0.1:8201/v1/database/creds/postgres-readonly
```

If the AppRole login starts returning `invalid role or secret ID`, the artifact
has usually expired rather than being permanently broken. Refresh it with
`make converge-openbao` and retry.

Controller-side mTLS verification for the private OpenBao API:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSLo "$tmpdir/step.tar.gz" https://github.com/smallstep/cli/releases/download/v0.30.1/step_darwin_0.30.1_arm64.tar.gz
tar -xf "$tmpdir/step.tar.gz" -C "$tmpdir"
"$tmpdir/step_0.30.1/bin/step" ca certificate \
  --force \
  --provisioner services \
  --provisioner-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/secrets/provisioners/services-password.txt \
  --ca-url https://100.64.0.1:9443 \
  --root /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt \
  --san openbao-client.lv3.internal \
  --not-after 1h \
  openbao-client.lv3.internal "$tmpdir/client.crt" "$tmpdir/client.key"
curl --cert "$tmpdir/client.crt" \
  --key "$tmpdir/client.key" \
  --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt \
  https://100.64.0.1:8200/v1/sys/health
curl --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt \
  https://100.64.0.1:8200/v1/sys/health
```

## Notes

- The loopback HTTP API on `127.0.0.1:8201` remains the managed automation and operator path for bootstrap, verification, and recovery-safe forwarding.
- ADR 0297 also allows the same HTTP listener to be published on the runtime
  guest IP when a bounded caller such as `docker-build` or `runtime-comms`
  needs direct access.
  Keep that publication private and rely on the guest firewall to scope it to
  the declared automation source only.
- The external OpenBao API on `https://100.64.0.1:8200` is private-only, published through the Proxmox host Tailscale path, and requires a valid client certificate signed by `step-ca`.
- The current implementation seeds existing mail, monitoring, Proxmox API, Windmill, and mail-profile artifacts into OpenBao so later consumers can fetch them without reintroducing git-managed secrets.
- Dedicated rotatable secret paths and their metadata now align with `config/secret-catalog.json`, so future scheduled evaluators can inspect bounded credential age directly in OpenBao.

## Recovery Notes From The 2026-03-26 Live Apply

As of the `2026-04-03` uptime hardening, `make converge-openbao` still performs
bounded Docker bridge-chain recovery on a dedicated `runtime-control` host,
but it now fails closed before any automatic Docker daemon restart on protected
shared-runtime hosts such as legacy `docker-runtime` or
`docker-runtime`. If that guard fires, stop the replay and either
finish the runtime-pool migration or rerun only in an explicitly approved
maintenance window with `-e common_docker_daemon_restart_force=true`.

On a dedicated `runtime-control` host, the role automatically recovers the
recurring Docker publish regression by rechecking the guest `DOCKER` and
`DOCKER-FORWARD` chains, restarting Docker when they are missing, waiting for
the chain rechecks to settle after that restart, and recreating the named
`lv3-openbao` container before `docker compose up`.

The same replay also hardened the post-unseal verification path: after a restart-and-unseal cycle, the role now retries the controller AppRole PostgreSQL dynamic credential request for a short bounded window because OpenBao can briefly close loopback HTTP requests while the database backend resumes.

That recovery path now also removes an empty detached `openbao_default` network
when Docker has lost the endpoint attachment. If Docker still has not recreated
those chains after the bounded recheck window, the role logs that degraded
preflight state and still continues into `docker compose up`; the decisive guard
is whether the runtime can actually rebind `:8200`, answer on `127.0.0.1:8201`,
and pass the subsequent seal-status plus AppRole verification steps.

As of the `2026-03-30` exact-main replay, the role also treats a first-pass
`docker compose up` DNAT failure as recoverable automation drift: it restarts
Docker again, removes the half-created `lv3-openbao` container plus detached
`openbao_default` network, rechecks `DOCKER` and `DOCKER-FORWARD`, and retries
the stack start once before surfacing a hard failure.

As of the `2026-03-29` ADR 0270 replay, the shared OpenBao helpers used by
runtime secret injection and host-native systemd credential delivery also
recover a missing loopback `127.0.0.1:8201` publication automatically. When the
local health probe fails with a connection-refused style outage, the helper now
force-recreates the `openbao` service, waits for the loopback listener to
return, and only then retries the health call. This keeps later workflows such
as `make converge-authentik` from failing just because the private OpenBao API
publication drifted while the container itself still existed.

If a future rerun still leaves the guest runtime broken, the failure usually presents as `docker compose up` failing to bind `:8200` with an iptables DNAT error and `docker inspect lv3-openbao` showing an empty `NetworkSettings.Networks` object.

If the automated cleanup still cannot recover the guest runtime, repair it in this order:

1. Restart Docker on `runtime-control`.
2. Remove the broken `lv3-openbao` container.
3. Remove the detached `openbao_default` network.
4. Recreate the stack with `docker compose --file /opt/openbao/docker-compose.yml up -d`.

After the guest is healthy again, restart the host-side socket activation pair if the proxy socket reports that the service is already active:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo systemctl stop lv3-tailscale-proxy-openbao.service && sudo systemctl start lv3-tailscale-proxy-openbao.socket'
```

## Recovery Notes From The 2026-08-28 Admin Lockout

`controller-automation`'s AppRole `secret_id` went stale (last generated
`2026-04-28`, presumably an ordinary TTL expiry) and the two usual recovery
paths were both found dead when we tried to fix it:

- The root token recorded in `.local/openbao/init.json` returns
  `permission denied` -- confirmed revoked.
- **All three possible pairs** of the 3 recorded unseal keys in that same
  `init.json` (threshold 2-of-3, so there are exactly 3 pairs) fail
  `generate-root` identically with `cipher: message authentication
  failed`. `bao status` at the time showed `sealed: false`,
  `raft_applied_index: 420940` -- a long-lived, continuously-operating
  store, not a fresh empty reinit -- so the most likely explanation is
  that this instance was **rekeyed** at some point after `init.json` was
  written, without the file ever being updated to match. A rekey does not
  invalidate existing AppRole data (it only re-wraps the master key), so
  this is very likely unrelated to why `controller-automation` itself went
  stale.
- The other 3 AppRole credential files from the same `2026-04-28` batch
  (`atlas`, `mail-platform`, `secret-rotation`) were also tested and are
  all dead the same way (`invalid role or secret ID`) -- this looks like a
  batch-wide TTL expiry, not something specific to `controller-automation`.

**What actually worked**: the `breakglass` userpass account (policy grants
`sudo` on `path "*"`) is a genuinely separate recovery path from the
Shamir unseal-key/root-token ceremony above, and it was still alive. The
password in the live account did **not** match the current
`.local/openbao/breakglass-password.txt` on this Mac -- it matched an
older value from a since-superseded local file that had only survived by
accident in an old email. That confirms `breakglass-password.txt` itself
had drifted stale exactly like `controller-automation`'s AppRole; it has
since been rotated via `auth/userpass/users/breakglass/password` (the
password-only endpoint, so the account's existing policy/TTL were left
untouched) and the local file now matches live OpenBao again. Treat this
as the primary recovery path going forward, before reaching for
`generate-root` -- and back up `breakglass-password.txt` somewhere more
durable than this one gitignored local directory, since a single-Mac
local file with no redundancy is exactly what let this drift unnoticed.

Fix applied to `controller-automation` once inside via `breakglass`:
`secret_id_ttl=0` and `secret_id_num_uses=0` on the role (previously
whatever short-lived default caused the original expiry), so this
specific credential should not go stale again on its own.

Two SSH/curl gotchas hit while debugging this, worth knowing before
reaching for `generate-root` or any userpass/approle login by hand again:

- `ssh` inside a `while read line; do ssh ...; done < file` loop inherits
  the loop's stdin by default and silently consumes the *rest of the
  file* as its own input unless called with `ssh -n`. This is what made
  an early unseal-key submission loop stop after 1 key instead of 2.
- A JSON `-d` body sent through `ssh host "curl ... -d ..."` crosses two
  shells (local, then whatever `sh -c` runs remotely). Only
  single-quote-wrapping the JSON with its internal double quotes
  backslash-escaped survives that intact: `-d '{\"key\":\"$VAL\"}'` built
  as one local double-quoted string. Reassembling the curl invocation
  through a generic `"$*"`-based helper strips that protection and the
  remote shell mangles the JSON, which OpenBao reports back as a plain
  `error parsing JSON` -- easy to misread as a wrong password/credential
  when it isn't.

The current host Tailscale IP is `100.64.0.1`, and both the OpenBao and `step-ca` proxy certificates now cover that address directly.
