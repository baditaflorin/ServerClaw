# ADR 0489: Firewall Rule Provenance and Dependency-Gap Detection

**Status**: ACCEPTED
**Date**: 2026-08-26
**Decision**: `network_policy` rules get an optional `provenance` block (owner/added_on/reconciled_from_live/workstream), backfilled organically. `scripts/firewall_drift.py` adds a sixth drift source to ADR 0091's suite — declared-vs-live diffing for both the guest nftables and Proxmox `.fw` layers — plus a static `depends_on` cross-reference against `config/service-capability-catalog.json` that catches a missing rule before it causes an outage, not after.

---

## Context

ADR 0091 named "network routes or firewall rules changed during an incident that were never cleaned up" as a drift source on day one, then implemented five other sources (tofu, ansible check-mode, docker image, DNS, TLS) and never came back for this one.

Two production incidents surfaced the gap on 2026-08-26:

1. **Gitea's LFS storage (MinIO at docker-runtime:9010) was unreachable from gitea's host (runtime-control).** Traced through a watchdog crash-loop (unrelated, already fixed), a container reporting "healthy" while its web server never actually listened, and a tcpdump confirming SYNs arriving with no SYN-ACK/RST — down to: port 9010 was never in `network_policy` for `docker-runtime` at all. Gitea's `secret_catalog_ids` already listed `gitea_minio_secret_key` — the dependency was real and known, just never declared anywhere a machine could check it.
2. **A live, uncommitted rule was found on `docker-runtime`'s guest nftables** (source `monitoring`, port `9100`, node_exporter) that matched this repo's own idempotent apply pattern but had no corresponding commit here — drift in the other direction: live state ahead of the declared source of truth, at risk of being silently reverted the next time `linux_guest_firewall` runs.

### A third mechanism, found but not yet located

While reconciling (2), the live `/etc/pve/firewall/120.fw` turned out to already contain both the 9100 rule *and* a previously-unknown one (`docker-build` → `docker-runtime:9000`, a Woodpecker CI dispatch path), inside a marked block:

```
# BEGIN fleet-pool-fw (generated from firewall-pools.json -- edit that, not this)
IN ACCEPT -source 10.10.10.30/32 -p tcp -dport 9000  # Woodpecker agent (docker-build-lv3) -> server gRPC (docker-runtime), dual-host CI dispatch
IN ACCEPT -source 10.10.10.40/32 -p tcp -dport 9100  # node_exporter scrape -- feeds fleet:placement_score (OPS.md 2026-08-25)
# END fleet-pool-fw
```

This reads as a real, deliberate, dated, documented mechanism — not an ad-hoc edit. It was searched for exhaustively and **not found**: not in this repo (`grep -r "firewall-pools.json\|fleet-pool-fw"` — zero hits), not in `baditaflorin/ServerClaw`, not anywhere on GitHub via `gh search code` for the exact marker strings. The `OPS.md` it cites doesn't exist in this repo either. Best hypothesis, consistent with the original investigation (empty bash history on the guest, no sshd session logs for the edit window, a 3-hour clock skew on an earlier drift backup's filename): this tool runs from somewhere outside this fleet's git-tracked surface — plausibly the operator's own machine — and has never been checked in.

**This is an open question for the operator, not something this ADR resolves.** See "Follow-ups."

## Decision

### 1. Optional per-rule provenance

```yaml
network_policy:
  guests:
    docker-runtime:
      allowed_inbound:
        - source: monitoring
          protocol: tcp
          ports: [9100]
          description: Prometheus node_exporter metrics scrape access
          provenance:
            owner: operator@example.com
            added_on: "2026-08-26"
            reconciled_from_live: true    # discovered live before being declared here
            workstream: null              # optional ADR/workstream id
```

`provenance` is optional and additive — `description` remains the primary human-readable field and is unchanged on all 191 pre-existing rules. This mirrors `services-registry`'s own `owner` field precedent: schema-defined, zero big-bang migration, backfilled organically, audited going forward rather than enforced retroactively. `argument_specs.yml` for `linux_guest_firewall`/`proxmox_network` already declares `network_policy` as an unvalidated `dict`, so this needed no role changes — only the templates matter, and neither `nftables.conf.j2` nor `vm.fw.j2` reads `provenance` (or `description`), so adding it is render-safe by construction.

### 2. `scripts/firewall_drift.py` — declared-vs-live diff

Two layers, one script, following the `dns_drift.py` / `tls_cert_drift.py` `collect_drift() -> list[dict]` convention:

- **guest-nftables**: SSH to each guest, `nft list ruleset`, parse the `input` chain, diff against `network_policy` resolved the same way `nftables.conf.j2`'s `render_rule` macro does (management/all_guests/host/named-guest/raw-CIDR/public expansion).
- **proxmox-fw**: SSH to the Proxmox host, `cat /etc/pve/firewall/<vmid>.fw`, same diff against the `vm.fw.j2`-equivalent declared set (including its `allow_container_forwarding` local-CIDR carve-out).

