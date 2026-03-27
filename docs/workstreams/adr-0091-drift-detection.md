# Workstream ADR 0091: Continuous Drift Detection and Reconciliation

- ADR: [ADR 0091](../adr/0091-continuous-drift-detection.md)
- Title: Scheduled drift detection across VM resources, service configuration, Docker images, DNS, and TLS — surfaced in the ops portal with NATS event emission
- Status: merged
- Branch: `codex/adr-0091-drift-detection`
- Worktree: `../proxmox_florin_server-drift-detection`
- Owner: codex
- Depends On: `adr-0085-opentofu-vm-lifecycle`, `adr-0074-ops-portal`, `adr-0075-service-capability-catalog`, `adr-0058-nats-jetstream`
- Conflicts With: none
- Shared Surfaces: `scripts/`, `config/`, Windmill workflows, Grafana dashboards, NATS subjects

## Scope

- write `scripts/drift_detector.py` — orchestrates all five drift sources and emits NATS events
- write `scripts/parse_ansible_drift.py` — parses `ansible-playbook --check --diff` output into structured per-host per-role per-task drift records
- write `scripts/docker_image_drift.py` — queries Docker daemon on each host, compares running image digests against `config/image-catalog.json`
- write `scripts/dns_drift.py` — queries internal DNS for each entry in `config/subdomain-catalog.json`, compares to declared records
- write `scripts/tls_cert_drift.py` — checks TLS expiry and issuer for all service URLs
- write Windmill workflow `continuous-drift-detection` — calls `make tofu-drift` and `scripts/drift_detector.py` in sequence; runs every 6 hours and on every merge to `main`
- add `make drift-report ENV=<env>` target (runs the full drift check locally, prints summary)
- update Grafana dashboards: add `Drift Status` panel to the platform overview dashboard
- write `docs/runbooks/drift-detection.md` — how to read drift reports, how to resolve common drift types
- add `lv3 diff` to the platform CLI (ADR 0090 integration)

## Non-Goals

- automatic reconciliation (auto-heal) — this workstream is detection only; reconciliation is always an operator-initiated action
- drift detection for LXC containers (VMs and Compose services only)

## Expected Repo Surfaces

- `scripts/drift_detector.py`
- `scripts/parse_ansible_drift.py`
- `scripts/docker_image_drift.py`
- `scripts/dns_drift.py`
- `scripts/tls_cert_drift.py`
- Windmill script `config/windmill/scripts/continuous-drift-detection.py`
- updated Grafana dashboard template in `collections/ansible_collections/lv3/platform/roles/monitoring_vm/templates/lv3-platform-overview.json.j2`
- `receipts/drift-reports/.gitkeep`
- updated `Makefile` (`drift-report`)
- `docs/runbooks/drift-detection.md`
- `docs/adr/0091-continuous-drift-detection.md`
- `docs/workstreams/adr-0091-drift-detection.md`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill `continuous-drift-detection` workflow is scheduled every 6 hours and has a successful run history
- Grafana `Drift Status` panel on the platform overview dashboard shows green (no drift on `main` after deployment)
- NATS subject `platform.drift.*` is queryable from the controller

## Verification

- introduce a deliberate VM resource change in Proxmox UI (change CPU from 4 to 3 on a test VM); run `make drift-report`; verify the change appears as `warn` drift in the output
- revert the change; run `make drift-report` again; verify no drift reported
- `scripts/tls_cert_drift.py` correctly identifies a test certificate with a 5-day expiry as `critical`
- Windmill workflow completes in < 5 minutes for the full platform (5 drift sources in sequence)

## Merge Criteria

- all five drift detectors produce valid JSON output against the live platform
- NATS `platform.drift.warn` event is published and received by the NATS subscriber (verified with `nats sub platform.drift.*`)
- Grafana panel updated and showing real drift data (or green if clean)
- `make drift-report` exits 0 on a clean `main` platform state

## Notes For The Next Assistant

- `parse_ansible_drift.py` must handle the case where `--check` fails with a non-diff error (e.g., connection refused to a VM); treat this as a separate `platform.drift.unreachable` event, not a false-positive diff
- the Docker image digest comparison must use the `RepoDigests` field from `docker inspect`, not the image tag; tags are mutable and can point to different digests
- add exponential backoff to all health probes in `drift_detector.py`; a service restarting during the drift check must not generate a false-positive drift event
- workstream suppression: before emitting any `warn` event, check `workstreams.yaml` for any workstream in status `in_progress` whose `shared_surfaces` intersects the drifting resource; if found, set `workstream_suppressed: true` in the event and skip the Grafana alert

## Outcome

- repository implementation is complete on `main` in repo release `0.94.0`
- `make drift-report`, `lv3 diff`, the Windmill `continuous-drift-detection` workflow surface, the ops portal drift panel, the NATS subject registration, and the Grafana drift summary panels now ship from the repository state
- no live platform version change is claimed yet; scheduling, dashboard ingestion, and the live receipt stream still require apply from `main`
