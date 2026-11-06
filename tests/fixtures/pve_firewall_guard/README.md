# pve_firewall_guard fixtures

Per-VM Proxmox firewall files used by `tests/test_pve_firewall_install_guard.py`. `live/<vmid>.fw` stands for
`/etc/pve/firewall/<vmid>.fw` on the hypervisor, `render/<vmid>.fw` for the inventory render (`vm.fw.j2`).

| VM  | live                                                                                          | render                                      | verdict |
| --- | --------------------------------------------------------------------------------------------- | ------------------------------------------- | ------- |
| 191 | hand-authored rules with comments, an AUTO-MIGRATED set, a disabled rule, a `fleet-pool-fw` block | only the rules the inventory knows          | refused |
| 140 | one hand-authored rule with a comment, one rule                                               | both rules (re-spaced) plus one new rule    | additive |
| 155 | no file                                                                                       | a new policy                                | new file |
| 110 | identical to the render                                                                       | identical                                   | unchanged |

The shapes are the ones the 2026-10-30 incident removed: a render that is a strict subset of the live file.
