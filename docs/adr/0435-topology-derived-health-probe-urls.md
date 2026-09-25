# ADR 0435: Topology-Derived Health-Probe URLs

- Status: Accepted
- Implementation Status: Proposed (catalog loader + migration of hardcoded URLs)
- Date: 2026-04-22
- Concern: forkability, IoC, health-probes, deploy-time
- Tags: health-probe-catalog, topology, ioc, adr-0407-extension, adr-0424
- Relates to:
  - ADR 0064 (health probe contracts for all services)
  - ADR 0407 (generic-by-default `.local/` overlay)
  - ADR 0424 (0fork clone onto Hetzner AX41)
  - ADR 0433 (topology-derived guest firewall `host_source`)

---

## Context

`config/health-probe-catalog.json` declares per-service liveness, readiness,
and Uptime Kuma probe definitions. URLs and hosts are stored as **literal
strings** that encode the production LV3 deployment topology. Example
(gitea):

```json
"liveness": {
  "kind": "http",
  "url": "http://10.10.10.92:3003/api/healthz",
  ...
}
```

`10.10.10.92` is the LV3 runtime-control guest IP. When a forked deployment
(ADR 0424) runs the same gitea playbook, the playbook's convergence succeeds
on the fork's runtime-control (`10.10.10.10`), but the post-verify HTTP
probe invoked via `playbooks/tasks/verify-probe.yml` dials `10.10.10.92`
— which does not exist on the fork network. The probe retries 24× with
5s delay and fails the play, even though the service itself is healthy.

This is a **second instance of the same pattern** described in ADR 0433:
infrastructure constants that differ between deployments are baked into
committed config. The health-probe catalog affects every service with a
non-loopback probe URL, not just gitea.

## Decision

Health-probe catalog URLs **must derive from topology at render time,
not from literal IPs at commit time**. The catalog is still committed
as JSON (so the schema and retry/status policy stay reviewable), but
host components are expressed as placeholders resolved by the catalog
loader.

### Placeholder syntax

Replace the host portion of every `url` / `host` field with one of:

- `{{owning_vm}}` → resolved to `hostvars[<service>.owning_vm].ansible_host`
- `{{loopback}}` → always `127.0.0.1`
- A literal IP or hostname is still legal for external targets (e.g.
  `grafana.example.com` for a public-edge probe).

Example rewrite for gitea:

```json
"liveness": {
  "kind": "http",
  "url": "http://{{owning_vm}}:3003/api/healthz",
  ...
}
```

### Loader responsibility

`Load the health probe catalog` task (currently a file-read) becomes a
two-step: read + render. Rendering uses the service's `owning_vm` field
(already in the catalog) to resolve `{{owning_vm}}` via `hostvars`.

### Migration

1. Add a `render_health_probe_catalog` filter or task-layer transform
   that substitutes placeholders.
2. Audit the catalog; rewrite every hardcoded `10.10.10.*` URL to the
   placeholder form.
3. The public `ServerClaw` mirror already sanitizes `10.10.10.*` via
   the publish pipeline. Placeholder-form catalog entries pass through
   unchanged, reducing the sanitization surface (current: ~588 files
   per publish — see CLAUDE.md §9).

### Out of scope

- Probe retries/delays/status codes (unchanged).
- Uptime Kuma `monitor.url` fields intended for external resolution
  (these already use domain names).
- Non-URL probe kinds (`tcp`, `command`, `systemd`) that reference
  hosts by inventory_hostname and already derive correctly.

## Consequences

- First-time fork deployments stop failing post-verify on services
  whose runtime itself is healthy.
- The catalog remains a single committed source of truth; only the
  loader gains a render step.
- Pairs naturally with ADR 0433: both remove committed infrastructure
  constants from the surface exposed to clone-from-public users.

## Validation

A forked deployment running `ansible-playbook playbooks/gitea.yml` should
see the liveness probe resolve to the fork's `owning_vm` IP, not the
prod LV3 IP. The 0fork deployment on 2026-04-22 surfaced this defect
and workarounded it by killing the playbook after service-level health
was confirmed; an ADR-compliant catalog would let the converge complete
cleanly on the first run.
