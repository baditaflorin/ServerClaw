# Workstream ADR 0101: Automated Certificate Lifecycle Management

- ADR: [ADR 0101](../adr/0101-automated-certificate-lifecycle-management.md)
- Title: step renewal agent sidecar for all Compose services, TLS validity health probes, and certificate inventory catalog
- Status: ready
- Branch: `codex/adr-0101-certificate-lifecycle`
- Worktree: `../proxmox_florin_server-certificate-lifecycle`
- Owner: codex
- Depends On: `adr-0042-step-ca`, `adr-0047-mtls`, `adr-0064-health-probes`, `adr-0091-drift-detection`, `adr-0096-slo-tracking`, `adr-0097-alerting-routing`
- Conflicts With: none
- Shared Surfaces: `config/health-probe-catalog.json`, all Compose stacks, systemd unit files on VMs

## Scope

- write `config/certificate-catalog.json` — inventory of all certificates issued by step-ca and Let's Encrypt
- write `scripts/tls_cert_probe.py` — TLS certificate validity probe (expiry and issuer check)
- write `scripts/generate_cert_renewal_config.py` — reads certificate catalog and generates systemd timers and sidecar configs for all certificates
- write Ansible role `cert_renewer_sidecar` — adds the step cert-renewer sidecar container to each Compose stack that has a TLS certificate
- update all relevant Compose service roles to include the cert-renewer sidecar (keycloak, netbox, mattermost, windmill, portainer, open_webui)
- write Ansible role `cert_renewal_timer` — manages systemd timers for VM-hosted services (openbao, step-ca itself)
- add TLS validity probes for all services to `config/health-probe-catalog.json`
- add cert expiry alert rules to `config/alertmanager/rules/platform.yml`
- write `docs/runbooks/cert-expired.md` — emergency manual renewal procedure
- add `config/certificate-catalog.json` to the schema validation gate (ADR 0087)

## Non-Goals

- Certificate issuance (covered by ADR 0042)
- OCSP stapling configuration in this iteration
- Automatic CA root rotation

## Expected Repo Surfaces

- `config/certificate-catalog.json`
- `scripts/tls_cert_probe.py`
- `scripts/generate_cert_renewal_config.py`
- `roles/cert_renewer_sidecar/`
- `roles/cert_renewal_timer/`
- All Compose service roles (patched: sidecar added where applicable)
- `config/health-probe-catalog.json` (patched: TLS probes added)
- `config/alertmanager/rules/platform.yml` (patched: cert expiry alerts added)
- `docs/runbooks/cert-expired.md`
- `docs/adr/0101-automated-certificate-lifecycle-management.md`
- `docs/workstreams/adr-0101-certificate-lifecycle.md`

## Expected Live Surfaces

- All running services have TLS certificates with > 30 days remaining (verified by `scripts/tls_cert_probe.py` run)
- cert-renewer sidecar is running in all applicable Compose stacks
- Grafana shows TLS expiry days for all certificates in the inventory

## Verification

- Run `python3 scripts/tls_cert_probe.py` against all service URLs in the certificate catalog; all should return OK (> 21 days remaining)
- Stop the cert-renewer sidecar on one Compose service; verify the cert does NOT renew automatically; restart the sidecar; verify it resumes
- Introduce a test certificate with 5 days remaining; verify the `CertExpiryWarning` and `CertExpiryCritical` alerts fire in Alertmanager

## Merge Criteria

- All Compose services that need TLS have a running cert-renewer sidecar
- `python3 scripts/tls_cert_probe.py` passes for all services in `config/certificate-catalog.json`
- Cert expiry alerts configured in Alertmanager
- Certificate catalog validates against its JSON schema

## Notes For The Next Assistant

- The `--exec "kill -HUP $(cat /var/run/service.pid)"` pattern for cert reload requires that the container exposes its PID file; for services that do not (most Docker images), use `--exec "docker kill --signal HUP <container_name>"` from the sidecar — but this requires the Docker socket to be mounted in the sidecar, which is a security consideration; discuss in the ADR implementation notes
- Let's Encrypt certificates for edge-published subdomains are renewed by certbot on `nginx-lv3`; these are already automated; just add them to the certificate catalog for inventory purposes without adding a sidecar (certbot handles renewal)
- The step-ca certificate for step-ca itself (bootstrap cert) has a different renewal process; it is renewed by the step-ca CA itself using its own provisioner; document this special case in `config/certificate-catalog.json` with `renewal_agent: step-ca-self`
