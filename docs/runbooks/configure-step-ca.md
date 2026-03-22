# Configure step-ca

## Purpose

This runbook converges ADR 0042 by deploying a private `step-ca` on `docker-runtime-lv3`, exposing it through the Proxmox host Tailscale address, and wiring SSH CA trust into the Proxmox host and managed guests.

## Entry Point

Preferred workflow:

```bash
make converge-step-ca
```

Equivalent syntax check:

```bash
make syntax-check-step-ca
```

## Preconditions

1. The controller SSH key exists at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`.
2. `docker-runtime-lv3` is reachable through the Proxmox jump path.
3. The Proxmox host Tailscale path is working at `100.118.189.95`.

## What The Workflow Changes

1. Installs `step` CLI tooling where needed.
2. Initializes a private CA under `/opt/step-ca` on `docker-runtime-lv3`.
3. Creates separate JWK provisioners for `humans`, `agents`, `services`, and `hosts`.
4. Starts a Compose-managed `step-ca` container on private port `9000`.
5. Publishes the CA API at `https://100.118.189.95:9443` through the Proxmox host Tailscale proxy.
6. Mirrors trust bootstrap artifacts and provisioner passwords to `.local/step-ca/` on the controller.
7. Configures `TrustedUserCAKeys` and SSH host certificates on the Proxmox host and managed guests.

## Controller-Local Artifacts

The converge creates these controller-local files:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/bootstrap.json`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/ssh_user_ca.pub`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/ssh_host_ca.pub`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/ssh/known_hosts`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/ca-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/provisioners/humans-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/provisioners/agents-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/provisioners/services-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/provisioners/hosts-password.txt`

Treat the `secrets/` subtree as sensitive material and keep it out of git.

## Verification

Basic runtime checks:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/step-ca/docker-compose.yml ps'
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo systemctl status lv3-tailscale-proxy-step-ca.socket --no-pager'
curl --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt https://100.118.189.95:9443/health
```

Issue a short-lived user certificate for `ops` and verify SSH against the CA-backed host certificates:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSLo "$tmpdir/step.tar.gz" https://github.com/smallstep/cli/releases/download/v0.30.1/step_darwin_0.30.1_arm64.tar.gz
tar -xf "$tmpdir/step.tar.gz" -C "$tmpdir"
"$tmpdir/step_0.30.1/bin/step" ssh certificate \
  --force \
  --no-agent \
  --insecure \
  --no-password \
  --provisioner humans \
  --provisioner-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/provisioners/humans-password.txt \
  --ca-url https://100.118.189.95:9443 \
  --root /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt \
  --not-after 8h \
  ops "$tmpdir/ops-ed25519"
ssh \
  -i "$tmpdir/ops-ed25519" \
  -o IdentitiesOnly=yes \
  -o CertificateFile="$tmpdir/ops-ed25519-cert.pub" \
  -o UserKnownHostsFile=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/ssh/known_hosts \
  -o StrictHostKeyChecking=yes \
  ops@100.118.189.95 hostname
ssh \
  -i "$tmpdir/ops-ed25519" \
  -o IdentitiesOnly=yes \
  -o CertificateFile="$tmpdir/ops-ed25519-cert.pub" \
  -o UserKnownHostsFile=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/ssh/known_hosts \
  -o StrictHostKeyChecking=yes \
  -o ProxyCommand="ssh -i $tmpdir/ops-ed25519 -o IdentitiesOnly=yes -o CertificateFile=$tmpdir/ops-ed25519-cert.pub -o UserKnownHostsFile=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/ssh/known_hosts -o StrictHostKeyChecking=yes ops@100.118.189.95 -W %h:%p" \
  ops@10.10.10.20 hostname
```

Issue and validate a private X.509 leaf certificate:

```bash
"$tmpdir/step_0.30.1/bin/step" ca certificate \
  --force \
  --provisioner services \
  --provisioner-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/provisioners/services-password.txt \
  --password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/secrets/provisioners/services-password.txt \
  --ca-url https://100.118.189.95:9443 \
  --root /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt \
  --san service-test.lv3.internal \
  --not-after 1h \
  service-test.lv3.internal "$tmpdir/service-test.crt" "$tmpdir/service-test.key"
openssl verify -CAfile /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt "$tmpdir/service-test.crt"
```

## Notes

- The CA stays private. There is no public-edge publication for ADR 0042.
- The existing bootstrap SSH key remains in place as a recovery path; the CA-backed SSH path is additive.
- The controller verification example above assumes an Apple Silicon controller because the current workstation is arm64 macOS. Use the matching `step` archive for other controller platforms.
- The temporary SSH verification key is intentionally written unencrypted with `--insecure --no-password` so non-interactive SSH can complete during validation; remove the temporary directory immediately after use.
