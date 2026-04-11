# ws-realtime-dynamic-children — Auto-discover all production hosts as Netdata streaming children

## Problem

`realtime.example.com` was missing newly provisioned VMs because the Netdata child host list was hardcoded in two places:

1. `netdata_runtime_child_inventory_hosts` in `roles/netdata_runtime/defaults/main.yml` — a static YAML list
2. The `hosts:` pattern in the `realtime.yml` playbook children play — explicit hostnames

When new VMs (`runtime-ai`, `runtime-control`, `runtime-general`, `coolify-apps`, etc.) were added to the inventory, they were not automatically picked up by the monitoring topology.

## Solution

Replace both hardcoded references with dynamic inventory-group derivation:

- `netdata_runtime_child_inventory_hosts` now computes its value at playbook time by unioning `proxmox_hosts` and `lv3_guests`, intersecting with the `production` group, and excluding the monitoring parent (`monitoring`).
- The `hosts:` pattern in `realtime.yml` uses `proxmox_hosts:lv3_guests:&production:!monitoring` so Ansible automatically targets all production hosts.

## Effect

Any VM added to the `production` group in `inventory/hosts.yml` will automatically receive Netdata child agent configuration and stream metrics to `realtime.example.com` on the next `realtime.yml` playbook run. No manual updates to defaults or playbook host lists required.
