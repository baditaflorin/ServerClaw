# Workstream ADR 0101: Automated Certificate Lifecycle Management

- ADR: [ADR 0101](../adr/0101-automated-certificate-lifecycle-management.md)
- Title: certificate inventory, TLS probes, and repo-managed renewal for current HTTPS endpoints
- Status: merged
- Branch: `codex/adr-0101-certificate-lifecycle`
- Worktree: `../proxmox_florin_server-certificate-lifecycle`
- Owner: codex
- Depends On: `adr-0042-step-ca`, `adr-0047-mtls`, `adr-0064-health-probes`, `adr-0091-drift-detection`, `adr-0096-slo-tracking`, `adr-0097-alerting-routing`
- Conflicts With: none
- Shared Surfaces: `config/health-probe-catalog.json`, `config/certificate-catalog.json`, systemd unit files on VMs, TLS-owning service roles

## Scope

- write `config/certificate-catalog.json` — inventory of all certificates issued by step-ca and Let's Encrypt
- write `scripts/tls_cert_probe.py` — TLS certificate validity probe (expiry and issuer check)
- write `scripts/generate_cert_renewal_config.py` — reads certificate catalog and generates systemd timers and sidecar configs for all certificates
- write Ansible role `cert_renewer_sidecar` — reusable future path for TLS-owning Compose stacks
- write Ansible role `cert_renewal_timer` — manages systemd timers for repo-owned renewal paths
- patch `openbao_runtime` to install the first repo-managed TLS renewal timer
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
- `roles/openbao_runtime/` (patched: repo-managed OpenBao renewal timer installed)
- `config/health-probe-catalog.json` (patched: TLS probes added)
- `config/alertmanager/rules/platform.yml` (patched: cert expiry alerts added)
- `docs/runbooks/cert-expired.md`
- `docs/adr/0101-automated-certificate-lifecycle-management.md`
- `docs/workstreams/adr-0101-certificate-lifecycle.md`

## Expected Live Surfaces

- All active HTTPS endpoints are inventoried in `config/certificate-catalog.json`
- `openbao_runtime` installs a persistent renewal timer on `docker-runtime-lv3`
- TLS observation and drift checks read from the same certificate catalog

## Verification

- Run `uv run --with pytest python -m pytest tests/test_tls_cert_probe.py tests/test_generate_cert_renewal_config.py tests/test_tls_cert_drift.py tests/test_platform_observation_tool.py -q`
- Run `uv run --with pytest python -m pytest tests/test_compose_runtime_secret_injection.py -q`
- Run `uv run --with pyyaml python scripts/validate_repository_data_models.py --validate`
- Run `python3 scripts/generate_cert_renewal_config.py --pretty`

## Merge Criteria

- `python3 scripts/tls_cert_probe.py` can probe the current certificate catalog
- the OpenBao renewal timer is rendered and enabled from the role
- Cert expiry alerts configured in Alertmanager
- Certificate catalog validates against its JSON schema

## Outcome

- Added the canonical `config/certificate-catalog.json` inventory plus `docs/schema/certificate-catalog.schema.json`
- Implemented `scripts/tls_cert_probe.py` and moved certificate observation and drift logic onto that shared catalog
- Added `scripts/generate_cert_renewal_config.py` so renewal ownership is machine-readable instead of implied
- Added reusable `cert_renewal_timer` and `cert_renewer_sidecar` roles
- Patched `openbao_runtime` to install the first repository-managed TLS renewal timer
- Extended `config/health-probe-catalog.json` with `tls_certificate_ids`
- Added the emergency manual-rotation runbook and the repo-managed alert rules file

## Notes For The Next Assistant

- The broad `./scripts/validate_repo.sh all` gate is slower than the focused checks because `ansible-lint` walks the whole playbook tree.
- Current `main` only has one renewal path the repository truly owns: OpenBao. The other HTTPS surfaces are now inventoried and probed instead of being over-automated incorrectly.
- The committed alert rules are a repo contract for ADR 0097; they are not yet a statement that Alertmanager is already live on this branch.