A live rule with no declared match is `critical` ("likely applied out-of-band") **unless** it falls inside a `# BEGIN <name>` / `# END <name>` marked block, in which case it's `warn` ("externally managed by `<name>`, not yet mirrored") — see the fleet-pool-fw discussion above. A declared rule absent from live state is `warn` ("apply is pending"). Unparsed live lines are surfaced as their own `warn` records rather than silently dropped — validated against real captures (357/357 nftables lines, 325/325 `.fw` lines parsed cleanly against `docker-runtime` in production).

Wired into `drift_detector.py` as a sixth source (`--skip-firewall` to opt out), and standalone via `make firewall-deps-report` / `make firewall-explain TARGET=... PORT=... SOURCE=...`.

### 3. Dependency-gap check (the part that would have caught the actual outage)

`config/service-capability-catalog.json` gets an optional `depends_on: [<service-id>, ...]` field (schema in `docs/schema/service-capability-catalog.schema.json`), same organic-backfill convention. `collect_dependency_gaps()` resolves each dependency pair to `(depender.vm, dependency.vm, port-from-internal_url)` and checks whether any `network_policy` rule on the dependency's guest permits the depender's guest on that port — a **static, declared-vs-declared** check that runs without SSH and would have flagged the gitea → MinIO gap before it caused an outage, not after. Verified with a live regression: removing the reconciled `docker-runtime` rule for `runtime-control:9010` reproduces the exact finding; restoring it clears it.

`services-registry` (the separate `0crawl`/`0exec` service mesh repo) was considered as the cross-reference source instead and ruled out — it has zero entries for gitea, minio, or any Proxmox VM in this fleet's topology. `config/service-capability-catalog.json` is the correct source because it already carries `vm` and `internal_url` for every service on *this* fleet.

### 4. Query mode

`firewall_drift.py explain <target> <port> <source>` answers "can X reach Y on port P, and why" against the declared source of truth, returning the matched rule, its resolved source CIDR, and its `provenance`/`owner` if present — the five-second lookup the 2026-08-26 gitea outage postmortem said should have existed instead of a packet capture and a cross-reference of three separate firewall layers.

### Reconciled in this change

Three rules discovered live without a matching declaration are now declared, closing both the outage-causing gap and the two drift instances found while building this:

| Guest | Source | Port | Description | `reconciled_from_live` |
|---|---|---|---|---|
| docker-runtime | runtime-control | 9010 | Gitea LFS access to the MinIO S3 API | `false` (not observed live at reconciliation time — see below) |
| docker-runtime | docker-build | 9000 | Woodpecker agent gRPC dispatch, dual-host CI dispatch | `true` |
| docker-runtime | monitoring | 9100 | Prometheus node_exporter metrics scrape access | `true` |

The gitea/MinIO rule is marked `reconciled_from_live: false` because, unlike the other two, it was not observed as a live rule during this investigation — it closes the *declared* gap (and the dependency-gap check now passes for it) but still needs an `ansible-playbook` apply against `docker-runtime` before it takes effect in production. That apply is intentionally **not** part of this change — see Non-Goals.

## Non-Goals

- **Not applying anything live.** This ADR only changes the declared source of truth (`platform_server`, private) and adds detection tooling. Applying the reconciled rules to production hosts, and publishing the schema change to the `ServerClaw` mirror, are separate, deliberate operator actions.
- **Not covering the Docker `forward` chain** in the guest-nftables layer (only `input`), or the `output` chain (policy `accept`, out of scope for an inbound-allowlist audit).
- **Not resolving the `fleet-pool-fw` / `firewall-pools.json` mystery.** The managed-block detection makes the drift detector correctly *tolerant* of it; it does not find or absorb it.

## Follow-ups

1. **Find (or build) `firewall-pools.json`.** If it's a real personal script, it should either move into this repo (so it has the same provenance/review this ADR is trying to establish for everything else) or be formally registered as a known external source-of-truth with an owner and a location, the same way this ADR asks every other rule to be.
2. **Apply the reconciled rules.** `ansible-playbook -i inventory/hosts.yml playbooks/site.yml -l docker-runtime` (or the narrower firewall-only tags, if any) to make the gitea/MinIO fix and the docker-build/monitoring reconciliations take effect live, then re-run `make drift-report ENV=production` to confirm clean.
3. **Publish to ServerClaw once reviewed.** `make publish-serverclaw` (dry run) then `make publish-serverclaw-push`, per the operator's own call given ServerClaw is public.
4. **Backfill `depends_on` beyond gitea → minio** as other cross-host dependencies are identified — organically, per the services-registry precedent, not as a blocking migration.
