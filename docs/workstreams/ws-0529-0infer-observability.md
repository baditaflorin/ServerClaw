# 0infer inventory and observability

## Goal

Extend the existing monitoring and Scanopy inventory automation to cover the
0infer Proxmox host and its running guests over private Tailscale routes.

## Scope

- Add 0infer to the monitoring VM's Scanopy onboarding list over the host's
  private Tailscale address; route guest daemon traffic through the private
  `vmbr70` relay so VM704 is covered without a Tailscale interface.
- Onboard all running 0infer guests through the existing QEMU Guest Agent path,
  and add both the host discovery daemon and the Proxmox API discovery daemon.
- Permit only the required monitoring SSH, node-exporter, and Scanopy TCP
  flows; keep Proxmox API and other management ports restricted.
- Add the Proxmox host and PostgreSQL guest to the exporter inventory.
- Use `0database` as the Scanopy/fleet identity for the existing PVE01 host;
  preserve `pve01` only where it remains the actual host name or transport alias.

## Verification

Run `pytest -q tests/test_scanopy_onboard_hv.py tests/test_monitoring_prometheus_codification.py`,
`python3 scripts/tailscale_policy_sync.py check`, the relevant Ansible
inventory/playbook syntax checks, and the repository validation gate. Live
policy and monitoring application follow after merge and green main CI.
