# HTTPS And TLS Assurance

This runbook covers the ADR 0249 path that combines recurring Prometheus
blackbox probes with deeper `testssl.sh` scans for every declared HTTPS
surface.

## Repo Surfaces

- `scripts/https_tls_assurance_targets.py`
- `scripts/generate_https_tls_assurance.py`
- `scripts/https_tls_assurance.py`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/windmill/scripts/https-tls-assurance.py`
- `receipts/https-tls-assurance/`

## Local Execution

Regenerate the committed Prometheus inputs:

```bash
make generate-https-tls-assurance
```

Run the deeper TLS posture scan:

```bash
make https-tls-assurance ENV=production
```

The scheduled and `make` paths default to a 60-second per-target `testssl.sh`
timeout so the sequential 31-surface production scan stays within the weekly
workflow budget. Override it when a slower manual replay is intentional:

```bash
make https-tls-assurance ENV=production HTTPS_TLS_TIMEOUT_SECONDS=180
```

Or call the Python entrypoints directly:

```bash
uv run --with pyyaml python scripts/generate_https_tls_assurance.py --write
uv run --with pyyaml python scripts/https_tls_assurance.py --env production --timeout-seconds 60 --print-report-json
```

## What the workflow does

1. Discovers active HTTPS surfaces from the service, subdomain, certificate,
   and health-probe catalogs.
2. Generates the Prometheus blackbox target set and expiry/failure alert rules
   from that shared discovery path.
3. Lets the monitoring stack scrape the HTTPS surfaces continuously from
   `monitoring-lv3`.
4. Runs `testssl.sh` against the same surface set for periodic protocol,
   cipher, and certificate-regression checks.
5. Writes a receipt under `receipts/https-tls-assurance/`.

## Outputs

Each TLS assurance receipt records:

- the discovered HTTPS target set with service and scope labels
- the raw `testssl.sh` artifact path per target
- classified TLS findings by severity
- an aggregate pass, warn, high, or critical summary

Raw `testssl.sh` artifacts are stored under
`.local/https-tls-assurance/<scan_id>/testssl/`.

## Verification

Use these checks after regenerating or replaying the workflow:

```bash
python3 -m py_compile scripts/https_tls_assurance_targets.py scripts/generate_https_tls_assurance.py scripts/https_tls_assurance.py config/windmill/scripts/https-tls-assurance.py
uv run --with pyyaml python scripts/generate_https_tls_assurance.py --check
uv run --with pyyaml python scripts/https_tls_assurance.py --env production --skip-testssl --print-report-json
uv run --with pytest --with pyyaml pytest -q tests/test_https_tls_assurance_targets.py tests/test_monitoring_vm_role.py tests/test_https_tls_assurance_windmill_wrapper.py
```

After `make converge-monitoring`, confirm:

- `/etc/prometheus/file_sd/https-tls-targets.yml` exists on `monitoring-lv3`
- `/etc/prometheus/rules/https-tls-alerts.yml` exists on `monitoring-lv3`
- Prometheus reports the `https-tls-blackbox` job as healthy
- the newest receipt under `receipts/https-tls-assurance/` matches the current
  discovered target set

If `ssh -J` is unreliable from a clean controller checkout, the same guest
verification can use an explicit proxy hop instead:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -W %h:%p ops@100.64.0.1' ops@10.10.10.40 'curl -fsS http://127.0.0.1:9090/api/v1/rules | jq -e ".data.groups[] | select(.name == \"https_tls_assurance\")" >/dev/null'
```
