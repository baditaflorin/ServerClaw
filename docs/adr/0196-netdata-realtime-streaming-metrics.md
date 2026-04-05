# ADR 0196: Netdata Realtime Streaming Metrics

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.25
- Implemented In Platform Version: 0.130.32
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

The platform already has Grafana, Prometheus, Loki, and Uptime Kuma for
historical observability and governed alerts, but operators still lack a
repo-managed surface for live host and guest metric inspection during deploys,
incident response, and break-fix work.

The current gap is specifically about immediacy:

- Grafana dashboards emphasize retained history and curated views.
- Prometheus is the authoritative time-series backend, but not the fastest
  browser-first surface for ad hoc live debugging.
- SSH plus ad hoc host tools does not satisfy the repo-managed, operator-safe
  workflow expected for routine production use.

## Decision

We deploy Netdata as a parent-plus-children topology for real-time metrics.

### Runtime shape

- service id: `realtime`
- product: Netdata
- parent host: `monitoring-lv3`
- child agents: all hosts in `lv3_guests` + `proxmox_hosts` for the active
  environment, excluding the monitoring parent — derived dynamically from
  inventory groups (see ADR 0319). No hardcoded list is maintained.
- parent listener: `http://10.10.10.40:19999`
- public URL: `https://realtime.lv3.org`
- publication model: shared NGINX edge plus the existing Keycloak-backed
  oauth2-proxy gate
- retention target: one day of parent-local dbengine retention for live
  troubleshooting, with child nodes keeping only lightweight local state

### Platform integration

- `netdata_runtime` is the repo-managed role for both parent and child hosts.
- The parent exports consolidated metrics to Prometheus through Netdata's
  built-in Prometheus endpoint.
- The public route reuses the shared edge auth stack instead of introducing a
  service-specific browser auth flow.
- The service is registered in the service, subdomain, health-probe,
  dependency, SLO, and data catalogs.
- A read-only API gateway route exposes the private Netdata parent under
  `/v1/realtime` for governed automation without requiring ad hoc host access.
- The operator CLI adds `lv3 realtime <vm-name>` as the browser-first shortcut
  into the live metrics surface.
- ADR 0071's observation loop consumes a Netdata anomaly signal so the live
  troubleshooting surface also contributes a governed drift signal.

## Consequences

### Positive

- Operators gain a low-latency browser surface for live CPU, memory, disk,
  network, and anomaly signals without dropping to ad hoc host commands.
- The metrics path stays repo-managed and re-runnable from the same automation
  model already used for the monitoring and edge stacks.
- Prometheus can ingest the consolidated Netdata export without duplicating the
  parent-child topology in another runtime.

### Trade-offs

- Netdata becomes another operator-facing runtime that must stay within the
  guest and shared-edge security model.
- The parent keeps only short retention by design, so longer-lived analysis
  remains in the existing Grafana and Prometheus surfaces.
- The public route depends on the shared edge auth and certificate surface even
  though the private parent stays reachable on the guest network for recovery.

## Verification

The 2026-03-27 rollout verified:

- `uv run --with pytest --with jsonschema python -m pytest tests/test_generate_platform_vars.py tests/test_subdomain_catalog.py tests/test_validate_service_catalog.py tests/test_nginx_edge_publication_role.py tests/test_monitoring_vm_role.py tests/test_netdata_runtime_role.py tests/test_realtime_playbook.py -q`
  passed with `42 passed`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  `make syntax-check-realtime`, `make workflow-info WORKFLOW=converge-realtime`,
  and `./scripts/validate_repo.sh health-probes alert-rules agent-standards`
  passed after the final branch updates
- `make live-apply-service service=realtime env=production EXTRA_ARGS='-e bypass_promotion=true'`
  completed successfully and converged the parent, child agents, monitoring
  scrape path, and shared edge publication
- `HETZNER_DNS_API_TOKEN=... make converge-realtime env=production` reran
  cleanly through the dedicated workflow wrapper and finished with
  `monitoring-lv3 : ok=185 changed=9 failed=0`, `nginx-lv3 : ok=100 changed=3 failed=0`,
  `proxmox_florin : ok=55 changed=0 failed=0`, `docker-runtime-lv3 : ok=26 changed=2 failed=0`,
  and `postgres-lv3 : ok=24 changed=0 failed=0`
- Prometheus on `monitoring-lv3` returned five `netdata_info{job="netdata"}`
  series for the realtime service topology, proving the consolidated parent
  export is being scraped
- `dig +short realtime.lv3.org` returned `65.108.75.123` and
  `curl -skI https://realtime.lv3.org/` returned `HTTP/2 302` to
  `/oauth2/sign_in`, confirming the public route and shared auth gate
- `make uptime-kuma-manage ACTION=bootstrap UPTIME_KUMA_ARGS='--base-url https://uptime.lv3.org'`
  created the private `Realtime Metrics Private` monitor and
  `make uptime-kuma-manage ACTION=ensure-monitors` reran cleanly from the
  separate worktree
- a latest-main replay on 2026-03-28 uncovered that the realtime playbook was
  not inheriting `inventory/group_vars/platform.yml` during live converge; after
  adding explicit `vars_files` loading to every realtime play and rerunning
  `make converge-realtime env=production`, `realtime.lv3.org` rendered on the
  live edge again and returned the expected oauth2 sign-in redirect

The first governed `make provision-subdomain FQDN=realtime.lv3.org env=production`
attempt hit a transient Hetzner record-creation failure inside a `no_log`
Ansible task even though zone discovery and token validation succeeded. A
direct Hetzner API POST using the same credential from `nginx-lv3` created the
missing A record, and the governed playbook then reran cleanly, expanded the
shared Let's Encrypt certificate, and completed the edge verification path.

## Related ADRs

- ADR 0011: Monitoring stack rollout
- ADR 0071: Agent observation loop and autonomous drift detection
- ADR 0133: Portal authentication by default
