# fleet_node_exporter

Declares how Prometheus node_exporter is published on one host of the 0docker, 0database, 0own or 0mcp fleets:
the addresses it binds, the textfile collector directory and its ownership, optional systemd socket proxies that
republish an exporter on a tailnet address, and `tailscale serve` TCP forwards for userspace-mode tailscaled.

It models the exporter **port arrangement** per host, so that two listeners can never silently claim the same
`address:port`: the managed proxies and the exporter are checked against each other before anything changes, and a
proxy marked `state: unmanaged` is documented but never touched. A proxy marked `state: disabled` names a stale socket
unit that would collide with a managed one; the role keeps it stopped and disabled. Tailnet-bound proxy sockets set
`free_bind: true` (`FreeBind=true`) so they still bind while tailscaled has not yet given `tailscale0` its address.

Run it only through `playbooks/fleet-observability.yml` with an explicit `--limit`. See
`docs/runbooks/fleet-observability.md`.

What it does not do: it does not write the `.prom` files that other jobs drop into the textfile directory (they stay
owned by their writers), does not configure Prometheus targets (Scanopy file_sd does), and does not manage tailnet
policy or PVE firewall rules.
