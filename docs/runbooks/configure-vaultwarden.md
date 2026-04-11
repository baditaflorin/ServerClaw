# Configure Vaultwarden

## Purpose

This runbook converges ADR 0147 by deploying a private Vaultwarden service on `runtime-control`, provisioning its PostgreSQL backend on `postgres`, publishing it only through the Proxmox host Tailscale path, and seeding the bounded admin bootstrap path.

## Entry Point

Preferred workflow:

```bash
make converge-vaultwarden
```

Equivalent syntax check:

```bash
make syntax-check-vaultwarden
```

## Preconditions

1. The controller SSH key exists at `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`.
2. `runtime-control`, `postgres`, and the private `step-ca` service are already reachable through the Proxmox jump path.
3. Operators who need browser or Bitwarden-extension access trust the LV3 internal CA root certificate from `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt`.

## What The Workflow Changes

1. Creates the `vaultwarden` PostgreSQL database and login role on `postgres`.
2. Generates a controller-local database password and admin token under `.local/vaultwarden/`.
3. Issues a private TLS certificate for `vault.example.com` from `step-ca` and installs a managed renewal timer on `runtime-control`.
4. Starts a Compose-managed Vaultwarden container under `/opt/vaultwarden`.
5. Publishes the HTTPS listener through the Proxmox host Tailscale TCP proxy so operators use `https://vault.example.com`.
6. Invites `ops@example.com` through the Vaultwarden admin API if that account has not already been created.

## Controller-Local Artifacts

The converge creates these controller-local files:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/vaultwarden/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/vaultwarden/admin-token.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/vaultwarden/admin-token-argon2.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/vaultwarden/bootstrap.json`

Treat the entire `.local/vaultwarden/` subtree as sensitive recovery material and keep it out of git.

## Verification

Basic runtime checks:

```bash
make syntax-check-vaultwarden
curl --http1.1 \
  --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt \
  --resolve vault.example.com:443:100.64.0.1 \
  https://vault.example.com/alive
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.92 'docker compose --file /opt/vaultwarden/docker-compose.yml ps'
```

Admin bootstrap smoke test:

```bash
tmp_cookie="$(mktemp)"
trap 'rm -f "$tmp_cookie"' EXIT
curl --silent --show-error \
  --http1.1 \
  --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt \
  --resolve vault.example.com:443:100.64.0.1 \
  --cookie-jar "$tmp_cookie" \
  --data-urlencode "token=$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/vaultwarden/admin-token.txt)" \
  https://vault.example.com/admin/ >/dev/null
curl --silent --show-error \
  --http1.1 \
  --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt \
  --resolve vault.example.com:443:100.64.0.1 \
  --cookie "$tmp_cookie" \
  https://vault.example.com/admin/users/by-mail/ops%40example.com
```

## First Operator Login

After the first successful converge:

1. Open `https://vault.example.com`.
2. Complete the invited-account registration flow for `ops@example.com`.
3. Create the `LV3 Platform` organisation.
4. Create the shared `platform-recovery` and `platform-services` collections.
5. Move break-glass passwords, recovery codes, and external operator credentials into the shared collections.
6. Record completion in the relevant workstream or ADR follow-up if any manual migration remains.

## Notes

- `vault.example.com` is intentionally private-only. Do not publish Vaultwarden through the public NGINX edge.
- The service certificate is signed by the internal LV3 CA, not a public CA. Operator clients must trust the private root certificate.
- Controller-side manual `curl` verification should force `--http1.1` and pin `vault.example.com` to `100.64.0.1`; the current Tailscale proxy path can return an empty reply or time out when libcurl negotiates HTTP/2 by default even though the service itself is healthy.
- The admin token is a bounded bootstrap path for invitation and recovery-safe checks; routine operator usage should happen through named Vaultwarden accounts, not through the admin panel.
