# Security Posture Reporting

This runbook covers the ADR 0102 security posture workflow that combines Lynis host scans with Trivy runtime image scans.

## Repo Surfaces

- `playbooks/tasks/security-scan.yml`
- `scripts/parse_lynis_report.py`
- `scripts/trivy_scan_running_images.sh`
- `scripts/security_posture_report.py`
- `config/windmill/scripts/security-posture-scan.py`
- `config/lynis-suppressions.json`
- `receipts/security-reports/`

## Local Execution

Run the full workflow from the controller checkout:

```bash
make security-posture-report
```

Or call the Python entrypoint directly:

```bash
python3 scripts/security_posture_report.py --env production --print-report-json
```

If the Lynis collection step already completed and you only need to retry aggregation or downstream publication, reuse the fetched `*.dat` files in `.local/security-posture/lynis/`:

```bash
uv run --with ansible-core --with pyyaml --with nats-py python scripts/security_posture_report.py --env production --skip-lynis --print-report-json
```

If the Lynis collection succeeds but the remote Trivy path flakes while waiting for
the guest-side Docker container, write a fresh host-only receipt from the same
cached Lynis data and record the Trivy failure separately in the live-apply
receipt or workstream notes:

```bash
uv run --with ansible-core --with pyyaml --with nats-py python scripts/security_posture_report.py --env production --skip-trivy --print-report-json
```

Use that fallback only to preserve fresh host evidence for vulnerability-budget
evaluation; it does not replace fixing the remote Trivy path or refreshing the
managed image receipts.

The workflow:

1. runs `playbooks/tasks/security-scan.yml` against the repo-managed Lynis targets
   derived from the active production service catalog (`proxmox_florin`,
   `docker-runtime-lv3`, `docker-build-lv3`, `backup-lv3`, `coolify-lv3`,
   `postgres-lv3`, `nginx-lv3`, and `monitoring-lv3`)
2. fetches each `report.dat` file into `.local/security-posture/lynis/`
3. parses and suppresses known-acceptable Lynis findings
4. SSHes to `docker-runtime-lv3` and `docker-build-lv3` and runs `scripts/trivy_scan_running_images.sh`
5. compares the new scan to the latest committed receipt in `receipts/security-reports/`
6. writes a new JSON receipt under `receipts/security-reports/`

## Outputs

Each receipt records:

- per-host hardening index
- per-host Lynis finding counts and new findings since the previous receipt
- per-image HIGH and CRITICAL CVEs
- an aggregate summary for portal and dashboard consumption

When the relevant environment variables or controller-local secret files are present, the workflow also:

- publishes `platform.security.*` NATS events
- posts a summary to Mattermost
- posts critical findings to GlitchTip
- writes `platform_security_posture_*` metrics to InfluxDB

## Windmill Worker Checkout

The Windmill-side wrapper expects the worker checkout at `/srv/proxmox_florin_server` to include the same repo surfaces the controller-side report needs:

- `ansible.cfg`
- `collections/`
- `config/`
- `inventory/`
- `playbooks/`
- `scripts/`

The `windmill_runtime` role now mirrors the required controller-local `bootstrap_ssh_private_key` and `nats_jetstream_admin_password` files into the worker checkout under `.local/` so `config/windmill/scripts/security-posture-scan.py` can execute the same report path honestly from the worker mount.

The inventory guest-jump path now honors `LV3_BOOTSTRAP_SSH_PRIVATE_KEY`, so worker-side Ansible runs can override the controller-only absolute key path with the mirrored worker checkout key.
Worker-side runs also honor `LV3_PROXMOX_HOST_ADDR`; the Windmill path prefers the Proxmox internal bridge address so guest SSH jumps stay on the private network instead of hairpinning through the management Tailscale address.

After updating the worker checkout from the latest `main`, verify the wrapper from the runtime VM with:

```bash
docker exec windmill_worker bash -lc 'cd /srv/proxmox_florin_server && python3 config/windmill/scripts/security-posture-scan.py --repo-path /srv/proxmox_florin_server'
```

Treat the run as successful only when the wrapper returns `status: ok` and includes a `REPORT_JSON=` payload from `scripts/security_posture_report.py`.
The inner `security_posture_report.py` command may still report `returncode: 1` when the generated summary status is `critical`; that indicates actionable findings were present, not that the worker automation path failed.

## Suppressions

Known-acceptable Lynis findings live in `config/lynis-suppressions.json`.

Add a suppression only when:

- the finding is persistent across scans
- the condition is understood
- the platform intentionally accepts the risk or cannot remediate it in repo automation yet

Prefer suppressing by Lynis finding id, not by raw text.

## Verification

Use these checks after a run:

```bash
python3 scripts/parse_lynis_report.py .local/security-posture/lynis
python3 scripts/security_posture_report.py --env production --print-report-json
```

Confirm:

- the newest file under `receipts/security-reports/` is valid JSON
- each expected active production host has a hardening index
- each Docker host contributed image scan data, or a documented `--skip-trivy`
  fallback explains why the receipt is host-only for that run
- the ops portal shows the latest security receipt summary
- `python3 scripts/vulnerability_budget.py --all` passes when no active
  exceptions have expired
