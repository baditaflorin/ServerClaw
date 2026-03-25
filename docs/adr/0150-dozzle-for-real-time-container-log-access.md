# ADR 0150: Dozzle for Real-Time Container Log Access

- Status: Accepted
- Implementation Status: Implemented on workstream branch
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

The platform already had Loki for retained log search and Grafana for historical
queries, but it still lacked a repo-managed surface for sub-second log tailing
during deploys, break-fix work, and incident response.

The existing options each left a gap:

- SSH plus `docker logs -f` required direct host access and service-specific
  container knowledge.
- Portainer provided runtime inspection but not a purpose-built real-time,
  multi-host log-tailing surface.
- Loki remained the long-term system of record, but its ingest pipeline added
  enough latency to be awkward while watching a deployment or restart live.

## Decision

We run Dozzle as a repo-managed hub-and-agent deployment.

### Runtime shape

- service id: `dozzle`
- hub host: `docker-runtime-lv3`
- agent hosts: `docker-runtime-lv3`, `docker-build-lv3`, `monitoring-lv3`
- hub private port: `8089`
- agent port: `7007`
- public hostname: `logs.lv3.org`
- publication model: shared NGINX edge plus Keycloak-backed oauth2-proxy
- pinned image: `docker.io/amir20/dozzle:v10.2.0@sha256:35da6eb0ce33dc413d85017877121e82b1626f9247c4fb2acf1f19427cbf47c7`

The hub runs on `docker-runtime-lv3` and aggregates the local agent plus the
remote agents on `docker-build-lv3` and `monitoring-lv3`. Each agent is bound
only to the private guest network and the repo-managed guest firewall only
allows the hub host to reach the remote agent port.

### Access boundary

`logs.lv3.org` is published through the shared NGINX edge and protected by the
existing oauth2-proxy plus Keycloak browser session from ADR 0133. The Dozzle
runtime itself does not enable container actions or shell access and remains a
read-only log surface.

The edge route enables streaming-safe proxy settings for Server-Sent Events so
Dozzle tail sessions are not delayed by response buffering.

### Platform integration

The service is wired into the image, workflow, command, service, health-probe,
SLO, dependency, data, alerting, subdomain, and exposure catalogs so it
behaves like the other repo-managed runtime surfaces.

The API gateway now also exposes the private Dozzle API at `/v1/dozzle`,
keeping real-time log access available to governed automation without requiring
ad hoc host access.

## Consequences

### Positive

- Operators can tail container logs from one browser surface without SSH.
- The hub consolidates the three managed Docker hosts into one repo-managed log
  view.
- The API gateway route provides a governed integration path for future
  diagnostic tooling that needs fresher signals than Loki can provide.

### Trade-offs

- Dozzle is intentionally not a retention system. Historical log search and
  long-term evidence remain in Loki.
- The runtime still depends on Docker socket access on each agent host, so the
  no-actions and no-shell boundary must remain explicit.
- `logs.lv3.org` depends on the shared NGINX edge and Keycloak gate for the
  preferred operator path, even though the private hub remains reachable on the
  guest network when debugging the service itself.

## Verification

The workstream implementation on 2026-03-25 verified:

- `uv run --with pytest python -m pytest tests/test_dozzle_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_validate_portal_auth.py tests/test_subdomain_exposure_audit.py -q`
  passed with `25 passed`
- `make syntax-check-dozzle` passed
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
  passed
- `uvx --from ansible-lint ansible-lint playbooks/dozzle.yml collections/ansible_collections/lv3/platform/playbooks/dozzle.yml roles/dozzle_runtime collections/ansible_collections/lv3/platform/roles/dozzle_runtime`
  passed
- `./scripts/validate_repo.sh health-probes` and `./scripts/validate_repo.sh alert-rules`
  passed

Live apply remains pending because this session could not reach the managed
environment: direct SSH to `100.118.189.95` and `65.108.75.123` failed, and
`make check-build-server` reported `build server ops@10.10.10.30 is
unreachable`.

## Related ADRs

- ADR 0023: Docker runtime VM baseline
- ADR 0052: Centralized log aggregation with Grafana Loki
- ADR 0055: Portainer for read-mostly Docker runtime operations
- ADR 0133: Portal authentication by default
