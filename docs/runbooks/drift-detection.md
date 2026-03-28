# Drift Detection

ADR 0091 adds a repository-managed drift suite that compares the declared platform state with live VM, service, DNS, and TLS state.

## Entry Points

- Local full run: `make drift-report ENV=production`
- CLI route: `lv3 diff --env production`
- Windmill workflow: `continuous-drift-detection`
- Windmill script path: `f/lv3/continuous_drift_detection`
- Latest receipts: `receipts/drift-reports/*.json`

## Receipt Shape

Each drift run writes one JSON receipt with:

- `generated_at`: UTC timestamp
- `environment`: `production` or `staging`
- `summary`: status code plus warn, critical, suppressed, and unsuppressed counts
- `records`: one entry per detected drift item

Each record includes the detector `source`, the impacted `service` or `resource`, the operator-facing `detail`, and whether the item was `workstream_suppressed`.

## Drift Sources

### OpenTofu

- Source id: `tofu`
- What it checks: planned VM changes from `scripts/tofu_exec.sh drift <env>`
- Typical fix: update the repo declaration or apply the intended OpenTofu state from the correct branch

### Ansible Check Mode

- Source id: `ansible-check-mode`
- What it checks: changes or unreachable hosts from `ansible-playbook --check --diff`
- Typical fix: rerun the owning playbook after verifying the host is reachable and the repo remains the source of truth

### Docker Image

- Source id: `docker-image`
- What it checks: running container digests from `docker inspect` against `config/image-catalog.json`
- Typical fix: redeploy the owning service so it returns to the pinned digest, or intentionally update the image catalog

### DNS

- Source id: `dns`
- What it checks: active records in `config/subdomain-catalog.json` against live resolver responses
- Typical fix: reprovision the record through the repo-managed subdomain workflow, then rerun drift detection

### TLS

- Source id: `tls`
- What it checks: certificate expiry and issuer from each HTTPS service URL
- Typical fix: renew the certificate on the owning service or edge publication path, then verify the issuer matches the declared provider

## Severity

- `warn`: drift exists but the service still appears healthy after the detector backoff probe
- `critical`: the drift is severe, the source itself failed, the service stayed unhealthy during backoff, or the certificate window is inside the critical threshold

## Workstream Suppression

Before a drift event is treated as actionable, the detector checks `workstreams.yaml` for `status: in_progress` entries whose `shared_surfaces` intersect the record surfaces.

When a match exists:

- the receipt sets `workstream_suppressed: true`
- the record still stays visible in the receipt and portal
- downstream alerting can skip it until the workstream closes

To override suppression during an investigation, temporarily set the workstream status away from `in_progress`, rerun the detector, then restore the correct state in the same branch if the suppression should remain.

## Metrics And Dashboard

If these environment variables are set when the detector runs, it also writes summary metrics for the Grafana platform dashboard:

- `DRIFT_INFLUXDB_URL`
- `DRIFT_INFLUXDB_BUCKET`
- `DRIFT_INFLUXDB_ORG`
- `DRIFT_INFLUXDB_TOKEN`

The dashboard reads the `platform_drift_summary` measurement and exposes:

- drift status code (`0` clean, `1` warn, `2` critical)
- unsuppressed drift count
- warn drift count
- critical drift count

## Verification

- `python3 -m py_compile scripts/drift_detector.py scripts/parse_ansible_drift.py scripts/docker_image_drift.py scripts/dns_drift.py scripts/tls_cert_drift.py`
- `echo '' | python3 scripts/parse_ansible_drift.py`
- `python3 scripts/drift_detector.py --help`
