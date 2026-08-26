# ADR 0476: Wire `make converge-nginx-edge` to `fix-edge-certificate.yml`

- Status: Implemented
- Implementation Status: Complete (this release)
- Date: 2026-04-29
- Concern: cert-lifecycle, ci-cd, drift
- Tags: cert-validation, ADR-0414-followup, gate-cleanup
- Reservation: res-0476-cert-lifecycle-make-target-fix
- Implements: ADR 0475 follow-up — eliminate the cert-validation gate
  bypass forced on Phases 10/11/12.
- Depends on:
  - ADR 0414 — cert lifecycle manager
  - ADR 0375 — certificate validation

## Context

`scripts/cert_lifecycle_manager.py sync-missing --apply` invokes
`make converge-nginx-edge env=<env>` to reconcile the shared NGINX
edge SAN cert. The make target does not exist:

```
$ make converge-nginx-edge env=production
make: *** No rule to make target `converge-nginx-edge'.  Stop.
[error] converge-nginx-edge failed (exit 2). 44 mismatches remain.
```

`configure-edge-publication` runs the full edge converge
(`playbooks/public-edge.yml`), which is broader than what
`sync-missing` needs and races with operator releases.
`playbooks/fix-edge-certificate.yml` is the narrow tool — it
reconciles the shared SAN cert only when missing public SANs are
detected.

## Decision

Add a top-level `converge-nginx-edge` make target that wraps
`playbooks/fix-edge-certificate.yml`, mirroring the
`configure-edge-publication` invocation pattern (env, bootstrap key,
proxmox-host jump connection). This closes the loop the cert manager
expects:

```make
converge-nginx-edge:
    ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_SCOPED_RUN) \
      --playbook playbooks/fix-edge-certificate.yml \
      --env $(env) -- \
      --private-key $(BOOTSTRAP_KEY) \
      -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
      $(EXTRA_ARGS)
```

## Consequences

- `cert_lifecycle_manager.py sync-missing --apply` runs end-to-end
  when the live edge is reachable, replacing the manual
  `ansible-playbook playbooks/fix-edge-certificate.yml` step in the
  ADR 0414 runbook.
- The cert-validation lane bypass on every push depends on the
  underlying edge being reachable — so this ADR fixes the *tooling*,
  but the bypass remains in effect until the operator's prod
  deployment regains a live nginx edge.

## What this leaves open

The current `prod` deployment under `.local/deployments/prod/` is
missing `connection.yml` and references VM 110 (nginx @ 10.10.10.40)
in `topology.yml` — that VM is not present on the live proxmox host
(`debian-base-template`). Either the lv3 prod nginx was decommissioned or the
deployment was migrated and the registry is stale. Operator action
required: regenerate `prod` connection.yml + update topology.yml with
the actual live VM list (`qm list` on the proxmox host) before the
sync-missing flow can reach an edge to converge.
