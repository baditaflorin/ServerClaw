# Configure OpenBao

## Purpose

This runbook converges ADR 0043 by deploying a private OpenBao service on `docker-runtime-lv3`, seeding the current platform secret sets into OpenBao, enabling Transit, and wiring PostgreSQL dynamic credentials through `postgres-lv3`.

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

1. The controller SSH key exists at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`.
2. `docker-runtime-lv3` and `postgres-lv3` are reachable through the Proxmox jump path.
3. The existing controller-local mail, monitoring, and Proxmox API artifacts are present so the workflow can seed them into OpenBao.

## What The Workflow Changes

1. Reuses the shared ADR 0067 guest network policy that allows `docker-runtime-lv3` to reach `postgres-lv3`, while this workflow manages PostgreSQL authentication through `pg_hba.conf`.
2. Creates the `openbao_rotator` PostgreSQL role with the minimum privileges needed to issue dynamic read-only credentials.
3. Starts a Compose-managed OpenBao container under `/opt/openbao` with integrated Raft storage, a loopback-published HTTP listener on `127.0.0.1:8201`, and a managed step-ca-backed TLS listener on `:8200`.
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

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/init.json`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/ops-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/breakglass-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/postgres-rotator-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/controller-automation-approle.json`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/mail-platform-approle.json`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/secret-rotation-approle.json`

Treat the entire `.local/openbao/` subtree as recovery material and keep it out of git.

## Verification

Basic runtime checks:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.20 docker compose --file /opt/openbao/docker-compose.yml ps'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=no ops@10.10.10.20 curl -fsS http://127.0.0.1:8201/v1/sys/health'
```

Routine operator login over an SSH port forward:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -L 8201:127.0.0.1:8201 ops@100.118.189.95 'ssh -o ExitOnForwardFailure=yes -N -L 8201:127.0.0.1:8201 ops@10.10.10.20'
curl --request POST --data "{\"password\":\"$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/ops-password.txt)\"}" http://127.0.0.1:8201/v1/auth/userpass/login/ops
```

Controller AppRole login and dynamic credential fetch:

```bash
role_id="$(jq -r '.role_id' /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/controller-automation-approle.json)"
secret_id="$(jq -r '.secret_id' /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openbao/controller-automation-approle.json)"
token="$(curl -fsS --request POST --data "{\"role_id\":\"$role_id\",\"secret_id\":\"$secret_id\"}" http://127.0.0.1:8201/v1/auth/approle/login | jq -r '.auth.client_token')"
curl -fsS --header "X-Vault-Token: $token" http://127.0.0.1:8201/v1/database/creds/postgres-readonly
```

Controller-side mTLS verification for the private OpenBao API:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSLo "$tmpdir/step.tar.gz" https://github.com/smallstep/cli/releases/download/v0.30.1/step_darwin_0.30.1_arm64.tar.gz
tar -xf "$tmpdir/step.tar.gz" -C "$tmpdir"
"$tmpdir/step_0.30.1/bin/step" ca certificate \
  --force \
  --provisioner services \
  --provisioner-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/provisioners/services-password.txt \
  --ca-url https://100.118.189.95:9443 \
  --root /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt \
  --san openbao-client.lv3.internal \
  --not-after 1h \
  openbao-client.lv3.internal "$tmpdir/client.crt" "$tmpdir/client.key"
curl --cert "$tmpdir/client.crt" \
  --key "$tmpdir/client.key" \
  --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt \
  https://100.118.189.95:8200/v1/sys/health
curl --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt \
  https://100.118.189.95:8200/v1/sys/health
```

## Notes

- The loopback HTTP API on `127.0.0.1:8201` remains the managed automation and operator path for bootstrap, verification, and recovery-safe forwarding.
- The external OpenBao API on `https://100.118.189.95:8200` is private-only, published through the Proxmox host Tailscale path, and requires a valid client certificate signed by `step-ca`.
- The current implementation seeds existing mail, monitoring, Proxmox API, Windmill, and mail-profile artifacts into OpenBao so later consumers can fetch them without reintroducing git-managed secrets.
- Dedicated rotatable secret paths and their metadata now align with `config/secret-catalog.json`, so future scheduled evaluators can inspect bounded credential age directly in OpenBao.
